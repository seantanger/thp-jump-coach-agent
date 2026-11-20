"""Training log: append-only store, the tools, and what the chat and Planner see."""

import json

import pytest
from langchain_core.messages import AIMessage

from src.coach.qa import answer_question, athlete_context
from src.planner.log import add_entry, load_log, log_workout, read_log, recent_log
from tests.test_graph import ScriptedChatModel
from tests.test_qa import fake_search  # noqa: F401 - fixture


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("THP_DATA_DIR", str(tmp_path))


def test_entries_are_appended_and_sorted_by_date():
    add_entry("2026-11-16", "squat 4x9 at 160", knee_pain=2)
    add_entry("2026-11-14", "15 max jumps")
    rows = load_log()
    assert [r["date"] for r in rows] == ["2026-11-14", "2026-11-16"] and rows[1]["knee_pain"] == 2


@pytest.mark.parametrize("day,pain", [("Saturday", None), ("2026-11-14", 11)])
def test_bad_entries_are_rejected(day, pain):
    with pytest.raises(ValueError):
        add_entry(day, "x", pain)
    assert load_log() == []


def test_the_same_entry_twice_is_stored_once():
    add_entry("2026-11-19", "core circuit, felt fine")
    add_entry("2026-11-19", "core circuit, felt fine ")
    assert len(load_log()) == 1


def test_recent_log_points_at_older_entries():
    for d in range(1, 13):
        add_entry(f"2026-11-{d:02d}", f"day {d}")
    out = recent_log(10)
    assert "day 12" in out and "day 3" in out and "day 2:" not in out and "2 earlier entries" in out


def test_tools_write_and_read_back():
    assert "Logged 2026-11-14" in log_workout.invoke({"day": "2026-11-14", "text": "knee ache after jumps", "knee_pain": 2})
    add_entry("2026-11-09", "clean 135")
    assert "2026-11-09" in read_log.invoke({}) and "knee 2/10" in read_log.invoke({})
    assert "2026-11-09" not in read_log.invoke({"since": "2026-11-10"})


def test_chat_context_includes_the_log():
    add_entry("2026-11-14", "slight knee ache after jumps", knee_pain=2)
    assert "slight knee ache after jumps (knee 2/10)" in athlete_context()


def test_chat_can_log_a_report(fake_search, tmp_path):  # noqa: F811
    call = AIMessage("", tool_calls=[{"name": "log_workout", "id": "1",
                                      "args": {"day": "2026-11-18", "text": "squat 4x9 at 160"}}])
    reply = dict(summary="Logged.", points=[], takeaway=None, safety_note=None, not_covered=False,
                 for_you="Noted your squat.")
    model = ScriptedChatModel(responses=[call, AIMessage(json.dumps(reply))])
    result = answer_question("I squatted 4x9 at 160", llm=model, trace_dir=tmp_path, athlete=True)
    assert load_log()[0]["text"] == "squat 4x9 at 160" and result["check"]["passed"]
    assert {"log_workout", "read_log"} <= set(model.bound_tools)
