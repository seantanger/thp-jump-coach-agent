"""The Planner from the command line: profile, new plan, next weeks, show. Every change asks for approval.

Usage:
    uv run python -m scripts.plan profile                  # answer prompts (lb / in), or --from-json PATH
    RETRIEVAL_MODE=bm25 uv run python -m scripts.plan new  # outline + first 1-2 weeks
    RETRIEVAL_MODE=bm25 uv run python -m scripts.plan next # next 1-2 weeks
    uv run python -m scripts.plan show                     # this week and the months ahead
    add --full to any command for the developer view (source links, paths, checks, trace)
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.kb.evidence import chunk_meta
from src.planner import run
from src.planner.render import render_outline, render_proposal, render_week
from src.planner.schema import Profile
from src.planner.store import load_profile, load_program, save_profile

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _ask(prompt: str, default=None, cast=str):
    raw = input(f"{prompt}{f' [{default}]' if default not in (None, '') else ''}: ").strip()
    if not raw:
        return default
    return cast(raw)


def _number_or_none(raw: str):
    return None if raw.lower() in ("", "-", "none") else float(raw)


def profile_command(args) -> None:
    if args.from_json:
        profile = Profile.model_validate_json(Path(args.from_json).read_text())
    else:
        old = load_profile()
        d = old.model_dump(mode="json") if old else {}
        lifts = {}
        for lift in ("back_squat", "power_clean"):
            value = _ask(f"{lift.replace('_', ' ')} max (lb, blank to skip)",
                         (d.get("lifts") or {}).get(f"{lift}_lb"), _number_or_none)
            if value:
                lifts[f"{lift}_lb"] = float(value)
        days = _ask("available days (e.g. mon,wed,fri,sat)", ",".join(d.get("available_days", [])))
        event_date = _ask("event date YYYY-MM-DD (blank for none)", (d.get("event") or {}).get("date"))
        profile = Profile.model_validate({
            "training_age_years": float(_ask("years of serious training", d.get("training_age_years", 1.0))),
            "lifts": lifts,
            "standing_vertical_in": _number_or_none(str(_ask("standing vertical (in)", d.get("standing_vertical_in")) or "")),
            "approach_vertical_in": _number_or_none(str(_ask("approach vertical (in)", d.get("approach_vertical_in")) or "")),
            "standing_reach_in": _number_or_none(str(_ask("standing reach (in)", d.get("standing_reach_in")) or "")),
            "height_in": _number_or_none(str(_ask("height (in)", d.get("height_in")) or "")),
            "days_per_week": int(_ask("training days per week", d.get("days_per_week", 4))),
            "available_days": [x.strip().lower()[:3] for x in (days or "").split(",") if x.strip()],
            "session_minutes": int(_ask("minutes per session", d.get("session_minutes", 90))),
            "equipment": [x.strip() for x in (_ask("equipment (comma separated)",
                                                  ",".join(d.get("equipment", ["barbell", "rack", "box"]))) or "").split(",")
                          if x.strip()],
            "event": {"date": event_date, "name": _ask("event name", (d.get("event") or {}).get("name", "test day"))}
            if event_date else None,
            "goal": _ask("goal", d.get("goal", "jump higher")),
            "knee_pain": None,
            "injury_notes": _ask("injury notes", d.get("injury_notes", "")) or "",
        }, strict=False)
    path = save_profile(profile)
    print(f"Saved profile to {path}")


def _decide(result: run.RunResult, full: bool) -> None:
    while result.status == "awaiting_approval":
        print(render_proposal(result, full=full))
        choice = input("\n[a]pprove, [r]eject or re[v]ise? ").strip().lower()[:1]
        if choice == "a":
            result = run.resume(result.thread_id, "approve")
        elif choice == "v":
            result = run.resume(result.thread_id, "revise", comment=input("What should change? "))
        else:
            result = run.resume(result.thread_id, "reject")
    print(render_proposal(result, full=full))


def show_command(args) -> None:
    program = load_program()
    if program is None:
        print("No plan yet — run `plan profile`, then `plan new`.")
        return
    sources = None
    if args.full:
        cites = {c for w in program.weeks for d in w.days for s in d.sessions for c in s.cites}
        sources = chunk_meta(cites)
    print(render_outline(program, full=args.full) + "\n")
    print(render_week(program, date.today(), full=args.full, sources=sources))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="developer view")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("profile")
    p.add_argument("--from-json")
    sub.add_parser("new")
    sub.add_parser("next")
    sub.add_parser("show")
    args = parser.parse_args()

    if args.command == "profile":
        profile_command(args)
    elif args.command == "show":
        show_command(args)
    else:
        _decide(run.start("new" if args.command == "new" else "roll_forward"), args.full)


if __name__ == "__main__":
    main()
