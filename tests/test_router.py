import pytest

from src.router import route


@pytest.mark.parametrize("message", [
    "make me a plan", "Can you build my program?", "I can only train 3 days a week now",
    "my dunk contest is March 1", "what's on this week", "what do I do next week?",
    "Only 4 days this month", "Move me to the next mesocycle",
])
def test_route_program_examples(message):
    assert route(message) == "program"


@pytest.mark.parametrize("message", [
    "why do eccentrics help my vertical", "is static stretching bad before jumping",
    "how long should a taper be?", "Do isometrics help patellar tendon pain?", "What is RSI?",
    "explain what a deload is",
])
def test_route_coach_examples(message):
    assert route(message) == "coach"
