"""Training log: what the athlete says they did and how it felt. Append-only facts, never a plan change."""

from __future__ import annotations

import json
from datetime import date, datetime

from langchain_core.tools import tool

from src.kb.paths import athlete_dir

RECENT = 10  # entries shown in the chat's first message; `read_log` goes further back


def _path():
    return athlete_dir() / "log.jsonl"


def load_log() -> list[dict]:
    """All entries, oldest first (by date, then by when they were noted)."""
    path = _path()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    return sorted(rows, key=lambda r: (r["date"], r["noted_at"]))


def add_entry(day: str, text: str, knee_pain: int | None = None, noted_at: datetime | None = None) -> dict:
    date.fromisoformat(day)  # a bad date raises; the tool turns that into a message for the model
    if knee_pain is not None and not 0 <= knee_pain <= 10:
        raise ValueError("knee_pain is 0-10")
    entry = {"date": day, "text": text.strip(), "knee_pain": knee_pain,
             "noted_at": (noted_at or datetime.now()).isoformat(timespec="seconds")}
    same = [r for r in load_log() if r["date"] == day and r["text"] == entry["text"]]
    if same:  # the model sometimes repeats a call in one turn
        return same[0]
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def render_log(entries: list[dict]) -> str:
    return "\n".join(f"- {e['date']}: {e['text']}" + (f" (knee {e['knee_pain']}/10)" if e["knee_pain"] is not None else "")
                     for e in entries) or "(empty)"


def recent_log(limit: int = RECENT) -> str:
    """The last entries plus a pointer to the rest, for the chat's and the Planner's first message."""
    rows = load_log()
    older = f"\n({len(rows) - limit} earlier entries: use read_log)" if len(rows) > limit else ""
    return render_log(rows[-limit:]) + older


@tool
def log_workout(day: str, text: str, knee_pain: int | None = None) -> str:
    """Write down what the athlete did or how they felt, as they said it. Saved at once; it does not change the plan.

    Use it when they report a session, weights, soreness or pain ("I did 135 today", "knee felt 2/10 after jumps").
    One call per day reported. If the report should change future days, also offer a plan draft.

    Args:
        day: the date it happened, YYYY-MM-DD (work out "today" or "Saturday" from the date in the first message).
        text: what they did and felt, with their numbers, in one or two sentences.
        knee_pain: knee pain 0-10 if they gave one, else omit.
    """
    entry = add_entry(day, text, knee_pain)
    return f"Logged {entry['date']}: {entry['text']}"


@tool
def read_log(since: str | None = None, limit: int = 60) -> str:
    """Read the athlete's training log further back than the recent entries in the first message.

    Use it for questions over time ("how much have I improved since week 1?", "how has my knee been?").

    Args:
        since: oldest date to include, YYYY-MM-DD; omit for the start.
        limit: most entries to return (the newest ones).
    """
    rows = [r for r in load_log() if since is None or r["date"] >= since]
    return render_log(rows[-limit:])
