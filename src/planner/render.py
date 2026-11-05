"""Athlete view (lean, no chunk IDs) and developer view (links, paths, failures) of plans and proposals."""

from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta

from src.coach.citations import link
from src.planner.merge import Change
from src.planner.schema import Program, Week
from src.units import Quantity, display

MAX_ATHLETE_CHANGES = 4


def _day(d: date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


def session_text(s: dict) -> str:
    """'back squat 5×6 @ 70%' from a session dict (athlete units)."""
    sets, reps = s.get("sets"), s.get("reps")
    dose = f"{sets}×{reps}" if sets and reps else f"{reps} reps" if reps else f"{sets} sets" if sets else ""
    intensity = s.get("intensity")
    load = f"@ {display(Quantity(**intensity))}" if intensity else ""
    return " ".join(x for x in (s["exercise"], dose, load) if x)


def _current_week(program: Program, today: date) -> Week | None:
    weeks = program.weeks
    current = [w for w in weeks if w.start <= today < w.start + timedelta(days=7)]
    upcoming = [w for w in weeks if w.start > today]
    return (current or upcoming or weeks[-1:] or [None])[0]


def render_week(program: Program, today: date, full: bool = False, sources: dict[str, dict] | None = None) -> str:
    week = _current_week(program, today)
    if week is None:
        return "No weeks written yet — run `plan next`."
    meso = program.mesocycles[week.mesocycle_index]
    weeks_in = math.ceil(((meso.end - meso.start).days + 1) / 7)
    header = (f"Month {meso.index + 1} of {len(program.mesocycles)} · {meso.emphasis} · "
              f"Week {(week.start - meso.start).days // 7 + 1} of {weeks_in}")
    if week.kind != "normal":
        header += f" · {week.kind} week"
    lines = [header, ""]
    for d in week.days:
        texts = [session_text(s.model_dump(mode="json")) for s in d.sessions] or [d.day_type]
        lines.append(f"{d.date:%a}  " + " · ".join(texts))
        if full:
            for s in d.sessions:
                links = " ".join(link(sources[c]) if sources and c in sources else c for c in s.cites)
                lines.append(f"      {s.exercise}: {links}")
                if s.deviation:
                    lines.append(f"      deviation: {s.deviation.reason}")
    if not full and any(s.cites for d in week.days for s in d.sessions):
        lines += ["", "ⓘ sources"]
    return "\n".join(lines)


def render_outline(program: Program, full: bool = False) -> str:
    lines = [f"Month {m.index + 1} · {_day(m.start)} – {_day(m.end)} · {m.emphasis} · {m.goal}"
             + (f"  [{', '.join(m.cites)}]" if full else "") for m in program.mesocycles]
    if program.tendon_track:
        lines.append(f"Knee: {program.tendon_track.stage_id} (next: {program.tendon_track.gate_to_next})")
    return "\n".join(lines)


_SESSION_PATH = re.compile(r"weeks\[(?P<week>[\d-]+)\]\.days\[(?P<day>[\d-]+)\]\.sessions\[\d+\]$")


def describe_change(c: Change) -> str:
    """One athlete-readable line per change."""
    m = _SESSION_PATH.match(c.path)
    if m:
        on = _day(date.fromisoformat(m["day"]))
        if c.before and c.after:
            before, after = session_text(c.before), session_text(c.after)
            if c.before["exercise"] == c.after["exercise"]:
                after = after[len(c.after["exercise"]) + 1:]
            return f"{on}: {before} → {after}"
        return f"{on}: {'added ' + session_text(c.after) if c.after else 'removed ' + session_text(c.before)}"
    if c.path == "macrocycle":
        return "New plan outline" if c.before is None else "Plan outline changed"
    if c.path.startswith("mesocycles[") and c.path.endswith("]"):
        i = int(c.path[len("mesocycles["):-1])
        return f"Month {i + 1}: {c.after['emphasis']}" if c.after else f"Month {i + 1} removed"
    if c.path.startswith("weeks[") and c.path.endswith("]"):
        start = date.fromisoformat(c.path[len("weeks["):-1])
        if c.after:
            return f"Week of {_day(start)}: {sum(len(d['sessions']) for d in c.after['days'])} sessions"
        return f"Week of {_day(start)} removed"
    field = c.path.rsplit(".", 1)[-1].replace("_", " ")
    return f"{field}: {c.before} → {c.after}"


def render_proposal(result, full: bool = False) -> str:
    status = result.status
    if status == "needs_profile":
        return "No profile yet — run `plan profile` first."
    if status == "saved":
        return f"Saved as version {result.version}."
    if status == "rejected":
        return "Discarded; nothing saved."
    if status == "stale":
        return "The plan changed while this proposal was waiting; run it again."
    if status == "declined":
        return f"Nothing changed: {(result.proposal or {}).get('summary', '')}"
    if status == "failed":
        if not full:
            return (f"Couldn't build a plan that passes the checks ({len(result.failures)} problem(s)). "
                    "Try again, or use --full / Developer view for details.")
        return "Checks failed:\n" + "\n".join(f"- [{f['check']}] {f['path']}: {f['reason']}" for f in result.failures)

    summary = (result.proposal or {}).get("summary", "")
    warnings = (result.verifier or {}).get("warnings", [])
    if not full:
        lines = ["What changes:"] + [f"  {describe_change(c)}" for c in result.changes[:MAX_ATHLETE_CHANGES]]
        if len(result.changes) > MAX_ATHLETE_CHANGES:
            lines.append(f"  (+{len(result.changes) - MAX_ATHLETE_CHANGES} more)")
        lines.append(f"Why: {summary}")
        if warnings:
            lines.append(f"⚠ {warnings[0]}")
        return "\n".join(lines)
    lines = [f"Proposal for version {result.version}: {summary}", ""]
    for c in result.changes:
        lines.append(f"- {c.path}: {json.dumps(c.before)} → {json.dumps(c.after)}")
    for w in warnings:
        lines.append(f"⚠ {w}")
    if result.verifier and result.verifier.get("result"):
        lines.append("Verifier: " + json.dumps(result.verifier["result"]))
    if result.trace:
        lines.append(f"trace {result.trace}")
    return "\n".join(lines)
