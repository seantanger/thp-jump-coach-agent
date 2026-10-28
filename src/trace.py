"""Local run traces: one JSONL file per question in $THP_DATA_DIR/traces/ (no LangSmith).

Traces hold the question, queries, chunk IDs and the answer, so they live with
the private data, not in this repo.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


class Tracer:
    """Appends one JSON object per event: {"ts", "run_id", "node", ...fields}."""

    def __init__(self, directory: Path | None = None, run_id: str | None = None):
        self.run_id = run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.path = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"{self.run_id}.jsonl"

    def log(self, node: str, **fields) -> None:
        if self.path is None:
            return
        event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "run_id": self.run_id, "node": node, **fields}
        with self.path.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def usage(message) -> dict:
    """Token counts from an AIMessage, {} if the provider sent none."""
    meta = getattr(message, "usage_metadata", None) or {}
    return {k: meta[k] for k in ("input_tokens", "output_tokens", "total_tokens") if k in meta}
