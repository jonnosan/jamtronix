"""compose() produces a fully-populated Song conforming to FIXED_PALETTE."""

from __future__ import annotations

import dataclasses

import pytest

from jtx.composer import (
    FIXED_PALETTE,
    FORMAT_SPECS,
    MOOD_ANCHORS,
    FormatType,
    compose,
    validate_palette,
)
from jtx.composer.mood import MoodSpec
from jtx.composer.voices import UTILITY_VOICES
from jtx.model import validate_song


def test_compose_euphoric_song_has_full_palette() -> None:
    song = compose("Test", "iac", MOOD_ANCHORS["euphoric"], "song", chaos=0.0)
    voice_names = set(song.voices.keys())
    assert set(FIXED_PALETTE).issubset(voice_names)
    assert set(UTILITY_VOICES).issubset(voice_names)
    # Validator agrees on palette conformance.
    assert validate_palette(song) == []


@pytest.mark.parametrize("anchor_name", sorted(MOOD_ANCHORS.keys()))
@pytest.mark.parametrize("fmt", sorted(FORMAT_SPECS.keys()))
def test_compose_passes_validate_song(anchor_name: str, fmt: FormatType) -> None:
    """Every anchor × format combination yields a structurally valid Song."""
    mood = MOOD_ANCHORS[anchor_name]
    song = compose(f"{anchor_name}-{fmt}", "iac", mood, fmt, chaos=0.3)
    errors = validate_song(song)
    assert errors == [], errors

    # Every part has its intensity envelope set.
    for name, part in song.parts.items():
        assert 0.0 <= part.intensity_start <= 1.0, name
        assert 0.0 <= part.intensity_end <= 1.0, name
    # Tempo within recipe-ish bounds (60..180).
    assert 60 <= song.tempo <= 180


def test_compose_loop_format_marks_part_as_loop() -> None:
    song = compose("Hold", "iac", MOOD_ANCHORS["dreamy"], "loop", chaos=0.0)
    assert len(song.parts) == 1
    only_part = next(iter(song.parts.values()))
    assert only_part.loop is True


def test_compose_sting_format_is_short_and_single_part() -> None:
    song = compose("Bump", "iac", MOOD_ANCHORS["happy"], "sting", chaos=0.0)
    assert len(song.parts) == 1
    total_bars = sum(p.bars for p in song.parts.values())
    assert 4 <= total_bars <= 8


def test_compose_chaos_clamped() -> None:
    """Chaos outside [0, 1] is clamped rather than raising."""
    a = compose("X", "iac", MOOD_ANCHORS["happy"], "song", chaos=2.5)
    b = compose("X", "iac", MOOD_ANCHORS["happy"], "song", chaos=1.0)
    assert dataclasses.asdict(a) == dataclasses.asdict(b)


def test_compose_handles_off_axis_mood() -> None:
    """An arbitrary (valence, energy) point not at an anchor still composes."""
    song = compose(
        "Off-axis",
        "iac",
        MoodSpec(valence=0.1, energy=0.3, chaos=0.5),
        "ramp",
        chaos=0.5,
    )
    assert validate_song(song) == []
    assert validate_palette(song) == []
