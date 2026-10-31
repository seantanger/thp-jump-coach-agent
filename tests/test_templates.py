"""Template schema, loader and get_cycle. Synthetic templates only."""

import json

import pytest
from pydantic import ValidationError

from src.planner.templates import (find_prescription, get_cycle, list_templates, load_template,
                                   template_cites)
from tests.planner_fixtures import C, C2, template_dict, write_template


@pytest.fixture
def tdir(tmp_path, monkeypatch):
    d = tmp_path / "templates"
    monkeypatch.setattr("src.planner.templates.templates_dir", lambda: d)
    return d


def test_load_reviewed_template_round_trips(tdir):
    write_template(tdir)
    t = load_template("synth_macro")
    assert [c.id for c in t.cycles] == ["volume", "strength"]
    assert t.cycles[0].prescriptions[1].intensity.unit == "cm"
    assert t.end.min_loading_weeks == 6
    assert template_cites(t) == {C, C2}


def test_unreviewed_template_refused(tdir):
    write_template(tdir, template_dict(reviewed=False))
    with pytest.raises(PermissionError, match="not reviewed"):
        load_template("synth_macro")
    assert load_template("synth_macro", require_reviewed=False).id == "synth_macro"


def test_uncited_prescription_rejected(tdir):
    data = template_dict()
    data["cycles"][0]["prescriptions"][0]["cites"] = []
    write_template(tdir, data)
    with pytest.raises(ValidationError, match=r"cycles\[0\]\.prescriptions\[0\]"):
        load_template("synth_macro")


def test_range_min_le_max(tdir):
    data = template_dict()
    data["cycles"][0]["prescriptions"][0]["sets"] = {"min": 6, "max": 4}
    write_template(tdir, data)
    with pytest.raises(ValidationError, match="min"):
        load_template("synth_macro")


def test_find_prescription_case_insensitive(tdir):
    write_template(tdir)
    t = load_template("synth_macro")
    p = find_prescription(t, "volume", "lift", "Back  Squat ")
    assert p is not None and p.sets.max == 5
    assert find_prescription(t, "volume", "lift", "front squat") is None


def test_get_cycle_artifact_lists_cites(tdir):
    write_template(tdir)
    msg = get_cycle.invoke({"name": "get_cycle", "args": {"template_id": "synth_macro", "cycle_id": "strength"},
                            "id": "c1", "type": "tool_call"})
    assert msg.artifact["template_id"] == "synth_macro"
    assert msg.artifact["data"]["id"] == "strength"
    assert msg.artifact["cites"] == [C2]
    assert json.loads(msg.content) == json.loads(json.dumps(msg.artifact, default=str))
    whole = get_cycle.invoke({"name": "get_cycle", "args": {"template_id": "synth_macro"}, "id": "c2",
                              "type": "tool_call"})
    assert whole.artifact["cites"] == sorted({C, C2})


def test_list_templates_skips_unreviewed(tdir):
    write_template(tdir)
    other = template_dict(reviewed=False)
    other["id"] = "draft"
    write_template(tdir, other)
    assert list_templates() == ["synth_macro"]
