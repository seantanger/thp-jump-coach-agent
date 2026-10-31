"""Two-node LangGraph agent: coach (LLM) <-> tools, looping until no tool calls.

search_library is capped at SEARCH_CAP calls per question in the tools node:
calls past the cap are not run and get an error message back instead.
"""

from __future__ import annotations

import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from src.agent import SEARCH_TOOL, run_capped
from src.llm import get_llm
from src.prompts import load_prompt
from src.tools import TOOLS
from src.trace import Tracer, usage

SEARCH_CAP = 4


class CoachState(MessagesState):
    search_calls: int


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
