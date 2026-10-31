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
    sets: Range
    reps: Range
    intensity: Range | None
    rest: str | None
    notes: str | None
    cites: list[str]


class Cycle(_Strict):
    id: str
    name: str
    emphasis: str
    goal: str
    weeks: Range
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
        return self


def _cited_parts(t: Template):
    yield "defaults", t.defaults
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
