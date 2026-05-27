"""Meter parsing + tick arithmetic helpers.

The on-disk Song stores ``meter`` as a string (e.g. ``"4/4"``, ``"3/4"``,
``"7/8"``). The scheduler converts this to ticks-per-bar at the active
PPQ. PPQ is conventionally 480 (slackbeatz's choice) so 16th-note
resolution lands on integer ticks.
"""

from __future__ import annotations


def parse_meter(meter: str) -> tuple[int, int]:
    """Parse ``"N/D"`` into ``(numerator, denominator)`` ints.

    Raises ``ValueError`` if the string doesn't have exactly one ``/``
    or either side isn't a positive int.
    """
    parts = meter.split("/")
    if len(parts) != 2:
        raise ValueError(f"meter {meter!r}: expected 'N/D'")
    num, den = (int(p) for p in parts)
    if num <= 0 or den <= 0:
        raise ValueError(f"meter {meter!r}: numerator and denominator must be > 0")
    return num, den


def ticks_per_bar(meter: str, ppq: int) -> int:
    """Total tick count for one bar of *meter* at *ppq* ticks-per-quarter.

    A whole note is ``4 * ppq`` ticks. One beat in ``N/D`` time is a
    ``1/D``-note long, i.e. ``(4 * ppq) // D`` ticks; a bar is N beats.
    """
    num, den = parse_meter(meter)
    whole_note = 4 * ppq
    if whole_note % den != 0:
        raise ValueError(
            f"meter {meter!r} at PPQ {ppq}: 1/{den} not representable in integer ticks"
        )
    return num * (whole_note // den)


def ticks_per_beat(meter: str, ppq: int) -> int:
    """Ticks per single beat in this meter at this PPQ."""
    _, den = parse_meter(meter)
    whole_note = 4 * ppq
    if whole_note % den != 0:
        raise ValueError(
            f"meter {meter!r} at PPQ {ppq}: 1/{den} not representable in integer ticks"
        )
    return whole_note // den
