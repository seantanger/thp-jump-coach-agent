"""Quantities with units. Athletes see pounds and inches; templates keep the transcript's unit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Unit = Literal["lb", "kg", "in", "cm", "m", "%", "s", "min"]

LB_PER_KG = 2.20462
CM_PER_IN = 2.54
_TO_BASE = {"lb": ("mass", 1.0), "kg": ("mass", LB_PER_KG),
            "in": ("length", 1.0), "cm": ("length", 1 / CM_PER_IN), "m": ("length", 100 / CM_PER_IN),
            "s": ("time", 1.0), "min": ("time", 60.0), "%": ("percent", 1.0)}
ATHLETE_UNIT = {"kg": "lb", "cm": "in", "m": "in"}


class Quantity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: float
    unit: Unit


def convert(q: Quantity, unit: str) -> Quantity:
    """The same amount in another unit of the same kind (mass, length, time, percent)."""
    kind, factor = _TO_BASE[q.unit]
    target_kind, target_factor = _TO_BASE.get(unit, (None, None))
    if target_kind != kind:
        raise ValueError(f"can't convert {q.unit} to {unit}")
    return Quantity(value=q.value * factor / target_factor, unit=unit)


def display(q: Quantity) -> str:
    """Athlete-facing text: kg -> lb, cm/m -> in, one decimal, no trailing .0."""
    q = convert(q, ATHLETE_UNIT.get(q.unit, q.unit))
    number = f"{round(q.value, 1):g}"
    return f"{number}%" if q.unit == "%" else f"{number} {q.unit}"
