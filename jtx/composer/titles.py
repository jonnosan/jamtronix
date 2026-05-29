"""Mood-tagged title word pools + format-aware suffix.

The Composer view's 'Random title' button calls :func:`random_title` to
draw from a pool that matches the current mood anchor. Format adds a
short suffix for short-form outputs (sting / jingle / loop / ramp);
song / anthem get no suffix.

Pure function on ``(mood_name_or_spec, fmt, rng)``: same inputs always
return the same title when called with a seeded RNG.
"""

from __future__ import annotations

import random

from jtx.composer.format import FormatType
from jtx.composer.mood import MOOD_ANCHORS, MoodSpec

_MOOD_FIRST: dict[str, tuple[str, ...]] = {
    "happy": ("Sunny", "Glow", "Bright", "Bloom", "Pulse", "Magnet", "Lift"),
    "sad": ("Hollow", "Pale", "Ash", "Drift", "Faded", "Quiet", "Grey"),
    "scared": ("Mirror", "Wraith", "Static", "Cipher", "Hollow", "Shroud"),
    "angry": ("Burn", "Strike", "Hammer", "Steel", "Razor", "Fault"),
    "dreamy": ("Vapor", "Floating", "Velvet", "Soft", "Moss", "Lull"),
    "euphoric": ("Astral", "Solar", "Rapture", "Neon", "Halo", "Crystal"),
    "brooding": ("Shadow", "Iron", "Tide", "Smoke", "Deep", "Slate"),
}

_MOOD_SECOND: dict[str, tuple[str, ...]] = {
    "happy": ("Lines", "Garden", "Cycle", "Field", "Bloom", "Mirror"),
    "sad": ("Tide", "Field", "Letter", "Hour", "Window", "Drift"),
    "scared": ("Static", "Maze", "Storm", "Hollow", "Tower", "Loop"),
    "angry": ("Engine", "Tower", "Strike", "Storm", "Hammer", "Forge"),
    "dreamy": ("Drift", "Bloom", "Tide", "Garden", "Mirror", "Loop"),
    "euphoric": ("Rapture", "Cycle", "Field", "Storm", "Bloom", "Halo"),
    "brooding": ("Tower", "Engine", "Tide", "Field", "Mirror", "Static"),
}

_FORMAT_SUFFIX: dict[FormatType, str] = {
    "sting": "Strike",
    "jingle": "Hook",
    "loop": "Loop",
    "ramp": "Rise",
    "song": "",
    "anthem": "",
}


def format_suffix(fmt: FormatType) -> str:
    """Return the word appended to short-form titles (empty for song / anthem)."""
    return _FORMAT_SUFFIX[fmt]


def _nearest_anchor(mood: MoodSpec) -> str:
    """Pick the anchor name whose (valence, energy) is closest to *mood*."""
    best_name = ""
    best_distance = float("inf")
    for name, spec in MOOD_ANCHORS.items():
        dv = spec.valence - mood.valence
        de = spec.energy - mood.energy
        distance = dv * dv + de * de
        if distance < best_distance:
            best_distance = distance
            best_name = name
    return best_name


def random_title(mood: MoodSpec, fmt: FormatType, rng: random.Random | None = None) -> str:
    """Draw a title from the word pool for *mood*'s nearest anchor.

    ``rng`` lets callers seed for determinism (Composer's 'Random title'
    leaves it ``None`` for a fresh pick each click).
    """
    r = rng if rng is not None else random.Random()
    anchor = _nearest_anchor(mood)
    first = r.choice(_MOOD_FIRST[anchor])
    second = r.choice(_MOOD_SECOND[anchor])
    suffix = format_suffix(fmt)
    base = f"{first} {second}"
    return f"{base} {suffix}" if suffix else base


__all__ = ["format_suffix", "random_title"]
