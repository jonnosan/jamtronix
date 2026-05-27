"""Tests for the RootProvider ABC + ProgressionRootProvider default."""

from __future__ import annotations

import pytest

from jtx.engine.root_provider import (
    ProgressionRootProvider,
    degree_to_semitones,
)
from jtx.model.song import ChordProgression, Key

# A minor scale: 0, 2, 3, 5, 7, 8, 10.
_A_MINOR = (0, 2, 3, 5, 7, 8, 10)
# A major scale: 0, 2, 4, 5, 7, 9, 11.
_A_MAJOR = (0, 2, 4, 5, 7, 9, 11)


# ------------------------------------------------------ degree parser


def test_degree_diatonic_minor() -> None:
    assert degree_to_semitones("i", _A_MINOR) == 0
    assert degree_to_semitones("VI", _A_MINOR) == 8
    assert degree_to_semitones("III", _A_MINOR) == 3
    assert degree_to_semitones("VII", _A_MINOR) == 10
    assert degree_to_semitones("iv", _A_MINOR) == 5
    assert degree_to_semitones("v", _A_MINOR) == 7


def test_degree_diatonic_major() -> None:
    assert degree_to_semitones("I", _A_MAJOR) == 0
    assert degree_to_semitones("IV", _A_MAJOR) == 5
    assert degree_to_semitones("V", _A_MAJOR) == 7
    assert degree_to_semitones("vi", _A_MAJOR) == 9


def test_degree_flat_lowers_by_semitone() -> None:
    # bIII in major would be 3 (vs diatonic III = 4).
    assert degree_to_semitones("bIII", _A_MAJOR) == 3


def test_degree_sharp_raises_by_semitone() -> None:
    # #IV in major = 6 (the tritone).
    assert degree_to_semitones("#IV", _A_MAJOR) == 6


def test_degree_strips_quality_markers() -> None:
    assert degree_to_semitones("V7", _A_MINOR) == 7
    assert degree_to_semitones("ii°", _A_MAJOR) == 2
    assert degree_to_semitones("Imaj7", _A_MAJOR) == 0
    assert degree_to_semitones("Vsus4", _A_MINOR) == 7


def test_degree_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown chord degree"):
        degree_to_semitones("VIII", _A_MAJOR)
    with pytest.raises(ValueError, match="empty"):
        degree_to_semitones("", _A_MAJOR)


# --------------------------------------------- ProgressionRootProvider


def test_progression_provider_with_no_progression_returns_zero() -> None:
    p = ProgressionRootProvider(Key(tonic="A", scale="minor"), None)
    assert p.root_semitones_for_bar(0) == 0
    assert p.root_semitones_for_bar(7) == 0


def test_progression_provider_with_empty_degrees_returns_zero() -> None:
    p = ProgressionRootProvider(
        Key(tonic="A", scale="minor"),
        ChordProgression(degrees=[], bars_per_chord=4),
    )
    assert p.root_semitones_for_bar(0) == 0


def test_progression_provider_cycles_through_degrees() -> None:
    p = ProgressionRootProvider(
        Key(tonic="A", scale="minor"),
        ChordProgression(degrees=["i", "VI", "III", "VII"], bars_per_chord=4),
    )
    # bars 0..3 = i, 4..7 = VI, 8..11 = III, 12..15 = VII, 16..19 = i (wrap).
    assert p.root_semitones_for_bar(0) == 0  # i
    assert p.root_semitones_for_bar(3) == 0  # still i
    assert p.root_semitones_for_bar(4) == 8  # VI = +8
    assert p.root_semitones_for_bar(8) == 3  # III = +3
    assert p.root_semitones_for_bar(12) == 10  # VII = +10
    assert p.root_semitones_for_bar(16) == 0  # wraps to i


def test_progression_provider_bars_per_chord_one_changes_every_bar() -> None:
    p = ProgressionRootProvider(
        Key(tonic="A", scale="minor"),
        ChordProgression(degrees=["i", "iv", "V", "i"], bars_per_chord=1),
    )
    assert p.root_semitones_for_bar(0) == 0  # i
    assert p.root_semitones_for_bar(1) == 5  # iv
    assert p.root_semitones_for_bar(2) == 7  # V
    assert p.root_semitones_for_bar(3) == 0  # i


def test_progression_provider_major_scale() -> None:
    p = ProgressionRootProvider(
        Key(tonic="A", scale="major"),
        ChordProgression(degrees=["I", "V", "vi", "IV"], bars_per_chord=2),
    )
    # A major scale: 0, 2, 4, 5, 7, 9, 11.
    assert p.root_semitones_for_bar(0) == 0  # I
    assert p.root_semitones_for_bar(2) == 7  # V
    assert p.root_semitones_for_bar(4) == 9  # vi
    assert p.root_semitones_for_bar(6) == 5  # IV
