"""Athlete profile, program versions and Planner proposals (spec §4). Strict: unknown keys fail."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, field_validator

from src.units import Quantity

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[str, ...] = get_args(Weekday)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Event(_Strict):
    date: date
    name: str


class KneePain(_Strict):
    status: Literal["none", "ache", "in_tendon_track"]
    notes: str = ""


class Profile(_Strict):
    training_age_years: float
    lifts: dict[str, float]                 # keys end in _lb, e.g. back_squat_lb
    standing_vertical_in: float | None
    approach_vertical_in: float | None
    standing_reach_in: float | None
    height_in: float | None
    days_per_week: int
    available_days: list[Weekday]
    session_minutes: int
    equipment: list[str]
    event: Event | None
    goal: str
    knee_pain: KneePain | None
    injury_notes: str = ""

    @field_validator("lifts")
    @classmethod
    def _pounds(cls, lifts: dict[str, float]) -> dict[str, float]:
        bad = [k for k in lifts if not k.endswith("_lb")]
        if bad:
            raise ValueError(f"lift keys must end in _lb (pounds): {bad}")
        return lifts

    @field_validator("days_per_week")
    @classmethod
    def _days(cls, n: int) -> int:
        if not 1 <= n <= 7:
            raise ValueError("days_per_week must be 1-7")
        return n


class Deviation(_Strict):
    reason: str
    cites: list[str]
    requested_by_user: bool = False


class Session(_Strict):
    exercise: str
    sets: int | None
    reps: int | None
    intensity: Quantity | None
    rest: str | None
    notes: str | None
    cites: list[str]
    deviation: Deviation | None = None


class Day(_Strict):
    date: date
    day_type: str
    sessions: list[Session]


class Week(_Strict):
    start: date
    mesocycle_index: int
    kind: Literal["normal", "unload", "taper"]
    volume_modifier: float
    days: list[Day]


class Mesocycle(_Strict):
    index: int
    cycle_id: str
    name: str
    emphasis: str
    start: date
    end: date
    goal: str
    entry_criteria: str
    exit_criteria: str
    primes_next: str | None
    cites: list[str]


class Macrocycle(_Strict):
    model: str
    template_id: str
    start: date
    event_date: date | None
    end: Literal["taper", "unload"]
    cites: list[str]


class TendonTrack(_Strict):
    template_id: str
    stage_id: str
    entered_on: date
    gate_to_next: str
    allowed_jumping: list[str]
    cites: list[str]


class Outline(_Strict):
    macrocycle: Macrocycle
    mesocycles: list[Mesocycle]
    tendon_track: TendonTrack | None


class Program(_Strict):
    version: int
    based_on: int | None
    created_at: datetime
    change_summary: str
    profile_snapshot: Profile
    macrocycle: Macrocycle
    mesocycles: list[Mesocycle]
    tendon_track: TendonTrack | None
    weeks: list[Week]


class Reason(_Strict):
    text: str
    cites: list[str]


class Proposal(_Strict):
    kind: Literal["new", "roll_forward", "life_change", "checkin", "edit"]
    request: str | None
    decision: Literal["accept", "adjust", "decline"]
    summary: str
    reasons: list[Reason]
    profile_changes: dict[str, Any] | None
    replace_outline: Outline | None
    replace_weeks: list[Week] | None


class GateResult(_Strict):
    track: str
    decision: Literal["hold", "progress", "unload", "step_back", "undecided"]
    rule_id: str | None
    inputs: dict[str, Any]
    cites: list[str]


def parse_proposal(raw: str) -> Proposal:
    """Planner output → Proposal; tolerates ``` fences and prose around the JSON object."""
    text = re.sub(r"```(?:json)?", "", raw)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in the Planner output")
    return Proposal.model_validate_json(text[start:end + 1])


def cites_in(obj) -> set[str]:
    """Every chunk ID under a "cites" key anywhere in a dumped (JSON-mode) structure."""
    if isinstance(obj, dict):
        found = set(obj["cites"]) if isinstance(obj.get("cites"), list) else set()
        return found.union(*(cites_in(v) for k, v in obj.items() if k != "cites"))
    if isinstance(obj, list):
        return set().union(*(cites_in(v) for v in obj))
    return set()
