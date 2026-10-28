"""Answer one question: run the coach graph, then check and render its citations."""

from __future__ import annotations

import time
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.citations import check_citations, render
from src.graph import SEARCH_TOOL, build_graph
from src.kb.paths import traces_dir
from src.tools import retrieval_config
from src.trace import Tracer, usage

RECURSION_LIMIT = 25  # 4 searches + a few retries / jump_height calls, two steps each


def answer_question(question: str, llm: BaseChatModel | None = None, trace_dir: Path | None = None) -> dict:
    """Returns answer (raw, with [chunk_id] markers), rendered, check, queries, retrieved, trace."""
    tracer = Tracer(traces_dir() if trace_dir is None else trace_dir)
    tracer.log("start", question=question, retrieval=retrieval_config())
    t0 = time.perf_counter()
    state = build_graph(llm, tracer=tracer).invoke(
        {"messages": [HumanMessage(question)], "search_calls": 0}, {"recursion_limit": RECURSION_LIMIT})
    messages = state["messages"]

    calls = {c["id"]: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
    searches = [m for m in messages if isinstance(m, ToolMessage) and m.name == SEARCH_TOOL
                and isinstance(m.artifact, list)]
    queries = [calls[m.tool_call_id]["args"].get("query", "") for m in searches]
    retrieved = {r["chunk_id"]: r for m in searches for r in m.artifact}

    answer = messages[-1].text
    check = check_citations(answer, retrieved)
    tokens: dict[str, int] = {}
    for m in messages:
        if isinstance(m, AIMessage):
            for k, v in usage(m).items():
                tokens[k] = tokens.get(k, 0) + v
    tracer.log("end", latency_s=round(time.perf_counter() - t0, 3), tokens=tokens, queries=queries,
               retrieved=list(retrieved), cited=check["cited"], check=check, answer=answer)
    return {
        "answer": answer,
        "rendered": render(answer, retrieved, check),
        "check": check,
        "queries": queries,
        "retrieved": retrieved,
        "tokens": tokens,
        "trace": tracer.path,
    }
