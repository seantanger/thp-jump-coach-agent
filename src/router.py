"""Code router: plan / program requests go to the Planner route, everything else to the Coach."""

from __future__ import annotations

import re
from typing import Literal

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_PROGRAM = re.compile("|".join([
    r"\b(?:plan|program|programme|schedule|mesocycle|macrocycle)s?\b",
    r"\b(?:this|next) (?:week|month)\b",
    r"\bonly (?:train )?\d+ days\b",
    r"\b\d+ days (?:a|per) week\b",
    rf"\b{_MONTH} \d{{1,2}}(?:st|nd|rd|th)?\b",
    r"\bmy (?:dunk )?(?:contest|event|competition|game|meet|tryouts?) is\b",
]), re.IGNORECASE)


def route(message: str) -> Literal["program", "coach"]:
    return "program" if _PROGRAM.search(message) else "coach"
