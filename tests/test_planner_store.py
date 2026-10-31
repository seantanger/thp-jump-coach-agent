"""Profile / program / proposal schema, versioned store, merge and diff."""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from src.planner.merge import diff_programs, merge_proposal
from src.planner.schema import parse_proposal
from src.planner.store import (StaleProgramError, latest_version, load_profile, load_program, save_profile,
                               save_program)
from tests.planner_fixtures import MON, profile, proposal, session, week

NOW = datetime(2026, 11, 1, 9, 0)


def test_profile_round_trip(tmp_path):
    save_profile(profile(), tmp_path)
    assert load_profile(tmp_path) == profile()
    assert load_profile(tmp_path / "nowhere") is None


def test_profile_rejects_kg_lift_key():
    with pytest.raises(ValidationError, match="_lb"):
        profile(lifts={"back_squat_kg": 140.0})


def test_save_program_never_overwrites(tmp_path):
    v1 = merge_proposal(None, proposal(), profile(), NOW)
    save_program(v1, tmp_path)
    assert (tmp_path / "program" / "v0001.json").exists()
    with pytest.raises((FileExistsError, StaleProgramError)):
        save_program(v1, tmp_path)


def test_save_program_rejects_stale_version(tmp_path):
    v1 = merge_proposal(None, proposal(), profile(), NOW)
    v2 = merge_proposal(v1, proposal(kind="roll_forward", with_outline=False), profile(), NOW)
    with pytest.raises(StaleProgramError):
        save_program(v2, tmp_path)          # v1 was never saved
    save_program(v1, tmp_path)
    save_program(v2, tmp_path)
    other_v2 = merge_proposal(v1, proposal(kind="roll_forward", with_outline=False), profile(), NOW)
    with pytest.raises(StaleProgramError):
        save_program(other_v2, tmp_path)    # built on v1 after v2 was saved
    assert latest_version(tmp_path) == 2
    assert load_program(None, tmp_path) == v2 and load_program(1, tmp_path) == v1


def test_merge_new_then_roll_forward():
    v1 = merge_proposal(None, proposal(), profile(), NOW)
    assert v1.version == 1 and v1.based_on is None and len(v1.weeks) == 2
    replaced = week(MON + timedelta(days=7), days=[])
    appended = week(MON + timedelta(days=14))
    v2 = merge_proposal(v1, proposal(kind="roll_forward", with_outline=False, weeks=[appended, replaced]),
                        profile(), NOW)
    assert v2.version == 2 and v2.based_on == 1
    assert [w.start for w in v2.weeks] == [MON, MON + timedelta(days=7), MON + timedelta(days=14)]
    assert v2.weeks[1].days == [] and v2.mesocycles == v1.mesocycles


def test_merge_applies_profile_changes(tmp_path):
    save_profile(profile(), tmp_path)
    v1 = merge_proposal(None, proposal(profile_changes={"days_per_week": 3}), profile(), NOW)
    assert v1.profile_snapshot.days_per_week == 3
    assert load_profile(tmp_path).days_per_week == 4


def test_merge_rejects_new_without_outline_and_change_without_program():
    with pytest.raises(ValueError, match="outline"):
        merge_proposal(None, proposal(with_outline=False), profile(), NOW)
    with pytest.raises(ValueError, match="no current program"):
        merge_proposal(None, proposal(kind="roll_forward", with_outline=False), profile(), NOW)


def test_diff_reports_changed_session_and_mesocycle():
    v1 = merge_proposal(None, proposal(), profile(), NOW)
    second = MON + timedelta(days=7)
    changed = week(second)
    changed.days[1].sessions[0] = session(sets=4, reps=3)
    v2 = merge_proposal(v1, proposal(kind="roll_forward", with_outline=False, weeks=[changed]), profile(), NOW)
    v2.mesocycles[1].emphasis = "strength-speed"
    paths = [c.path for c in diff_programs(v1, v2)]
    assert paths == ["mesocycles[1].emphasis", f"weeks[{second}].days[{second + timedelta(days=2)}].sessions[0]"]
    assert [c.path for c in diff_programs(None, v1)][:2] == ["macrocycle", "mesocycles[0]"]


def test_parse_proposal_strips_fences_and_prose():
    raw = proposal().model_dump_json()
    assert parse_proposal(f"Here is the plan:\n```json\n{raw}\n```\nDone.") == proposal()


def test_parse_proposal_rejects_extra_keys():
    raw = proposal().model_dump_json()[:-1] + ', "bonus": 1}'
    with pytest.raises(ValidationError):
        parse_proposal(raw)
