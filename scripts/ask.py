"""Ask the coach one question; print the rendered answer, citation check and search queries.

Usage:
    RETRIEVAL_MODE=bm25 uv run python -m scripts.ask "Do isometrics help patellar tendon pain?"
    uv run python -m scripts.ask --model ollama:qwen3:4b "..."
    uv run python -m scripts.ask --raw "..."     # also print the answer with [chunk_id] markers

Retrieval reads RETRIEVAL_METHOD / RETRIEVAL_MODE / RETRIEVAL_K (dense mode
needs Ollama for the query embedding; bm25 does not). Each run writes a trace
to $THP_DATA_DIR/traces/.
"""

from __future__ import annotations

import argparse

from src.llm import get_llm
from src.qa import answer_question
from src.tools import retrieval_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--model", help="override COACH_MODEL, e.g. ollama:qwen3:4b")
    parser.add_argument("--raw", action="store_true", help="also print the unrendered answer")
    args = parser.parse_args()

    result = answer_question(args.question, llm=get_llm("coach", model_spec=args.model))
    check = result["check"]
    print(result["rendered"])
    if args.raw:
        print("\n--- raw answer ---\n" + result["answer"])
    print("\n--- citation check:", "PASS" if check["passed"] else "FAIL", "---")
    for reason in check["reasons"]:
        print(f"  {reason}")
    for claim in check["uncited_claims"]:
        print(f"  uncited: {claim[:100]}")
    print(f"  cited: {', '.join(check['cited']) or '(none)'}")
    print(f"\n--- searches ({retrieval_config()}) ---")
    for q in result["queries"]:
        print(f"  {q}")
    print(f"\ntokens {result['tokens']}  trace {result['trace']}")


if __name__ == "__main__":
    main()
