"""Embed chunks into the persistent Chroma index, one collection per method.

Usage (takes hours on CPU; resumable, so just rerun after an interruption):
    nohup caffeinate -i uv run python -u -m scripts.build_index \
        >> ~/git/thp-ai/data/index/build.log 2>&1 &
    uv run python -m scripts.build_index timewindow --min-words 15

Methods are built in order (timewindow first). Chunks under --min-words are
skipped; chunks already embedded with the same text are not re-embedded.
"""

from __future__ import annotations

import argparse
import json

from src.kb.index import INDEX_CONFIG, METHODS, build_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("methods", nargs="*", help=f"default: {' '.join(METHODS)}")
    parser.add_argument("--min-words", type=int, default=INDEX_CONFIG["min_words"])
    args = parser.parse_args()

    unknown = set(args.methods) - set(METHODS)
    if unknown:
        parser.error(f"unknown method(s) {sorted(unknown)}; choose from {METHODS}")
    config = {**INDEX_CONFIG, "min_words": args.min_words}
    for method in args.methods or METHODS:
        stats = build_index(method, config=config, log=lambda s: print(s, flush=True))
        print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
