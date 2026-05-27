"""Meter parsing + tick arithmetic."""

from __future__ import annotations

import pytest

from jtx.engine.meter import parse_meter, ticks_per_bar, ticks_per_beat


def test_parse_meter_common() -> None:
    assert parse_meter("4/4") == (4, 4)
    assert parse_meter("3/4") == (3, 4)
    assert parse_meter("7/8") == (7, 8)
    assert parse_meter("12/8") == (12, 8)


def test_parse_meter_rejects_garbage() -> None:
    for bad in ["4", "4/4/4", "x/4", "4/y", "0/4", "4/0", "-4/4"]:
        with pytest.raises(ValueError):
            parse_meter(bad)


def test_ticks_per_bar_4_4() -> None:
    # 4/4 at PPQ 480: a quarter note = 480 ticks, bar = 4 quarters = 1920.
    assert ticks_per_bar("4/4", 480) == 1920


def test_ticks_per_bar_other_meters() -> None:
    assert ticks_per_bar("3/4", 480) == 1440
    assert ticks_per_bar("7/8", 480) == 4 * 480 * 7 // 8  # = 1680
    assert ticks_per_bar("12/8", 480) == 2880


def test_ticks_per_beat() -> None:
    # In N/D, one beat is a 1/D note = whole_note / D ticks.
    assert ticks_per_beat("4/4", 480) == 480
    assert ticks_per_beat("7/8", 480) == 240
    assert ticks_per_beat("3/4", 480) == 480
