import math

import pytest

from src.tools import G, jump_height, jump_height_cm


@pytest.mark.parametrize(
    "t, expected_cm",
    [(0.5, 30.66), (0.52, 33.16), (0.61, 45.63), (0.7, 60.09)],
)
def test_known_values(t, expected_cm):
    assert jump_height_cm(t) == pytest.approx(expected_cm, abs=0.01)


def test_matches_formula():
    t = 0.437
    assert jump_height_cm(t) == pytest.approx(G * t**2 / 8 * 100, abs=0.005)


def test_scales_with_square_of_time():
    assert jump_height_cm(0.6) / jump_height_cm(0.3) == pytest.approx(4, rel=1e-3)


@pytest.mark.parametrize("bad", [0, -0.3])
def test_rejects_non_positive(bad):
    with pytest.raises(ValueError, match="positive"):
        jump_height_cm(bad)


def test_rejects_milliseconds():
    with pytest.raises(ValueError, match="ms"):
        jump_height_cm(520)


def test_tool_invoke_and_schema():
    assert jump_height.name == "jump_height"
    assert jump_height.args["flight_time_s"]["type"] == "number"
    assert math.isclose(jump_height.invoke({"flight_time_s": 0.5}), 30.66, abs_tol=0.01)
