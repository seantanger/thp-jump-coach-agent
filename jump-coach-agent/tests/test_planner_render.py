"""Athlete and developer views of a program and of a pending proposal."""

from datetime import datetime, timedelta

from src.planner.merge import diff_programs, merge_proposal
from src.planner.render import render_outline, render_proposal, render_week
from src.planner.run import RunResult
from tests.planner_fixtures import C, C2, MON, day, profile, proposal, session, week

NOW = datetime(2026, 11, 1, 9, 0)
SOURCES = {C: {"channel": "Synth Channel", "title": "Squat Basics", "timestamp": "01:35",
               "url_t": "https://www.youtube.com/watch?v=vidAAAAAAAA&t=95s"},
           C2: {"channel": "Synth Channel", "title": "Depth Jumps", "timestamp": "00:00",
                "url_t": "https://www.youtube.com/watch?v=vidBBBBBBBB&t=0s"}}


def program(weeks=None):
    return merge_proposal(None, proposal(weeks=weeks), profile(), NOW)


def test_render_week_athlete_view_has_no_chunk_ids():
    text = render_week(program(), MON)
    assert text.splitlines()[0] == "Month 1 of 2 · volume · Week 1 of 4"
    assert "Mon  back squat 5×6 @ 70%" in text
    assert "@95#0" not in text and "vidAAAAAAAA" not in text
    assert text.splitlines()[-1] == "ⓘ sources"


def test_render_week_uses_lb_and_in():
    w = week(days=[day(MON, "lift", [session(intensity=("kg", 100.0))]),
                   day(MON + timedelta(days=2), "jump", [session("depth jump", 3, 5, ("cm", 40.0), (C2,))])])
    text = render_week(program([w]), MON)
    assert "220.5 lb" in text and "15.7 in" in text and "kg" not in text and "cm" not in text


def test_render_week_shows_session_notes():
    s = session("general lower-body accessory", 3, 10, None).model_copy(update={"notes": "Sumo deadlift, moderate load."})
    text = render_week(program([week(days=[day(MON, "lift", [s, session()])])]), MON)
    assert "      general lower-body accessory: Sumo deadlift, moderate load." in text
    assert "back squat: " not in text  # sessions without notes add no line


def test_render_week_full_has_links():
    text = render_week(program(), MON, full=True, sources=SOURCES)
    assert "[Synth Channel – Squat Basics @ 01:35](https://www.youtube.com/watch?v=vidAAAAAAAA&t=95s)" in text
    assert "ⓘ sources" not in text


def test_render_outline_lists_months():
    lines = render_outline(program()).splitlines()
    assert lines[0].startswith("Month 1 · ") and "volume" in lines[0] and len(lines) == 2


def pending(changes, status="awaiting_approval", **kw):
    return RunResult(thread_id="t1", status=status, proposal={"summary": "Cut squat volume for weeks 2-4."},
                     changes=changes, **kw)


def test_render_proposal_athlete_is_short():
    v1 = program()
    second = MON + timedelta(days=7)
    changed = week(second)
    for d in changed.days:
        d.sessions[0] = session(sets=4, reps=3)
    v2 = merge_proposal(v1, proposal(kind="roll_forward", with_outline=False, weeks=[changed]), profile(), NOW)
    changes = diff_programs(v1, v2)
    assert len(changes) == 3
    text = render_proposal(pending(changes))
    assert len(text.splitlines()) <= 8
    assert text.startswith("What changes:") and "Why: Cut squat volume for weeks 2-4." in text
    assert "back squat 5×6 @ 70% → 4×3 @ 70%" in text and "weeks[" not in text


def test_render_proposal_full_lists_failures_and_paths():
    failures = [{"check": "fidelity", "path": "weeks[2026-11-02]", "reason": "sets 8 outside 4-5"}]
    text = render_proposal(pending([], status="failed", failures=failures), full=True)
    assert "[fidelity] weeks[2026-11-02]: sets 8 outside 4-5" in text
    athlete = render_proposal(pending([], status="failed", failures=failures))
    assert "couldn't" in athlete.lower() and "[fidelity]" not in athlete


def test_render_proposal_status_messages():
    assert "plan profile" in render_proposal(pending([], status="needs_profile"))
    assert "version 3" in render_proposal(pending([], status="saved", version=3))
    assert "changed" in render_proposal(pending([], status="stale")).lower()


def test_week_rows_one_row_per_session_without_chunk_ids():
    from tests.planner_fixtures import MON, week
    from src.planner.render import week_rows
    rows = week_rows(week(MON))
    assert rows and set(rows[0]) == {"Day", "Type", "Exercise", "Sets×Reps", "Load", "Notes"}
    assert not any("@" in str(v) for r in rows for v in r.values())
