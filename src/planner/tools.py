"""Read-only tools for the Planner. Nothing here writes; code saves a program only after approval."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from src.planner import store
from src.planner.templates import get_cycle
from src.tools import jump_height, search_library

PLAN_CAPS = {"search_library": 6}
PLAN_TOTAL_CAP = 12
MAX_RETRIES = 2


@tool(response_format="content_and_artifact")
def get_profile() -> tuple[str, dict | None]:
    """The athlete's profile: training age, lifts (lb), verticals (in), available days, equipment, event, goal."""
    profile = store.load_profile()
    data = profile.model_dump(mode="json") if profile else None
    return json.dumps(data), data


@tool(response_format="content_and_artifact")
def get_program(version: int | None = None) -> tuple[str, dict | None]:
    """The athlete's saved program (latest version if none given): outline and the weeks filled so far.

    Args:
        version: a saved version number; omit for the latest.
    """
    program = store.load_program(version)
    data = program.model_dump(mode="json") if program else None
    return json.dumps(data), data


PLAN_TOOLS = [get_cycle, get_profile, get_program, search_library, jump_height]
