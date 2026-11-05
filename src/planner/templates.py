"""Cycle templates: hand-built from the transcripts, every number cited, loaded only once reviewed.

Templates live in $THP_DATA_DIR/templates/<id>.yaml (transcript-derived, never in this repo).
Numbers keep the unit the transcript used; code converts to lb / in for athletes.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, model_validator

from src.kb.paths import templates_dir

# Templates cite this method's chunk IDs. IDs are only unique within one method (charsplit_350 has a different
# "vid@0#0"), so the Planner, its Verifier and plan source links must all read this method.
TEMPLATE_METHOD = "charsplit_matched"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Range(_Strict):
    min: float
    max: float
    unit: str | None = None

    @model_validator(mode="after")
    def _ordered(self):
        if self.min > self.max:
            raise ValueError(f"min {self.min} > max {self.max}")
        return self


class Defaults(_Strict):
    values: dict[str, Any]
    cites: list[str]


class DayType(_Strict):
    id: str
    label: str
    cites: list[str]


class Prescription(_Strict):
    day_type: str
    exercise: str
    equipment: list[str]
    sets: Range | None  # None: the transcript gives no number
    reps: Range | None
    intensity: Range | None
    rest: str | None
    notes: str | None
    cites: list[str]


class Cycle(_Strict):
    id: str
    name: str
    emphasis: str
    goal: str
    weeks: Range | None  # None: the transcript gives no length
    entry_criteria: str
    exit_criteria: str
    primes_next: str | None
    allowed_jumping: list[str] | None  # tendon stages: exercise names allowed; None = no restriction
    day_types: list[DayType]
    prescriptions: list[Prescription]
    cites: list[str]


class WeekKind(_Strict):
    volume: Range
    cites: list[str]


class TemplateEnd(_Strict):
    kind: Literal["taper", "unload"]
    days: Range
    min_loading_weeks: int
    cites: list[str]


class Gate(_Strict):
    id: str
    track: str
    signal: str
    condition: str
    decision: Literal["hold", "progress", "unload", "step_back"]
    cites: list[str]


class Scheduling(_Strict):
    """How a week is laid out: an order of day types and spacing rules, not fixed weekdays."""
    pattern: list[str]                      # day types in order within a week (or a repeating cycle)
    hard_day_types: list[str]               # day types that count as hard for spacing
    min_days_between_hard: int              # 2 = at least one easy day between hard days
    allowed_back_to_back: list[list[str]]   # hard pairs the source does run on consecutive days
    missed_sessions: Literal["skip"]        # a missed session is dropped, not made up
    cites: list[str]


class Review(_Strict):
    drafted: date
    reviewed_by_user: bool
    notes: str


class Template(_Strict):
    id: str
    name: str
    kind: Literal["macrocycle", "tendon_track"]
    model: str
    sources: list[str]
    defaults: Defaults
    elastic_exercises: list[str]
    scheduling: Scheduling
    cycles: list[Cycle]
    week_kinds: dict[str, WeekKind]
    end: TemplateEnd | None
    gates: list[Gate]
    review: Review

    @model_validator(mode="after")
    def _everything_cited(self):
        missing = [path for path, obj in _cited_parts(self) if not obj.cites]
        if missing:
            raise ValueError(f"uncited: {', '.join(missing)}")
        known = {d.id for c in self.cycles for d in c.day_types}
        s = self.scheduling
        unknown = [d for d in (*s.pattern, *s.hard_day_types, *(x for pair in s.allowed_back_to_back for x in pair))
                   if d not in known]
        if unknown:
            raise ValueError(f"scheduling uses unknown day types: {', '.join(sorted(set(unknown)))}")
        return self


def _cited_parts(t: Template):
    yield "defaults", t.defaults
    yield "scheduling", t.scheduling
    for i, c in enumerate(t.cycles):
        yield f"cycles[{i}]", c
        for j, d in enumerate(c.day_types):
            yield f"cycles[{i}].day_types[{j}]", d
        for j, p in enumerate(c.prescriptions):
            yield f"cycles[{i}].prescriptions[{j}]", p
    for name, k in t.week_kinds.items():
        yield f"week_kinds.{name}", k
    if t.end:
        yield "end", t.end
    for i, g in enumerate(t.gates):
        yield f"gates[{i}]", g


def load_template(template_id: str, directory: Path | None = None, require_reviewed: bool = True) -> Template:
    path = (directory or templates_dir()) / f"{template_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no template {template_id!r} in {path.parent}")
    template = Template.model_validate(yaml.safe_load(path.read_text()))
    if require_reviewed and not template.review.reviewed_by_user:
        raise PermissionError(f"template {template_id} is not reviewed yet")
    return template


def list_templates(directory: Path | None = None) -> list[str]:
    """IDs of the reviewed templates."""
    directory = directory or templates_dir()
    ids = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            load_template(path.stem, directory)
        except (PermissionError, ValueError):
            continue
        ids.append(path.stem)
    return ids


def template_cites(t: Template) -> set[str]:
    return {cid for _, obj in _cited_parts(t) for cid in obj.cites}


def _cycle_cites(c: Cycle) -> set[str]:
    return {*c.cites, *(x for d in c.day_types for x in d.cites), *(x for p in c.prescriptions for x in p.cites)}


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


def find_prescription(t: Template, cycle_id: str, day_type: str, exercise: str) -> Prescription | None:
    cycle = next((c for c in t.cycles if c.id == cycle_id), None)
    if cycle is None:
        return None
    return next((p for p in cycle.prescriptions
                 if p.day_type == day_type and _norm(p.exercise) == _norm(exercise)), None)


@tool(response_format="content_and_artifact")
def get_cycle(template_id: str, cycle_id: str | None = None) -> tuple[str, dict]:
    """Read a reviewed training template, or one cycle (mesocycle / tendon stage) of it.

    Args:
        template_id: e.g. "long_conjugate_6mo" or "tendon_track".
        cycle_id: one cycle's id; omit for the whole template.

    Returns:
        The template or cycle with its prescriptions, ranges, entry / exit criteria and chunk-ID cites.
    """
    t = load_template(template_id)
    if cycle_id is None:
        data, cites = t.model_dump(mode="json"), template_cites(t)
    else:
        cycle = next((c for c in t.cycles if c.id == cycle_id), None)
        if cycle is None:
            raise ValueError(f"no cycle {cycle_id!r} in {template_id}; cycles: {[c.id for c in t.cycles]}")
        data, cites = cycle.model_dump(mode="json"), _cycle_cites(cycle)
    artifact = {"template_id": template_id, "data": data, "cites": sorted(cites)}
    return json.dumps(artifact), artifact
