"""Pieces of the agent tool loop shared by the Coach and the Planner."""

from __future__ import annotations

import time

from langchain_core.messages import ToolMessage

from src.trace import Tracer

SEARCH_TOOL = "search_library"


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
