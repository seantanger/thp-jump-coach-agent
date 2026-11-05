"""Planner graph: tool caps, check retries, interrupt approval, versioned save. Scripted model only."""

import json
from datetime import timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.planner import run
from src.planner.merge import merge_proposal
from src.planner.render import render_proposal
from src.planner.store import latest_version, load_profile, save_profile, save_program
from tests.planner_fixtures import MON, profile, proposal, week, write_template
from tests.test_graph import ScriptedChatModel

TODAY = MON - timedelta(days=1)
CYCLE_CALL = {"name": "get_cycle", "args": {"template_id": "synth_macro"}, "id": "cyc"}


@pytest.fixture
def athlete(tmp_path, monkeypatch):
    """Temp template, athlete and trace dirs; in-memory checkpointer shared by start/resume; no search index."""
    write_template(tmp_path / "templates")
    monkeypatch.setattr("src.planner.templates.templates_dir", lambda: tmp_path / "templates")
    monkeypatch.setattr("src.planner.store.athlete_dir", lambda: tmp_path / "athlete")
    monkeypatch.setattr("src.planner.run.traces_dir", lambda: tmp_path / "traces")
    saver = InMemorySaver()
    monkeypatch.setattr("src.planner.run.checkpointer", lambda: saver)
    monkeypatch.setattr("src.tools.search", lambda query, k, method, mode: [])
    save_profile(profile())
    return tmp_path / "athlete"


def scripted(*answers):
    """get_cycle first, then each answer as the final message of one attempt (re-reading the template)."""
    responses = []
    for i, text in enumerate(answers):
        responses += [AIMessage("", tool_calls=[{**CYCLE_CALL, "id": f"cyc{i}"}]), AIMessage(text)]
    return ScriptedChatModel(responses=responses)


def good(**kw):
    return proposal(**kw).model_dump_json()


def test_new_plan_pauses_for_approval_then_saves_v1(athlete):
    model = scripted(good())
    result = run.start("new", llm=model, today=TODAY)
    assert result.status == "awaiting_approval" and result.version == 1
    assert result.changes and result.changes[0].path == "macrocycle"
    assert latest_version() == 0
    done = run.resume(result.thread_id, "approve", llm=model)
    assert done.status == "saved" and done.version == 1
    assert (athlete / "program" / "v0001.json").exists()


def test_reject_saves_nothing(athlete):
    model = scripted(good())
    result = run.start("new", llm=model, today=TODAY)
    assert run.resume(result.thread_id, "reject", llm=model).status == "rejected"
    assert latest_version() == 0


def test_revise_sends_comment_back_to_planner(athlete):
    model = scripted(good(), good(summary="Second try."))
    first = run.start("new", llm=model, today=TODAY)
    second = run.resume(first.thread_id, "revise", comment="Only three days a week please", llm=model)
    assert second.status == "awaiting_approval" and second.proposal["summary"] == "Second try."
    assert any("Only three days a week please" in m.content for m in model.seen[2] if isinstance(m, HumanMessage))


def test_check_failure_retries_at_most_twice(athlete):
    bad = json.loads(good())
    bad["replace_weeks"][0]["days"][0]["sessions"][0]["cites"] = ["madeUPmadeU@1#0"]
    model = scripted(*[json.dumps(bad)] * 3)
    result = run.start("new", llm=model, today=TODAY)
    assert result.status == "failed" and len(model.seen) == 6        # 3 attempts x (get_cycle + answer)
    assert any(f["check"] == "provenance" for f in result.failures)
    assert latest_version() == 0
    assert "madeUPmadeU@1#0" in model.seen[2][-1].content            # the failure reasons went back to the model


def test_malformed_output_counts_as_attempt(athlete):
    extra = good()[:-1] + ', "bonus": 1}'
    model = scripted(f"Sure! Here it is:\n```json\n{extra}\n```", f"```json\n{good()}\n```")
    result = run.start("new", llm=model, today=TODAY)
    assert result.status == "awaiting_approval"                       # second attempt parsed through the fences
    assert "schema" in model.seen[2][-1].content


def test_retry_keeps_what_was_read_earlier(athlete):
    bad = json.loads(good())
    bad["replace_weeks"][0]["volume_modifier"] = 0.5                # week_kinds failure
    model = ScriptedChatModel(responses=[AIMessage("", tool_calls=[CYCLE_CALL]), AIMessage(json.dumps(bad)),
                                         AIMessage(good())])          # fixed, without reading the template again
    assert run.start("new", llm=model, today=TODAY).status == "awaiting_approval"


def test_unknown_template_is_retried_not_a_crash(athlete):
    bad = json.loads(good())
    bad["replace_outline"]["macrocycle"]["template_id"] = "typo_macro"
    model = scripted(json.dumps(bad), good())
    assert run.start("new", llm=model, today=TODAY).status == "awaiting_approval"
    assert "typo_macro" in model.seen[2][-1].content


def test_decline_shows_the_reason_and_saves_nothing(athlete):
    declined = json.loads(good())
    declined.update(decision="decline", summary="I need your event date.", replace_outline=None, replace_weeks=None)
    model = scripted(json.dumps(declined))
    result = run.start("new", llm=model, today=TODAY)
    assert result.status == "declined" and len(model.seen) == 2       # no retries
    assert "I need your event date." in render_proposal(result)
    assert latest_version() == 0


def test_approved_profile_changes_are_saved(athlete):
    model = scripted(good(profile_changes={"days_per_week": 3}))
    pending = run.start("new", llm=model, today=TODAY)
    assert load_profile().days_per_week == 4                          # nothing changes before approval
    assert run.resume(pending.thread_id, "approve", llm=model).status == "saved"
    assert load_profile().days_per_week == 3


def test_planner_reads_the_template_method(athlete, monkeypatch):
    methods = []
    monkeypatch.setattr("src.tools.search", lambda query, k, method, mode: methods.append(method) or [])
    monkeypatch.setenv("RETRIEVAL_METHOD", "charsplit_350")
    search = {"name": "search_library", "args": {"query": "q"}, "id": "s"}
    model = ScriptedChatModel(responses=[AIMessage("", tool_calls=[search, CYCLE_CALL]), AIMessage(good())])
    run.start("new", llm=model, today=TODAY)
    assert methods == ["charsplit_matched"]


def test_plan_tool_caps(athlete):
    searches = [{"name": "search_library", "args": {"query": f"q{i}"}, "id": f"s{i}"} for i in range(8)]
    cycles = [{**CYCLE_CALL, "id": f"c{i}"} for i in range(7)]
    model = ScriptedChatModel(responses=[AIMessage("", tool_calls=searches + cycles), AIMessage(good())])
    run.start("new", llm=model, today=TODAY)
    tool_messages = [m for m in model.seen[1] if m.type == "tool"]
    assert [m.status for m in tool_messages[:8]] == ["success"] * 6 + ["error"] * 2
    assert sum(m.status == "success" for m in tool_messages) == 12   # 6 searches + 7 reads allowed per tool; 12 run
    assert tool_messages[-1].status == "error" and "12 tool calls" in tool_messages[-1].content


def test_needs_profile_without_calling_model(athlete):
    (athlete / "profile.json").unlink()
    model = scripted(good())
    assert run.start("new", llm=model, today=TODAY).status == "needs_profile"
    assert model.seen == []


def test_stale_approval_refused(athlete):
    v1 = merge_proposal(None, proposal(), profile(), run.now())
    save_program(v1)
    roll = proposal(kind="roll_forward", with_outline=False, weeks=[week(MON + timedelta(days=14))])
    model = scripted(roll.model_dump_json())
    pending = run.start("roll_forward", llm=model, today=TODAY)
    assert pending.status == "awaiting_approval" and pending.version == 2
    save_program(merge_proposal(v1, roll, profile(), run.now()))   # someone else saved v2 meanwhile
    assert run.resume(pending.thread_id, "approve", llm=model).status == "stale"
    assert latest_version() == 2


def test_context_passes_today_and_last_filled_week(athlete):
    save_program(merge_proposal(None, proposal(), profile(), run.now()))
    model = scripted(proposal(kind="roll_forward", with_outline=False,
                              weeks=[week(MON + timedelta(days=14))]).model_dump_json())
    run.start("roll_forward", llm=model, today=TODAY)
    context = model.seen[0][1].content
    assert f"Today: {TODAY}" in context and f"Last filled week starts {MON + timedelta(days=7)}" in context
