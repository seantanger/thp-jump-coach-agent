"""Retrieval scoring against time-range gold (method-agnostic).

A retrieved chunk is a hit when it comes from a gold video and its
[start, end] overlaps one of that video's gold ranges. Gold is a time range,
not a chunk ID, so every chunking method is scored the same way.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.kb.chunk import format_timestamp, url_at

KS = (1, 5, 10)


def load_questions(path: Path) -> list[dict]:
    return yaml.safe_load(Path(path).read_text())["questions"]


def in_scope(questions: list[dict]) -> list[dict]:
    """Questions with gold; out-of-scope ones (gold: []) are excluded from recall."""
    return [q for q in questions if q["gold"]]


def is_hit(chunk: dict, gold: list[dict]) -> bool:
    return any(
        chunk["video_id"] == g["video_id"] and chunk["start"] < g["end"] and chunk["end"] > g["start"]
        for g in gold
    )


def score_question(results: list[dict], gold: list[dict], ks: tuple[int, ...] = KS) -> dict:
    """results are ranked chunks (best first). recall@k is 1 if any of the top k
    is a hit (did the reader get at least one answering passage); rr is
    1 / rank of the first hit, 0 if none. video@5 is the looser diagnostic "a
    gold video is in the top 5", to separate wrong-place-in-right-video misses
    (often incomplete gold) from wrong-video misses."""
    hits = [is_hit(r, gold) for r in results]
    first = next((i + 1 for i, h in enumerate(hits) if h), None)
    videos = {g["video_id"] for g in gold}
    scores = {f"recall@{k}": float(any(hits[:k])) for k in ks}
    scores["video@5"] = float(any(r["video_id"] in videos for r in results[:5]))
    scores["rr"] = 1.0 / first if first else 0.0
    scores["first_hit_rank"] = first
    scores["hits"] = hits
    return scores


def aggregate(per_question: list[dict], ks: tuple[int, ...] = KS) -> dict:
    n = len(per_question)
    out = {f"recall@{k}": sum(q[f"recall@{k}"] for q in per_question) / n for k in ks}
    out["mrr"] = sum(q["rr"] for q in per_question) / n
    out["video@5"] = sum(q["video@5"] for q in per_question) / n
    return out


def promo_share(results_by_question: list[list[dict]], k: int = 5) -> float:
    """Fraction of all top-k results that are promo_candidate chunks."""
    top = [r for results in results_by_question for r in results[:k]]
    return sum(r["promo_candidate"] for r in top) / len(top) if top else 0.0


def review_markdown(questions: list[dict], titles: dict[str, str]) -> str:
    """Checklist for verifying gold on YouTube (private: contains quotes)."""
    lines = [
        "# Retrieval test questions: gold review",
        "",
        "Open each link, check the range answers the question, then set `status:` in",
        "`questions.yaml` to `verified` (correct as is) or `fixed` (you edited the gold).",
        "Gold lists the strong sources found by keyword search, not necessarily every one.",
        "",
    ]
    for q in questions:
        lines += [f"## {q['id']} ({q['topic']}, {q['difficulty']}): status: {q['status']}", "",
                  f"**{q['question']}**", ""]
        if not q["gold"]:
            lines += ["_Out of scope: no gold. Should be refused / answered as not covered._", ""]
            continue
        for g in q["gold"]:
            lines.append(
                f"- [{titles.get(g['video_id'], g['video_id'])} @ {format_timestamp(g['start'])}"
                f"–{format_timestamp(g['end'])}]({url_at(g['video_id'], g['start'])}): \"{g['quote']}\""
            )
        lines.append("")
    return "\n".join(lines)
