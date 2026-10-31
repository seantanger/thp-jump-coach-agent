"""Synthetic planner templates for tests. Made-up content and chunk IDs, never transcript text."""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import yaml

C = "vidAAAAAAAA@95#0"   # a made-up chunk ID used as the default cite
C2 = "vidBBBBBBBB@0#1"


def template_dict(reviewed: bool = True) -> dict:
    return copy.deepcopy({
        "id": "synth_macro", "name": "Synthetic macrocycle", "kind": "macrocycle", "model": "long_conjugate",
        "sources": ["vidAAAAAAAA"],
        "defaults": {"values": {"lift_days": ["mon", "wed", "fri"], "jump_session_minutes": 40}, "cites": [C]},
        "elastic_exercises": ["depth jump", "approach jump"],
        "scheduling": {"pattern": ["lift", "jump", "lift"], "hard_day_types": ["lift", "jump"],
                       "min_days_between_hard": 2, "allowed_back_to_back": [], "missed_sessions": "skip",
                       "cites": [C]},
        "cycles": [
            {"id": "volume", "name": "Volume", "emphasis": "volume", "goal": "build work capacity",
             "weeks": {"min": 4, "max": 4}, "entry_criteria": "none", "exit_criteria": "4 weeks done",
             "primes_next": "strength", "allowed_jumping": None, "cites": [C],
             "day_types": [{"id": "lift", "label": "Lift", "cites": [C]},
                           {"id": "jump", "label": "Jump session", "cites": [C2]}],
             "prescriptions": [
                 {"day_type": "lift", "exercise": "back squat", "equipment": ["barbell", "rack"],
                  "sets": {"min": 4, "max": 5}, "reps": {"min": 6, "max": 12},
                  "intensity": {"min": 65, "max": 70, "unit": "%"}, "rest": "2-3 min", "notes": None, "cites": [C]},
                 {"day_type": "jump", "exercise": "depth jump", "equipment": ["box"],
                  "sets": {"min": 3, "max": 3}, "reps": {"min": 5, "max": 5},
                  "intensity": {"min": 40, "max": 40, "unit": "cm"}, "rest": None, "notes": None, "cites": [C2]}]},
            {"id": "strength", "name": "Strength", "emphasis": "absolute strength", "goal": "raise max strength",
             "weeks": {"min": 4, "max": 4}, "entry_criteria": "volume done", "exit_criteria": "4 weeks done",
             "primes_next": None, "allowed_jumping": None, "cites": [C2],
             "day_types": [{"id": "lift", "label": "Lift", "cites": [C2]}],
             "prescriptions": [
                 {"day_type": "lift", "exercise": "back squat", "equipment": ["barbell", "rack"],
                  "sets": {"min": 5, "max": 5}, "reps": {"min": 3, "max": 4},
                  "intensity": {"min": 80, "max": 85, "unit": "%"}, "rest": None, "notes": None, "cites": [C2]}]},
        ],
        "week_kinds": {"normal": {"volume": {"min": 1, "max": 1}, "cites": [C]},
                       "unload": {"volume": {"min": 0.6, "max": 0.7}, "cites": [C]},
                       "taper": {"volume": {"min": 0.3, "max": 0.5}, "cites": [C2]}},
        "end": {"kind": "taper", "days": {"min": 10, "max": 14}, "min_loading_weeks": 6, "cites": [C2]},
        "gates": [{"id": "g1", "track": "macro", "signal": "jump_result", "condition": "3 bad sessions in a row",
                   "decision": "unload", "cites": [C]}],
        "review": {"drafted": date(2026, 10, 30), "reviewed_by_user": reviewed, "notes": ""},
    })


def write_template(directory: Path, data: dict | None = None) -> Path:
    data = data or template_dict()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{data['id']}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


# --- program builders (Task 4+) ----------------------------------------------------

MON = date(2026, 11, 2)  # a Monday


def profile(**overrides):
    from src.planner.schema import Profile
    data = dict(training_age_years=2.0, lifts={"back_squat_lb": 315.0}, standing_vertical_in=28.0,
                approach_vertical_in=34.0, standing_reach_in=None, height_in=72.0, days_per_week=4,
                available_days=["mon", "tue", "wed", "fri"], session_minutes=90,
                equipment=["barbell", "rack", "box", "platform"], event=None, goal="dunk", knee_pain=None)
    data.update(overrides)
    return Profile(**data)


def session(exercise="back squat", sets=5, reps=6, intensity=("%", 70.0), cites=(C,), deviation=None):
    from src.planner.schema import Session
    from src.units import Quantity
    q = Quantity(value=intensity[1], unit=intensity[0]) if intensity else None
    return Session(exercise=exercise, sets=sets, reps=reps, intensity=q, rest=None, notes=None,
                   cites=list(cites), deviation=deviation)


def day(on: date, day_type="lift", sessions=None):
    from src.planner.schema import Day
    return Day(date=on, day_type=day_type, sessions=sessions if sessions is not None else [session()])


def week(start: date = MON, mesocycle_index=0, kind="normal", volume=1.0, days=None):
    from datetime import timedelta
    from src.planner.schema import Week
    days = days if days is not None else [day(start), day(start + timedelta(days=2)), day(start + timedelta(days=4))]
    return Week(start=start, mesocycle_index=mesocycle_index, kind=kind, volume_modifier=volume, days=days)


def outline(start: date = MON, event_date=None):
    from datetime import timedelta
    from src.planner.schema import Macrocycle, Mesocycle, Outline
    m1 = Mesocycle(index=0, cycle_id="volume", name="Volume", emphasis="volume", start=start,
                   end=start + timedelta(days=27), goal="work capacity", entry_criteria="start",
                   exit_criteria="4 weeks", primes_next="strength", cites=[C])
    m2 = Mesocycle(index=1, cycle_id="strength", name="Strength", emphasis="absolute strength",
                   start=start + timedelta(days=28), end=start + timedelta(days=55), goal="max strength",
                   entry_criteria="volume done", exit_criteria="4 weeks", primes_next=None, cites=[C2])
    macro = Macrocycle(model="long_conjugate", template_id="synth_macro", start=start, event_date=event_date,
                       end="taper", cites=[C])
    return Outline(macrocycle=macro, mesocycles=[m1, m2], tendon_track=None)


def proposal(kind="new", weeks=None, with_outline=True, profile_changes=None, summary="First two weeks."):
    from datetime import timedelta
    from src.planner.schema import Proposal, Reason
    if weeks is None:
        weeks = [week(MON), week(MON + timedelta(days=7))]
    return Proposal(kind=kind, request=None, decision="accept", summary=summary,
                    reasons=[Reason(text="Template month 1.", cites=[C])], profile_changes=profile_changes,
                    replace_outline=outline() if with_outline else None, replace_weeks=weeks)
