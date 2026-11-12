"""The code checks on a candidate program (spec §7). Synthetic template and program."""

from datetime import datetime, timedelta

import pytest

from src.planner.checks import run_checks
from src.planner.merge import merge_proposal
from src.planner.schema import Deviation, GateResult, TendonTrack
from src.planner.templates import Template
from tests.planner_fixtures import C, C2, MON, day, profile, proposal, session, template_dict, week

TODAY = MON - timedelta(days=1)
NOW = datetime(2026, 11, 1, 9, 0)
RETRIEVED = {C, C2}


def tendon_template() -> Template:
    data = template_dict()
    data.update(id="synth_tendon", kind="tendon_track", end=None, week_kinds={})
    data["elastic_exercises"] = ["depth drop", "box jump"]
    data["cycles"] = [
        {"id": f"stage{i}", "name": f"Stage {i}", "emphasis": "tendon", "goal": "g", "weeks": None,
         "entry_criteria": "e", "exit_criteria": "x", "primes_next": None, "allowed_jumping": allowed, "cites": [C],
         "day_types": [{"id": "elastic", "label": "Elastic", "cites": [C]}, {"id": "hsr", "label": "HSR", "cites": [C]},
                       {"id": "iso_only", "label": "Isometrics only", "cites": [C]}],
         "prescriptions": [{"day_type": "elastic", "exercise": ex, "equipment": ["box"], "sets": None,
                            "reps": {"min": 10, "max": 20}, "intensity": None, "rest": None, "notes": None,
                            "cites": [C]} for ex in ("depth drop", "box jump")]}
        for i, allowed in ((1, ["depth drop"]), (2, ["depth drop", "box jump"]))]
    data["scheduling"] = {"pattern": ["elastic", "hsr"], "hard_day_types": ["elastic", "hsr"],
                          "min_days_between_hard": 2, "allowed_back_to_back": [["elastic", "hsr"]],
                          "missed_sessions": "skip", "cites": [C]}
    return Template.model_validate(data)


TEMPLATES = {"synth_macro": Template.model_validate(template_dict()), "synth_tendon": tendon_template()}


def candidate(weeks=None, **outline_overrides):
    prop = proposal(weeks=weeks)
    for k, v in outline_overrides.items():
        setattr(prop.replace_outline.macrocycle if k == "event_date" else prop.replace_outline, k, v)
    return merge_proposal(None, prop, profile(), NOW)


def check(program, previous=None, gates=(), retrieved=RETRIEVED, who=None, today=TODAY):
    return run_checks(program, previous=previous, profile=who or profile(), templates=TEMPLATES,
                      retrieved_ids=set(retrieved), gates=list(gates), today=today)


def kinds(failures):
    return [f.check for f in failures]


def test_clean_program_has_no_failures():
    assert check(candidate()) == []


def test_provenance_flags_unretrieved_cite():
    failures = check(candidate(), retrieved={C})
    assert failures and set(kinds(failures)) == {"provenance"} and C2 in failures[0].reason


def test_provenance_only_checks_changed_items():
    v1 = candidate()
    v2 = merge_proposal(v1, proposal(kind="roll_forward", with_outline=False, weeks=[week(MON + timedelta(days=14))]),
                        profile(), NOW)
    assert check(v2, previous=v1, retrieved={C}) == []   # C2 is only on the unchanged outline


def test_coverage_requires_cites_and_deviation_reason():
    w = week()
    w.days[0].sessions[0] = session(cites=())
    assert "coverage" in kinds(check(candidate(weeks=[w])))
    w = week()
    w.days[0].sessions[0] = session(sets=8, deviation=Deviation(reason="", cites=[]))
    assert "coverage" in kinds(check(candidate(weeks=[w])))


def test_fidelity_passes_within_range_and_unit_tolerance():
    w = week(days=[day(MON, "lift"), day(MON + timedelta(days=2), "jump",
                                         [session("depth jump", 3, 5, ("in", 16.0), (C2,))])])
    assert check(candidate(weeks=[w])) == []


def test_fidelity_fails_out_of_range_without_deviation():
    w = week(days=[day(MON, "jump", [session("depth jump", 3, 5, ("in", 24.0), (C2,))])])
    failures = check(candidate(weeks=[w]))
    assert kinds(failures) == ["fidelity"] and "intensity" in failures[0].reason
    w.days[0].sessions[0].deviation = Deviation(reason="Higher box for an advanced athlete", cites=[C2])
    assert check(candidate(weeks=[w])) == []


def test_fidelity_unknown_exercise_needs_deviation():
    w = week(days=[day(MON, "lift", [session("front squat")])])
    assert kinds(check(candidate(weeks=[w]))) == ["fidelity"]
    w.days[0].sessions[0].deviation = Deviation(reason="no rack", cites=[], requested_by_user=True)
    assert check(candidate(weeks=[w])) == []


def test_calendar_rejects_gap_overlap_and_past_days():
    program = candidate()
    program.mesocycles[1].start += timedelta(days=1)          # gap between mesocycles
    assert "calendar" in kinds(check(program))
    assert "calendar" in kinds(check(candidate(), today=MON + timedelta(days=1)))   # Review Focus 4


def test_calendar_follows_available_days_not_fixed_weekdays():
    tue = MON + timedelta(days=1)
    tts = [tue, tue + timedelta(days=2), tue + timedelta(days=4)]   # Tue, Thu, Sat
    who = profile(available_days=["tue", "thu", "sat"], days_per_week=3)
    assert check(candidate(weeks=[week(days=[day(d) for d in tts])]), who=who) == []
    failures = check(candidate(weeks=[week(days=[day(MON), day(tue)])]))
    assert kinds(failures) == ["calendar"] and "min_days_between_hard" in failures[0].reason
    assert "calendar" in kinds(check(candidate(weeks=[week(days=[day(d) for d in tts])])))  # Thu/Sat not available


def test_calendar_allows_template_back_to_back_pair():
    program = candidate(weeks=[week(days=[day(MON, "elastic", [session("depth drop", None, 10, None)]),
                                          day(MON + timedelta(days=1), "hsr", [])])])
    program.tendon_track = TendonTrack(template_id="synth_tendon", stage_id="stage1", entered_on=MON,
                                       gate_to_next="x", allowed_jumping=["depth drop"], cites=[C])
    assert check(program) == []


def test_calendar_does_not_count_isometrics_only_tendon_days():
    # Daily isometrics on top of one elastic + heavy-slow pair: 7 days for a 3-day athlete, Thu-Sun not available.
    iso = [day(MON + timedelta(days=i), "iso_only", []) for i in range(2, 7)]
    program = candidate(weeks=[week(days=[day(MON, "elastic", [session("depth drop", None, 10, None)]),
                                          day(MON + timedelta(days=1), "hsr", []), *iso])])
    program.tendon_track = TendonTrack(template_id="synth_tendon", stage_id="stage1", entered_on=MON,
                                       gate_to_next="x", allowed_jumping=["depth drop"], cites=[C])
    assert check(program, who=profile(days_per_week=3)) == []
    program.weeks[0].days[3].day_type = "elastic"   # Thu: spacing is fine, but a hard tendon day still counts
    failures = check(program, who=profile(days_per_week=2))
    assert {f.reason for f in failures} == {"3 training days > 2 per week", "thu is not an available day"}


def test_calendar_event_needs_taper_and_min_loading():
    soon = MON + timedelta(days=41)    # 6 weeks out: plan doesn't end on it, and < 6 loading weeks + taper
    failures = check(candidate(event_date=soon))
    assert kinds(failures) == ["calendar", "calendar"]
    event = MON + timedelta(days=55)   # last mesocycle ends on it; enough loading
    program = candidate(event_date=event)
    program.macrocycle.start -= timedelta(weeks=8)
    program.weeks.append(week(MON + timedelta(days=42), mesocycle_index=1))   # inside the 14-day taper window
    failures = check(program)
    assert any("taper" in f.reason for f in failures)


def test_week_kinds_volume_range():
    assert "week_kinds" in kinds(check(candidate(weeks=[week(kind="unload", volume=0.9)])))
    assert check(candidate(weeks=[week(kind="unload", volume=0.65)])) == []


def test_gates_block_progress_on_hold():
    program = candidate(weeks=[week(days=[day(MON, "elastic", [session("depth drop", None, 10, None)])])])
    program.tendon_track = TendonTrack(template_id="synth_tendon", stage_id="stage2", entered_on=MON,
                                       gate_to_next="x", allowed_jumping=["depth drop", "box jump"], cites=[C])
    hold = GateResult(track="tendon", decision="hold", rule_id="g1", inputs={"stage_id": "stage1"}, cites=[C])
    assert "gates" in kinds(check(program, gates=[hold]))
    progress = hold.model_copy(update={"decision": "progress"})
    assert check(program, gates=[progress]) == []


def test_gates_limit_jumping_to_the_stage():
    program = candidate(weeks=[week(days=[day(MON, "elastic", [session("box jump", None, 10, None)])])])
    program.tendon_track = TendonTrack(template_id="synth_tendon", stage_id="stage1", entered_on=MON,
                                       gate_to_next="x", allowed_jumping=["depth drop"], cites=[C])
    assert "gates" in kinds(check(program))


def test_gates_use_the_template_list_not_the_planners():
    program = candidate(weeks=[week(days=[day(MON, "elastic", [session("box jump", None, 10, None)])])])
    program.tendon_track = TendonTrack(template_id="synth_tendon", stage_id="stage1", entered_on=MON,
                                       gate_to_next="x", allowed_jumping=["depth drop", "box jump"], cites=[C])
    assert "gates" in kinds(check(program))   # stage1 in the template allows only depth drop


@pytest.mark.parametrize("template_id, stage_id", [("typo_tendon", "stage1"), ("synth_tendon", "stage9")])
def test_gates_fail_on_unknown_tendon_template_or_stage(template_id, stage_id):
    program = candidate()
    program.tendon_track = TendonTrack(template_id=template_id, stage_id=stage_id, entered_on=MON,
                                       gate_to_next="x", allowed_jumping=[], cites=[C])
    assert "gates" in kinds(check(program))


def test_equipment_missing_fails():
    failures = check(candidate(), who=profile(equipment=["box"]))
    assert set(kinds(failures)) == {"equipment"} and "barbell" in failures[0].reason


def swapped(name, equipment=()):
    return session(name, deviation=Deviation(reason="same job, found by search", cites=[C], equipment=list(equipment)))


def test_equipment_is_checked_for_a_deviated_exercise():
    w = week(days=[day(MON, "lift", [swapped("trap bar deadlift", ["trap bar"])])])
    failures = check(candidate(weeks=[w]))
    assert kinds(failures) == ["equipment"] and "trap bar" in failures[0].reason
    w.days[0].sessions[0] = swapped("trap bar deadlift", ["barbell"])
    assert check(candidate(weeks=[w])) == []


def test_at_most_two_swapped_exercises_per_week():
    names = ["trap bar deadlift", "split squat", "calf raise"]
    w = week(days=[day(MON + timedelta(days=2 * i), "lift", [swapped(n)]) for i, n in enumerate(names)])
    failures = check(candidate(weeks=[w]))
    assert kinds(failures) == ["fidelity"] and "swapped" in failures[0].reason
    w = week(days=[day(MON + timedelta(days=2 * i), "lift", [swapped(n)]) for i, n in enumerate(names[:2] * 2)][:3])
    assert check(candidate(weeks=[w])) == []   # the same two exercises on three days still count as two


def slot_templates():
    data = template_dict()
    slot = {"day_type": "lift", "exercise": "lower-body accessory", "equipment": [], "sets": {"min": 2, "max": 5},
            "reps": {"min": 8, "max": 12}, "intensity": None, "rest": None, "notes": None, "cites": [C],
            "options": [{"exercise": "RDL", "equipment": ["barbell"], "cites": [C]},
                        {"exercise": "leg curl", "equipment": ["curl machine"], "cites": [C]}]}
    data["cycles"][0]["prescriptions"].append(slot)
    return {"synth_macro": Template.model_validate(data), "synth_tendon": TEMPLATES["synth_tendon"]}


def check_slots(program, who=None):
    return run_checks(program, previous=None, profile=who or profile(), templates=slot_templates(),
                      retrieved_ids=RETRIEVED, gates=[], today=TODAY)


def test_slot_option_needs_no_deviation_and_uses_its_own_equipment():
    w = week(days=[day(MON, "lift", [session("RDL", 3, 10, None)])])
    assert check_slots(candidate(weeks=[w])) == []
    w.days[0].sessions[0] = session("leg curl", 3, 10, None)
    failures = check_slots(candidate(weeks=[w]))
    assert kinds(failures) == ["equipment"] and "curl machine" in failures[0].reason
    w.days[0].sessions[0] = session("RDL", 9, 10, None)           # the slot's sets range still applies
    assert kinds(check_slots(candidate(weeks=[w]))) == ["fidelity"]


def test_approved_sessions_in_a_changed_week_are_not_rejudged():
    old = session("core circuit")                                       # outside the template, already approved
    before = candidate(weeks=[week(days=[day(MON, "lift", [old])])])
    assert kinds(check(before)) == ["fidelity"]                         # a new plan would fail it
    edited = candidate(weeks=[week(days=[day(MON, "lift", [old]), day(MON + timedelta(days=2), "lift", [session()])])])
    assert check(edited, previous=before) == []                         # an edit elsewhere in the week doesn't
    edited.weeks[0].days[0].sessions[0] = session("core circuit", 3, 10, None)
    assert kinds(check(edited, previous=before)) == ["fidelity"]        # but touching it brings it back under the checks
