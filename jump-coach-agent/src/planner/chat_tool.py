"""The chat agent's one way to change a plan: run the Planner graph and hand back the pending proposal.

Nothing is saved here. The athlete approves in the UI, and `run.resume` makes code save it.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import tool

PLAN_TOOL = "propose_plan_change"


@tool(PLAN_TOOL, response_format="content_and_artifact")
def propose_plan_change(action: Literal["edit", "life_change", "new", "roll_forward"], request: str):
    """Draft a change to the athlete's saved plan for them to approve. Takes about a minute; at most once per question.

    Use it when the athlete reports doing something different ("I did 135 today"), asks to change the plan
    ("swap RDLs for hip thrusts", "only 3 days now"), or asks for a new plan or the next weeks. Never for
    questions about the plan or hypotheticals.

    Args:
        action: edit (change sessions), life_change (days, equipment, schedule), new (no plan yet), roll_forward (next weeks).
        request: the athlete's request in their own words, with the dates and numbers they gave.
    """
    from src.planner import run
    from src.planner.render import render_proposal
    result = run.start(action, request=request)
    return render_proposal(result), result
