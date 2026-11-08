import pytest

from src.tools import jump_height
from src.units import Quantity, convert, display


def test_convert_and_display():
    assert convert(Quantity(value=40, unit="cm"), "in").value == pytest.approx(15.748, abs=1e-3)
    assert convert(Quantity(value=100, unit="kg"), "lb").value == pytest.approx(220.462, abs=1e-3)
    assert display(Quantity(value=40, unit="cm")) == "15.7 in"
    assert display(Quantity(value=225, unit="lb")) == "225 lb"
    assert display(Quantity(value=80, unit="%")) == "80%"
    with pytest.raises(ValueError):
        convert(Quantity(value=1, unit="lb"), "in")


def test_jump_height_reports_inches():
    out = jump_height.invoke({"flight_time_s": 0.52})
    assert out == {"cm": 33.16, "in": 13.06}


def test_data_paths_under_thp_data_dir(monkeypatch, tmp_path):
    from src.kb.paths import athlete_dir, templates_dir
    monkeypatch.setenv("THP_DATA_DIR", str(tmp_path))
    assert templates_dir() == tmp_path.resolve() / "templates"
    assert athlete_dir() == tmp_path.resolve() / "athlete"
