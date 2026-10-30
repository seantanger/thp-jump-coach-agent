"""Tools the agents can call."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar

from langchain_core.tools import tool

from src.kb.search import search

G = 9.81  # m/s^2


def jump_height_cm(flight_time_s: float) -> float:
    """Jump height from flight time: h = g * t^2 / 8, returned in cm."""
    if flight_time_s <= 0:
        raise ValueError("flight_time_s must be positive")
    if flight_time_s > 2.0:
        raise ValueError("flight_time_s looks wrong (> 2 s); pass seconds, not ms")
    return round(G * flight_time_s**2 / 8 * 100, 2)


@tool
def jump_height(flight_time_s: float) -> float:
    """Convert a vertical jump's flight time (air time) into jump height.

    Args:
        flight_time_s: Time in the air in SECONDS (convert ms to s first, e.g. 520 ms -> 0.52).

    Returns:
        Jump height in centimetres, from h = g * t^2 / 8.
    """
    return jump_height_cm(flight_time_s)


# --- search_library ----------------------------------------------------------

MIN_WORDS = 15  # shorter chunks are fragments, not answers
MAX_K = 10
RESULT_FIELDS = ("chunk_id", "channel", "title", "timestamp", "url_t", "promo_candidate", "text")


_RETRIEVAL_OVERRIDE = ContextVar("retrieval_override", default=None)

@contextmanager
def retrieval_settings(config=None):
    """Per-question settings; isolated between Streamlit sessions and graph tasks."""
    token = _RETRIEVAL_OVERRIDE.set(config)
    try:
        yield
    finally:
        _RETRIEVAL_OVERRIDE.reset(token)


def retrieval_config() -> dict:
    """Which index search_library reads: RETRIEVAL_METHOD / _MODE / _K in the env."""
    if override := _RETRIEVAL_OVERRIDE.get():
        return dict(override)
    return {
        "method": os.getenv("RETRIEVAL_METHOD") or "charsplit_matched",
        "mode": os.getenv("RETRIEVAL_MODE") or "dense",
        "k": int(os.getenv("RETRIEVAL_K") or 5),
    }


def library_results(query: str, k: int | None = None) -> list[dict]:
    """Top chunks for one query, trimmed to RESULT_FIELDS; chunks under MIN_WORDS are skipped."""
    config = retrieval_config()
    k = max(1, min(int(config["k"] if k is None else k), MAX_K))
    hits = search(query, k=k, method=config["method"], mode=config["mode"])
    return [
        {"chunk_id": c["chunk_id"], "channel": c["channel_name"], "title": c["title"],
         "timestamp": c["timestamp"], "url_t": c["url_t"], "promo_candidate": c["promo_candidate"],
         "text": c["text"]}
        for c in hits
        if c["word_count"] >= MIN_WORDS
    ]


@tool(response_format="content_and_artifact")
def search_library(query: str, k: int | None = None) -> tuple[str, list[dict]]:
    """Search the John Evans / THP Strength transcript library for passages that answer a question.

    Write the query in coaching terms, not the athlete's words (e.g. "eccentric
    strength" rather than "lowering phase"). Each result has a chunk_id: cite it
    as [chunk_id] after every claim it supports.

    Args:
        query: What to look for, in coaching vocabulary.
        k: How many passages to return (default from RETRIEVAL_K, at most 10).

    Returns:
        A JSON list of {chunk_id, channel, title, timestamp, url_t, promo_candidate, text}.
        promo_candidate=true means the passage contains a sales plug; ignore that part.
    """
    results = library_results(query, k)
    return json.dumps(results, ensure_ascii=False), results


TOOLS = [jump_height, search_library]
