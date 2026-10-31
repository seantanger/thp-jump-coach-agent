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
