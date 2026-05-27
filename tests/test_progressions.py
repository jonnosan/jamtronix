"""Tests for the chord-progression family helper."""

from __future__ import annotations

from jtx_gui.progressions import (
    FAMILIES,
    degrees_for,
    lookup,
    rotate,
    rotation_count,
)


def test_rotate_zero_returns_input() -> None:
    assert rotate(("i", "VII", "VI", "V"), 0) == ["i", "VII", "VI", "V"]


def test_rotate_one_shifts_left() -> None:
    assert rotate(("i", "VII", "VI", "V"), 1) == ["VII", "VI", "V", "i"]


def test_rotate_wraps_past_length() -> None:
    assert rotate(("i", "VII"), 3) == rotate(("i", "VII"), 1)


def test_degrees_for_known_family() -> None:
    assert degrees_for("andalusian", 0) == ["i", "VII", "VI", "V"]


def test_degrees_for_static() -> None:
    assert degrees_for("static", 0) == ["i"]


def test_degrees_for_unknown_falls_back_to_static() -> None:
    assert degrees_for("bogus", 0) == ["i"]


def test_lookup_finds_known_family_at_rotation_zero() -> None:
    assert lookup(["i", "VII", "VI", "V"]) == ("andalusian", 0)


def test_lookup_finds_rotated_family() -> None:
    assert lookup(["VII", "VI", "V", "i"]) == ("andalusian", 1)


def test_lookup_returns_none_for_unknown() -> None:
    assert lookup(["i", "II", "iii", "IV"]) is None


def test_lookup_empty_returns_none() -> None:
    assert lookup([]) is None


def test_rotation_count_matches_family_length() -> None:
    for fname, base in FAMILIES.items():
        assert rotation_count(fname) == len(base)


def test_rotation_count_unknown_is_one() -> None:
    assert rotation_count("bogus") == 1
