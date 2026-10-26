"""Time embedding a random sample of timewindow chunks; estimate full-corpus time.

Usage:
    uv run python -m scripts.time_embeddings            # 200 chunks, EMBEDDING_MODEL
    uv run python -m scripts.time_embeddings --n 50 --model ollama:nomic-embed-text

Run scripts.build_chunks first. Vectors are discarded. The result replaces the
timing section at the end of $THP_DATA_DIR/chunks/report.md.
"""

from __future__ import annotations

import argparse
import os
import random
import time

from scripts.build_chunks import METHODS, TIMING_MARKER, chunks_dir, read_jsonl
from src.llm import get_embeddings

SEED = 7
BATCH = 16


def _hms(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    return f"{h} h {rem // 60:02d} min" if h else f"{rem // 60} min {rem % 60:02d} s"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--model", help="override EMBEDDING_MODEL")
    args = parser.parse_args()

    out_dir = chunks_dir()
    corpora = {m: read_jsonl(out_dir / f"{m}.jsonl") for m in METHODS}
    sample = random.Random(SEED).sample(corpora["timewindow"], args.n)
    texts = [c["text"] for c in sample]

    spec = args.model or os.getenv("EMBEDDING_MODEL")
    embeddings = get_embeddings(spec)
    embeddings.embed_documents(texts[:2])  # warm-up: model load, excluded

    t0 = time.perf_counter()
    for k in range(0, len(texts), BATCH):
        embeddings.embed_documents(texts[k : k + BATCH])
    elapsed = time.perf_counter() - t0

    per_chunk = elapsed / len(texts)
    per_kchar = elapsed / sum(len(t) for t in texts) * 1000
    lines = [
        TIMING_MARKER,
        "",
        "## Embedding timing",
        "",
        f"`{spec}`, {len(texts)} random timewindow chunks (seed {SEED}), batches of {BATCH}, "
        f"warm-up excluded: **{elapsed:.1f} s total, {per_chunk:.3f} s/chunk** "
        f"({per_kchar:.3f} s per 1k chars). Vectors were not stored.",
        "",
        "Estimated full-corpus time. *By chunk* = chunks x s/chunk; *by length* = "
        "total chars x s/char, which accounts for charsplit_350's shorter chunks "
        "(but not per-call overhead, so its true time sits between the two).",
        "",
        "| method | chunks | total chars | by chunk | by length |",
        "|---|---:|---:|---:|---:|",
    ]
    for method, recs in corpora.items():
        chars = sum(len(r["text"]) for r in recs)
        lines.append(
            f"| `{method}` | {len(recs)} | {chars:,} | {_hms(len(recs) * per_chunk)} "
            f"| {_hms(chars * per_kchar / 1000)} |"
        )
    section = "\n".join(lines) + "\n"

    report_path = out_dir / "report.md"
    report = report_path.read_text()
    head = report.split(TIMING_MARKER)[0] if TIMING_MARKER in report else report + "\n"
    report_path.write_text(head + section)
    print(section)


if __name__ == "__main__":
    main()
