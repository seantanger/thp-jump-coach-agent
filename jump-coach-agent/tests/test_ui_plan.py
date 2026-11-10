"""UI Plan tab: new plan → proposal shown → approve → saved. Run API stubbed; no model calls."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from src.planner.merge import Change
from src.planner.run import RunResult

APP = str(Path(__file__).resolve().parents[1] / "ui/app.py")


@pytest.fixture
def ui(tmp_path, monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setattr("src.planner.store.athlete_dir", lambda: tmp_path / "athlete")
    pending = RunResult(thread_id="t1", status="awaiting_approval", proposal={"summary": "Six-month plan."},
                        changes=[Change(path="macrocycle", before=None, after={})], version=1)
    start, resume = Mock(return_value=pending), Mock(return_value=RunResult(thread_id="t1", status="saved", version=1))
    monkeypatch.setattr("src.planner.run.start", start)
    monkeypatch.setattr("src.planner.run.resume", resume)
    return testing.AppTest.from_file(APP), start, resume


def test_ui_plan_tab_new_plan_flow(ui):
    app, start, resume = ui
    app.run()
    app.button(key="plan_new").click().run()
    assert start.call_args.args[0] == "new"
    shown = " ".join(t.value for t in app.text)
    assert "What changes:" in shown and "New plan outline" in shown
    app.button(key="plan_approve").click().run()
    assert resume.call_args.args[:2] == ("t1", "approve")
    assert "Saved as version 1." in [s.value for s in app.success]
    assert not app.exception
