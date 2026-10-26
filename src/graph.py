"""Two-node LangGraph agent: agent (LLM) <-> tools, looping until no tool calls."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.llm import get_llm
from src.prompts import load_prompt
from src.tools import TOOLS


def build_graph(llm: BaseChatModel | None = None, role: str = "coach"):
    """Compile the agent graph. Pass `llm` to inject a model (tests, comparisons)."""
    llm = llm or get_llm(role)
    llm_with_tools = llm.bind_tools(TOOLS)
    system = SystemMessage(content=load_prompt(role))

    def agent(state: MessagesState) -> dict:
        response = llm_with_tools.invoke([system, *state["messages"]])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    # Tool errors (e.g. ms passed instead of s) go back to the model so it can retry.
    graph.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
