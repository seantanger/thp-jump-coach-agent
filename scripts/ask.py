"""Ask the coach graph one question and print the full message trace.

Usage:
    uv run python -m scripts.ask "My flight time was 0.52 s, how high did I jump?"
    uv run python -m scripts.ask --model ollama:qwen3:4b "..."
"""

from __future__ import annotations

import argparse

from langchain_core.messages import HumanMessage

from src.graph import build_graph
from src.llm import get_llm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--model", help="override COACH_MODEL, e.g. ollama:qwen3:4b")
    args = parser.parse_args()

    graph = build_graph(llm=get_llm("coach", model_spec=args.model))
    state = graph.invoke({"messages": [HumanMessage(args.question)]}, {"recursion_limit": 10})
    for message in state["messages"]:
        message.pretty_print()


if __name__ == "__main__":
    main()
