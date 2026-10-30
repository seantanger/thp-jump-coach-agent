"""Answer one question: run the coach graph, then check and render its citations."""

from __future__ import annotations

import time
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.citations import check_citations, render, parse_answer
from src.red_flags import referral_kind, SAFETY_NOTE
from src.graph import SEARCH_TOOL, build_graph
from src.kb.paths import traces_dir
from src.tools import retrieval_config, retrieval_settings
from src.trace import Tracer, usage

RECURSION_LIMIT = 25  # 4 searches + a few retries / jump_height calls, two steps each


def answer_question(question: str, llm: BaseChatModel | None = None, trace_dir: Path | None = None,
                    retrieval: dict | None = None) -> dict:
    """Shared CLI/UI/QA entry point; no conversation memory, session-local retrieval."""
    with retrieval_settings(retrieval):
        return _answer_question(question, llm, trace_dir)


def _answer_question(question: str, llm: BaseChatModel | None, trace_dir: Path | None) -> dict:
    """Returns structured answer, rendered markdown, check, retrieval, usage and private trace."""
    tracer = Tracer(traces_dir() if trace_dir is None else trace_dir)
    tracer.log("start", question=question, retrieval=retrieval_config())
    t0 = time.perf_counter()
    referral = referral_kind(question)
    if referral:
        note = ("Seek emergency care now for back pain with bladder/bowel changes or groin numbness."
                if referral == "urgent" else "See a physiotherapist or doctor before continuing to train this issue.")
        answer = dict(summary="", points=[], takeaway=None, safety_note=note, not_covered=False)
        check = check_citations(answer, {}, referral=True)
        tracer.log("end", latency_s=0, tokens={}, queries=[], retrieved=[], cited=[], check=check, answer=answer)
        return dict(answer=answer, rendered=render(answer, {}, check), check=check, queries=[],
                    retrieved={}, tokens={}, trace=tracer.path, latency_s=time.perf_counter()-t0, referral=referral)
    state = build_graph(llm, tracer=tracer, require_search=True).invoke(
        {"messages": [HumanMessage(question)], "search_calls": 0}, {"recursion_limit": RECURSION_LIMIT})
    messages = state["messages"]

    calls = {c["id"]: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
    searches = [m for m in messages if isinstance(m, ToolMessage) and m.name == SEARCH_TOOL
                and isinstance(m.artifact, list)]
    queries = [calls[m.tool_call_id]["args"].get("query", "") for m in searches]
    retrieved = {r["chunk_id"]: r for m in searches for r in m.artifact}

    raw = messages[-1].text
    try:
        answer = parse_answer(raw)
        if any(word in question.lower() for word in ("ache", "sore", "stiff", "pain", "tendon")):
            answer["safety_note"] = SAFETY_NOTE
        check = check_citations(answer, retrieved)
    except (ValueError, TypeError) as exc:
        answer = dict(summary="The Coach returned invalid structured output.", points=[],
                      takeaway=None, safety_note=None, not_covered=False)
        check = dict(passed=False, cited=[], fabricated=[], uncited_claims=[], not_covered=False,
                     reasons=[f"invalid structured output: {type(exc).__name__}"])
        tracer.log("invalid_output", raw=raw)

    tokens: dict[str, int] = {}
    for m in messages:
        if isinstance(m, AIMessage):
            for k, v in usage(m).items():
                tokens[k] = tokens.get(k, 0) + v
    tracer.log("end", latency_s=round(time.perf_counter() - t0, 3), tokens=tokens, queries=queries,
               retrieved=list(retrieved), cited=check["cited"], check=check, answer=answer)
    return {
        "latency_s": time.perf_counter() - t0,
        "referral": None,
        "answer": answer,
        "rendered": render(answer, retrieved, check),
        "check": check,
        "queries": queries,
        "retrieved": retrieved,
        "tokens": tokens,
        "trace": tracer.path,
    }
