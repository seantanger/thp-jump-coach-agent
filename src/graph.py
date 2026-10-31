"""Two-node LangGraph agent: coach (LLM) <-> tools, looping until no tool calls.

search_library is capped at SEARCH_CAP calls per question in the tools node:
calls past the cap are not run and get an error message back instead.
"""

from __future__ import annotations

import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from src.llm import get_llm
from src.prompts import load_prompt
from src.tools import TOOLS
from src.trace import Tracer, usage

SEARCH_TOOL = "search_library"
SEARCH_CAP = 4


class CoachState(MessagesState):
    search_calls: int


def run_tool(tools: dict, call: dict) -> ToolMessage:
    """Run one tool call; errors (e.g. ms passed instead of s) go back to the model so it can retry."""
    tool = tools.get(call["name"])
    if tool is None:
        return ToolMessage(f"Error: {call['name']} is not a valid tool, try one of {sorted(tools)}.",
                           tool_call_id=call["id"], name=call["name"], status="error")
    try:
        return tool.invoke({**call, "type": "tool_call"})
    except Exception as e:  # noqa: BLE001 - every tool error is reported to the model
        return ToolMessage(f"Error: {e!r}\n Please fix your mistakes.",
                           tool_call_id=call["id"], name=call["name"], status="error")


def run_capped(calls: list[dict], tools: dict, used: dict[str, int], caps: dict[str, int],
               total_cap: int | None, tracer: Tracer) -> tuple[list[ToolMessage], dict[str, int]]:
    """Run tool calls in order; calls past a per-tool cap or the total cap get an error message, not a run.

    `used` counts calls per tool name plus "_total"; the updated counts are returned.
    """
    used = {**used}
    out = []
    for call in calls:
        name, t0 = call["name"], time.perf_counter()
        tool_capped = name in caps and used.get(name, 0) >= caps[name]
        capped = tool_capped or (total_cap is not None and used.get("_total", 0) >= total_cap)
        if capped and tool_capped and name == SEARCH_TOOL:
            message = ToolMessage(
                f"Search limit reached ({caps[name]} searches per question); this search was not run. "
                "Answer from the chunks you already have, or say the library doesn't cover it.",
                tool_call_id=call["id"], name=name, status="error")
        elif capped:
            limit = f"{caps[name]} {name} calls" if tool_capped else f"{total_cap} tool calls"
            message = ToolMessage(f"Limit reached ({limit}); this call was not run. Finish with what you have.",
                                  tool_call_id=call["id"], name=name, status="error")
        else:
            used[name] = used.get(name, 0) + 1
            used["_total"] = used.get("_total", 0) + 1
            message = run_tool(tools, call)
        returned = message.artifact if isinstance(message.artifact, list) else None
        tracer.log("tools", tool=name, args=call["args"], status=message.status, capped=capped,
                   chunk_ids=[r["chunk_id"] for r in returned if "chunk_id" in r] if returned is not None else None,
                   latency_s=round(time.perf_counter() - t0, 3))
        out.append(message)
    used.setdefault(SEARCH_TOOL, 0)
    return out, used


def build_graph(llm: BaseChatModel | None = None, role: str = "coach", tracer: Tracer | None = None,
                search_cap: int = SEARCH_CAP, require_search: bool = False):
    """Compile the agent graph. Pass `llm` to inject a model (tests, comparisons)."""
    llm = llm or get_llm(role)
    llm_with_tools = llm.bind_tools(TOOLS)
    system = SystemMessage(content=load_prompt(role))
    tracer = tracer or Tracer()
    tools = {t.name: t for t in TOOLS}

    def coach(state: CoachState) -> dict:
        t0 = time.perf_counter()
        response = llm_with_tools.invoke([system, *state["messages"]])
        if require_search and not response.tool_calls and not state.get("search_calls", 0):
            question = next(m.content for m in state["messages"] if isinstance(m, HumanMessage))
            response = AIMessage(content=response.content, usage_metadata=response.usage_metadata,
                tool_calls=[{"name": SEARCH_TOOL, "args": {"query": question}, "id": "required_search"}])
        tracer.log("coach", latency_s=round(time.perf_counter() - t0, 3), tokens=usage(response),
                   tool_calls=[{"name": c["name"], "args": c["args"]} for c in response.tool_calls],
                   text_chars=len(response.text))
        return {"messages": [response]}

    def run_tools(state: CoachState) -> dict:
        out, used = run_capped(state["messages"][-1].tool_calls, tools,
                               {SEARCH_TOOL: state.get("search_calls", 0)}, {SEARCH_TOOL: search_cap}, None, tracer)
        return {"messages": out, "search_calls": used[SEARCH_TOOL]}

    graph = StateGraph(CoachState)
    graph.add_node("coach", coach)
    graph.add_node("tools", run_tools)
    graph.add_edge(START, "coach")
    graph.add_conditional_edges("coach", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "coach")
    return graph.compile()
