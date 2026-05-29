"""Mood / format-aware title generation."""

from __future__ import annotations

import random

import pytest

from jtx.composer import MOOD_ANCHORS, FormatType, format_suffix, random_title
from jtx.composer.titles import _MOOD_FIRST, _MOOD_SECOND


@pytest.mark.parametrize("anchor_name", sorted(MOOD_ANCHORS.keys()))
def test_titles_draw_from_mood_pool(anchor_name: str) -> None:
    """A title for *anchor_name* uses words from that anchor's word pools."""
    mood = MOOD_ANCHORS[anchor_name]
    rng = random.Random(42)
    title = random_title(mood, "song", rng=rng)
    first, second = title.split(" ", 1)
    assert first in _MOOD_FIRST[anchor_name]
    assert second in _MOOD_SECOND[anchor_name]


@pytest.mark.parametrize("fmt", ["sting", "jingle", "loop", "ramp"])
def test_short_format_titles_get_suffix(fmt: FormatType) -> None:
    suffix = format_suffix(fmt)
    assert suffix
    title = random_title(MOOD_ANCHORS["happy"], fmt, rng=random.Random(0))
    assert title.endswith(suffix)


@pytest.mark.parametrize("fmt", ["song", "anthem"])
def test_long_format_titles_have_no_suffix(fmt: FormatType) -> None:
    assert format_suffix(fmt) == ""
    title = random_title(MOOD_ANCHORS["happy"], fmt, rng=random.Random(0))
    # No trailing single-word format tag.
    assert not title.endswith(" Strike")
    assert not title.endswith(" Loop")


def test_random_title_is_seedable() -> None:
    """Seeded RNG produces the same title across two calls."""
    a = random_title(MOOD_ANCHORS["happy"], "song", rng=random.Random(123))
    b = random_title(MOOD_ANCHORS["happy"], "song", rng=random.Random(123))
    assert a == b


def test_off_axis_mood_picks_nearest_anchor() -> None:
    """A point near 'euphoric' (high valence, high energy) picks euphoric pools."""
    from jtx.composer.mood import MoodSpec

    mood = MoodSpec(valence=0.8, energy=0.8, chaos=0.0)
    title = random_title(mood, "song", rng=random.Random(7))
    first = title.split(" ", 1)[0]
    assert first in _MOOD_FIRST["euphoric"]
