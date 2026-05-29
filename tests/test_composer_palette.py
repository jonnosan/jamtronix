"""validate_fixed_palette accepts composer output, rejects mismatches."""

from __future__ import annotations

from jtx.composer import MOOD_ANCHORS, compose
from jtx.model import (
    Key,
    Song,
    VoiceConfig,
    validate_fixed_palette,
)


def test_validate_fixed_palette_accepts_compose_output() -> None:
    song = compose("Sanity", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0)
    assert validate_fixed_palette(song) == []


def test_validate_fixed_palette_rejects_missing_voice() -> None:
    song = compose("Sanity", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0)
    del song.voices["lead"]
    errors = validate_fixed_palette(song)
    assert errors
    assert "missing voices" in errors[0]
    assert "'lead'" in errors[0]


def test_validate_fixed_palette_rejects_extra_voice() -> None:
    song = compose("Sanity", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0)
    song.voices["mystery"] = VoiceConfig(algorithm="rest")
    errors = validate_fixed_palette(song)
    assert errors
    assert "unexpected voice names" in errors[0]
    assert "'mystery'" in errors[0]


def test_validate_fixed_palette_rejects_empty_song() -> None:
    """A bare Song with no voices fails on every palette member."""
    song = Song(title="Empty", setup_ref="iac", key=Key(tonic="A"))
    errors = validate_fixed_palette(song)
    assert errors
    assert "missing voices" in errors[0]


def test_validate_fixed_palette_allows_utility_voices() -> None:
    """Utility voices (filter/root_ref/chord_ref) are not flagged as extras."""
    song = compose("Sanity", "iac", MOOD_ANCHORS["happy"], "song", chaos=0.0)
    # compose() already wires utility voices; validate should ignore them.
    assert "filter" in song.voices
    assert "root_ref" in song.voices
    assert "chord_ref" in song.voices
    assert validate_fixed_palette(song) == []
