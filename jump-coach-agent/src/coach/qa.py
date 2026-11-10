"""Answer one question: run the coach graph, then check and render its citations."""

from __future__ import annotations

import time
from pathlib import Path

from langchain_core.language_models import BaseChatModel
import json
from datetime import date, timedelta

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.coach.citations import check_citations, render, render_compact, parse_answer
from src.coach.graph import SEARCH_TOOL, build_graph
from src.kb.paths import traces_dir
from src.planner.chat_tool import PLAN_TOOL, propose_plan_change
from src.tools import retrieval_config, retrieval_settings
from src.trace import Tracer, usage
from src.verifier import verifier_failures, verifier_warnings

RECURSION_LIMIT = 25  # 4 searches + a few retries / jump_height calls, two steps each
MAX_VERIFY_RETRIES = 2


def answer_verifier():
    """(question, answer, evidence) -> VerifierResult with the real Verifier; None turns it off."""
    from src.verifier import verify_answer
    return verify_answer


def answer_question(question: str, llm: BaseChatModel | None = None, trace_dir: Path | None = None,
                    retrieval: dict | None = None, verify: bool = True, history: list | None = None,
                    athlete: bool = False) -> dict:
    """Shared CLI/UI/QA entry point. `athlete=True` is the chat agent: it sees the athlete's profile and plan,
    the earlier turns (`history`: [(question, answer dict)]), and may draft a plan change for approval."""
    with retrieval_settings(retrieval):
        return _answer_question(question, llm, trace_dir, answer_verifier() if verify else None, history, athlete)


def athlete_context(today: date | None = None) -> str:
    """Today, the profile and the current week of the saved plan, as the chat agent's first message."""
    from src.planner import store
    from src.planner.render import render_outline, render_week
    today = today or date.today()
    profile, program = store.load_profile(), store.load_program()
    lines = [f"Today: {today} ({today:%A})",
             f"Athlete profile: {profile.model_dump_json() if profile else '(none yet)'}"]
    if program is None:
        lines.append("Saved plan: none yet.")
    else:
        lines += [f"Saved plan v{program.version} (weeks written through "
                  f"{program.weeks[-1].start + timedelta(days=6) if program.weeks else 'none'}):",
                  render_outline(program), "Current week:", render_week(program, today)]
    return "\n".join(lines)


def _past_turns(history: list | None, limit: int = 4) -> list:
    """Earlier turns as messages; answers go back as the JSON the model wrote, so it keeps that format."""
    out = []
    for question, result in (history or [])[-limit:]:
        if result.get("answer"):
            out += [HumanMessage(question), AIMessage(json.dumps(result["answer"]))]
    return out


def _read_answer(question: str, messages: list, tracer: Tracer) -> tuple[dict, dict, list[str], dict]:
    """Parse and code-check the coach's last message against this run's searches."""
    calls = {c["id"]: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
    searches = [m for m in messages if isinstance(m, ToolMessage) and m.name == SEARCH_TOOL
                and isinstance(m.artifact, list)]
    queries = [calls[m.tool_call_id]["args"].get("query", "") for m in searches]
    retrieved = {r["chunk_id"]: r for m in searches for r in m.artifact}
    raw = messages[-1].text
    try:
        answer = parse_answer(raw)
        check = check_citations(answer, retrieved)
    except (ValueError, TypeError) as exc:
        answer = dict(summary="The Coach returned invalid structured output.", points=[],
                      takeaway=None, safety_note=None, not_covered=False)
        check = dict(passed=False, cited=[], fabricated=[], uncited_claims=[], not_covered=False,
                     reasons=[f"invalid structured output: {type(exc).__name__}"])
        tracer.log("invalid_output", raw=raw)
    return answer, check, queries, retrieved


def _answer_question(question: str, llm: BaseChatModel | None, trace_dir: Path | None, verifier=None,
                     history: list | None = None, athlete: bool = False) -> dict:
    """Returns structured answer, full and compact markdown, check, retrieval, usage and private trace."""
    tracer = Tracer(traces_dir() if trace_dir is None else trace_dir)
    tracer.log("start", question=question, retrieval=retrieval_config())
    t0 = time.perf_counter()
    graph = build_graph(llm, tracer=tracer, require_search=not athlete, extra_tools=[propose_plan_change] if athlete else ())
    start = [HumanMessage(athlete_context()), *_past_turns(history)] if athlete else []
    state = graph.invoke({"messages": [*start, HumanMessage(question)], "search_calls": 0, "plan_calls": 0},
                         {"recursion_limit": RECURSION_LIMIT})
    verdict = None
    for attempt in range(MAX_VERIFY_RETRIES + 1):
        answer, check, queries, retrieved = _read_answer(question, state["messages"], tracer)
        if verifier is None or not check["passed"] or not answer["points"]:
            break
        try:
            verdict = verifier(question, answer, {c: retrieved[c]["text"] for c in check["cited"] if c in retrieved})
        except (ValueError, TypeError) as exc:
            tracer.log("verifier", attempt=attempt + 1, error=type(exc).__name__)
            verdict = None  # an earlier verdict was about an earlier answer
            check = {**check, "verifier_warnings": [f"Verifier output could not be read ({type(exc).__name__}); not verified"]}
            break
        failures = verifier_failures(verdict)
        tracer.log("verifier", attempt=attempt + 1, verdict=verdict.verdict, failures=failures)
        if not failures:
            break
        if attempt == MAX_VERIFY_RETRIES:
            check = {**check, "passed": False, "reasons": check["reasons"] + failures}
            break
        feedback = HumanMessage("A fresh-context check found problems:\n" + "\n".join(f"- {f}" for f in failures)
                                + "\nRevise and return the complete JSON answer again.")
        state = graph.invoke({"messages": [*state["messages"], feedback], "search_calls": state.get("search_calls", 0),
                              "plan_calls": state.get("plan_calls", 0)},
                             {"recursion_limit": RECURSION_LIMIT})
    if verdict is not None:
        check = {**check, "verifier": verdict.model_dump(), "verifier_warnings": verifier_warnings(verdict)}
    messages = state["messages"]

    tokens: dict[str, int] = {}
    for m in messages:
        if isinstance(m, AIMessage):
            for k, v in usage(m).items():
                tokens[k] = tokens.get(k, 0) + v
    tracer.log("end", latency_s=round(time.perf_counter() - t0, 3), tokens=tokens, queries=queries,
               retrieved=list(retrieved), cited=check["cited"], check=check, answer=answer)
    plans = [m.artifact for m in messages if isinstance(m, ToolMessage) and m.name == PLAN_TOOL and m.artifact]
    return {
        "latency_s": time.perf_counter() - t0,
        "referral": None,
        "plan": plans[-1] if plans else None,  # a RunResult; "awaiting_approval" shows Approve / Reject in the UI
        "answer": answer,
        "rendered": render(answer, retrieved, check),
        "compact": render_compact(answer, retrieved, check),
        "check": check,
        "queries": queries,
        "retrieved": retrieved,
        "tokens": tokens,
        "trace": tracer.path,
    }
