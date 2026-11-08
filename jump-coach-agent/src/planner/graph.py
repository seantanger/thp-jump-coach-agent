"""Planner graph: context → Planner (capped tool loop) → checks (retry ≤ 2) → approval interrupt → save.

The Planner only proposes. Code merges the proposal into a candidate version, runs the checks (and the
Verifier when one is given), pauses for the athlete's decision, and saves only on approval.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from src.agent import SEARCH_TOOL, run_capped
from src.llm import get_llm
from src.planner import store
from src.planner.checks import run_checks
from src.planner.merge import Change, diff_programs, merge_proposal
from src.planner.schema import Profile, Program, Proposal, parse_proposal
from src.planner.templates import list_templates, load_template
from src.planner.tools import MAX_RETRIES, PLAN_CAPS, PLAN_TOOLS, PLAN_TOTAL_CAP
from src.prompts import load_prompt
from src.trace import Tracer, usage

Verify = Callable[[list[Change], Proposal], tuple[list[str], list[str], dict | None]]


class PlanState(MessagesState):
    action: str
    request: str | None
    today: str                 # ISO date; strings keep checkpoints simple
    used: dict
    attempts: int              # failed reviews so far
    proposal: dict | None
    candidate: str | None      # candidate Program as JSON
    changes: list
    failures: list
    verifier: dict | None
    status: str
    saved_version: int | None


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _context_message(state: PlanState, profile, program: Program | None) -> HumanMessage:
    today = date.fromisoformat(state["today"])
    lines = [f"Action: {state['action']}", f"Request: {state.get('request') or '(none)'}",
             f"Today: {today} ({today.strftime('%A')})", f"Reviewed templates: {', '.join(list_templates()) or '(none)'}",
             f"Athlete profile: {profile.model_dump_json()}"]
    if program is None:
        lines.append("Current program: none yet.")
    else:
        meso = ", ".join(f"{m.index}:{m.cycle_id} {m.start}..{m.end}" for m in program.mesocycles)
        last = program.weeks[-1].start if program.weeks else None
        lines += [f"Current program: v{program.version}; mesocycles {meso}",
                  f"Last filled week starts {last}" if last else "No weeks filled yet."]
    return HumanMessage("\n".join(lines))


def _retrieved_ids(messages) -> set[str]:
    ids = set()
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        if isinstance(m.artifact, list):
            ids |= {r["chunk_id"] for r in m.artifact if isinstance(r, dict) and "chunk_id" in r}
        elif isinstance(m.artifact, dict) and isinstance(m.artifact.get("cites"), list):
            ids |= set(m.artifact["cites"])
    return ids


def build_plan_graph(llm: BaseChatModel | None = None, verify: Verify | None = None, tracer: Tracer | None = None,
                     checkpointer=None):
    llm = llm or get_llm("planner")
    llm_with_tools = llm.bind_tools(PLAN_TOOLS)
    system = SystemMessage(content=load_prompt("planner"))
    tracer = tracer or Tracer()
    tools = {t.name: t for t in PLAN_TOOLS}

    def context(state: PlanState) -> dict:
        profile = store.load_profile()
        if profile is None:
            tracer.log("context", status="needs_profile")
            return {"status": "needs_profile"}
        message = _context_message(state, profile, store.load_program())
        tracer.log("context", action=state["action"], request=state.get("request"))
        return {"messages": [message], "used": {}, "attempts": 0, "status": "planning"}

    def planner(state: PlanState) -> dict:
        t0 = time.perf_counter()
        response = llm_with_tools.invoke([system, *state["messages"]])
        tracer.log("planner", latency_s=round(time.perf_counter() - t0, 3), tokens=usage(response),
                   tool_calls=[{"name": c["name"], "args": c["args"]} for c in response.tool_calls])
        return {"messages": [response]}

    def run_tools(state: PlanState) -> dict:
        out, used = run_capped(state["messages"][-1].tool_calls, tools, state.get("used") or {}, PLAN_CAPS,
                               PLAN_TOTAL_CAP, tracer)
        return {"messages": out, "used": used}

    def retry(state: PlanState, failures: list[dict]) -> dict:
        attempts = state.get("attempts", 0) + 1
        tracer.log("review", passed=False, attempt=attempts, failures=failures)
        if attempts > MAX_RETRIES:
            return {"attempts": attempts, "failures": failures, "status": "failed"}
        text = "\n".join(f"- [{f['check']}] {f['path']}: {f['reason']}" for f in failures)
        message = HumanMessage(f"Your proposal failed these checks:\n{text}\n"
                               "Fix them and return the complete proposal JSON again.")
        return {"messages": [message], "attempts": attempts, "failures": failures, "used": {}, "status": "planning"}

    def review(state: PlanState) -> dict:
        raw = state["messages"][-1].text
        current, profile = store.load_program(), store.load_profile()
        templates = {tid: load_template(tid) for tid in list_templates()}
        try:
            proposal = parse_proposal(raw)
            if proposal.decision == "decline":  # e.g. a missing fact: show the athlete why, save nothing
                tracer.log("review", declined=True, summary=proposal.summary)
                return {"proposal": proposal.model_dump(mode="json"), "status": "declined"}
            candidate = merge_proposal(current, proposal, profile, now())
            if candidate.macrocycle.template_id not in templates:
                raise ValueError(f"template_id {candidate.macrocycle.template_id!r} is not a reviewed template; "
                                 f"use one of {sorted(templates)}")
        except (ValidationError, ValueError) as exc:
            return retry(state, [{"check": "schema", "path": "proposal", "reason": str(exc)[:600]}])
        # Anything read earlier in this run (before a retry or a revise) still counts as retrieved.
        retrieved = _retrieved_ids(state["messages"])
        failures = [f.model_dump() for f in run_checks(
            candidate, previous=current, profile=candidate.profile_snapshot, templates=templates,
            retrieved_ids=retrieved, gates=[], today=date.fromisoformat(state["today"]))]
        changes = diff_programs(current, candidate)
        verifier = None
        if not failures and verify is not None:
            verifier_failures, warnings, raw_result = verify(changes, proposal)
            verifier = {"warnings": warnings, "result": raw_result}
            failures = [{"check": "verifier", "path": "proposal", "reason": r} for r in verifier_failures]
        if failures:
            return {**retry(state, failures), "verifier": verifier}
        tracer.log("review", passed=True, attempt=state.get("attempts", 0) + 1, version=candidate.version,
                   changes=len(changes))
        return {"proposal": proposal.model_dump(mode="json"), "candidate": candidate.model_dump_json(),
                "changes": [c.model_dump(mode="json") for c in changes], "failures": [], "verifier": verifier,
                "status": "awaiting_approval"}

    def approve(state: PlanState) -> dict:
        candidate = Program.model_validate_json(state["candidate"])
        warnings = (state.get("verifier") or {}).get("warnings", [])
        decision = interrupt({"summary": state["proposal"]["summary"], "changes": state["changes"],
                              "warnings": warnings, "version": candidate.version})
        tracer.log("approve", decision=decision)
        choice = decision.get("decision")
        if choice == "approve":
            return {"status": "approved"}
        if choice == "revise":
            comment = decision.get("comment") or "Please revise the proposal."
            return {"messages": [HumanMessage(f"The athlete asked for changes: {comment}")], "attempts": 0,
                    "used": {}, "status": "planning"}
        return {"status": "rejected"}

    def save(state: PlanState) -> dict:
        candidate = Program.model_validate_json(state["candidate"])
        try:
            store.save_program(candidate)
        except store.StaleProgramError as exc:
            tracer.log("save", status="stale", reason=str(exc))
            return {"status": "stale"}
        if changes := state["proposal"].get("profile_changes"):
            # Applied to the profile as it is now, so an edit made while the proposal waited is kept.
            store.save_profile(Profile.model_validate({**store.load_profile().model_dump(), **changes}, strict=False))
        tracer.log("save", status="saved", version=candidate.version, profile_changes=changes)
        return {"status": "saved", "saved_version": candidate.version}

    def after_planner(state: PlanState) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "review"

    graph = StateGraph(PlanState)
    for name, node in (("context", context), ("planner", planner), ("tools", run_tools), ("review", review),
                       ("approve", approve), ("save", save)):
        graph.add_node(name, node)
    graph.add_edge(START, "context")
    graph.add_conditional_edges("context", lambda s: END if s.get("status") == "needs_profile" else "planner")
    graph.add_conditional_edges("planner", after_planner, {"tools": "tools", "review": "review"})
    graph.add_edge("tools", "planner")
    graph.add_conditional_edges("review", lambda s: {"awaiting_approval": "approve", "planning": "planner"}.get(
        s["status"], END))
    graph.add_conditional_edges("approve", lambda s: {"approved": "save", "planning": "planner"}.get(s["status"], END))
    graph.add_edge("save", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = ["build_plan_graph", "PlanState", "Verify", "SEARCH_TOOL"]
