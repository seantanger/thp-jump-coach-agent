"""Chunk text and display metadata by chunk ID, for source links and the Verifier."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable

from src.kb.paths import load_chunks
from src.tools import retrieval_config


@lru_cache(maxsize=4)
def _by_id(method: str) -> dict[str, dict]:
    return {c["chunk_id"]: c for c in load_chunks(method)}


def chunk_meta(ids: Iterable[str], method: str | None = None) -> dict[str, dict]:
    """{chunk_id: {channel, title, timestamp, url_t}} for the IDs that exist."""
    chunks = _by_id(method or retrieval_config()["method"])
    return {cid: {"channel": chunks[cid]["channel_name"], "title": chunks[cid]["title"],
                  "timestamp": chunks[cid]["timestamp"], "url_t": chunks[cid]["url_t"]}
            for cid in ids if cid in chunks}
