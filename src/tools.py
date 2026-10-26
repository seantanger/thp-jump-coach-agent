"""Tools the agents can call."""

from __future__ import annotations

from langchain_core.tools import tool

G = 9.81  # m/s^2


def jump_height_cm(flight_time_s: float) -> float:
    """Jump height from flight time: h = g * t^2 / 8, returned in cm."""
    if flight_time_s <= 0:
        raise ValueError("flight_time_s must be positive")
    if flight_time_s > 2.0:
        raise ValueError("flight_time_s looks wrong (> 2 s); pass seconds, not ms")
    return round(G * flight_time_s**2 / 8 * 100, 2)


@tool
def jump_height(flight_time_s: float) -> float:
    """Convert a vertical jump's flight time (air time) into jump height.

    Args:
        flight_time_s: Time in the air in SECONDS (convert ms to s first, e.g. 520 ms -> 0.52).

    Returns:
        Jump height in centimetres, from h = g * t^2 / 8.
    """
    return jump_height_cm(flight_time_s)


TOOLS = [jump_height]
