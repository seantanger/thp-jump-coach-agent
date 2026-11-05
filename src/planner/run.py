"""Start and resume Planner runs: shared by the CLI and the UI. Paused runs live in a SQLite checkpointer."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langgraph.types import Command

from src.kb.paths import athlete_dir, traces_dir
from src.planner.graph import Verify, build_plan_graph, now  # noqa: F401 - now is used by callers
from src.planner.merge import Change
from src.planner.templates import TEMPLATE_METHOD
from src.tools import retrieval_config, retrieval_settings
from src.trace import Tracer

RECURSION_LIMIT = 100  # 3 attempts x (12 tool calls + answer) plus context / review / approve steps

Status = Literal["awaiting_approval", "saved", "rejected", "failed", "stale", "needs_profile", "declined"]


def _template_method():
    """Keep the caller's search mode and k, but read the chunk IDs the templates cite."""
    return retrieval_settings({**retrieval_config(), "method": TEMPLATE_METHOD})


@dataclass
class RunResult:
    thread_id: str
    status: Status
    proposal: dict | None = None
    changes: list[Change] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    verifier: dict | None = None
    version: int | None = None
    trace: Path | None = None


DEFAULT = object()  # "use the real Verifier"; tests switch it off via default_verifier


def default_verifier():
    from src.verifier import make_program_verifier
    return make_program_verifier()


def _verifier(verify):
    return default_verifier() if verify is DEFAULT else verify


_SAVER = None


def checkpointer():
    """One SQLite checkpointer per process, in the athlete data dir (paused proposals survive restarts)."""
    global _SAVER
    if _SAVER is None:
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = athlete_dir() / "checkpoints.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        _SAVER = SqliteSaver(sqlite3.connect(path, check_same_thread=False))
    return _SAVER


def _graph(thread_id: str, llm, verify):
    tracer = Tracer(traces_dir(), run_id=f"plan-{thread_id}")
    graph = build_plan_graph(llm=llm, verify=verify, tracer=tracer, checkpointer=checkpointer())
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    return graph, config, tracer


def _result(thread_id: str, state: dict, tracer: Tracer) -> RunResult:
    pending = state.get("__interrupt__")
    status = "awaiting_approval" if pending else state.get("status", "failed")
    version = state.get("saved_version")
    if pending:
        version = pending[0].value.get("version")
    return RunResult(thread_id=thread_id, status=status, proposal=state.get("proposal"),
                     changes=[Change(**c) for c in state.get("changes") or []], failures=state.get("failures") or [],
                     verifier=state.get("verifier"), version=version, trace=tracer.path)


def start(action: Literal["new", "roll_forward"], request: str | None = None, llm: BaseChatModel | None = None,
          verify: Verify | None = DEFAULT, thread_id: str | None = None, today: date | None = None) -> RunResult:
    thread_id = thread_id or uuid.uuid4().hex[:12]
    graph, config, tracer = _graph(thread_id, llm, _verifier(verify))
    with _template_method():
        state = graph.invoke({"messages": [], "action": action, "request": request,
                              "today": (today or date.today()).isoformat()}, config)
    return _result(thread_id, state, tracer)


def resume(thread_id: str, decision: Literal["approve", "reject", "revise"], comment: str | None = None,
           llm: BaseChatModel | None = None, verify: Verify | None = DEFAULT) -> RunResult:
    graph, config, tracer = _graph(thread_id, llm, _verifier(verify))
    with _template_method():
        state = graph.invoke(Command(resume={"decision": decision, "comment": comment}), config)
    return _result(thread_id, state, tracer)
