"""Chord quality presets — name → tuple of semitone intervals.

Used by ``sustained_chord``, ``chord_stab``, ``arp`` and
``voice_follower``. Replaces the older free-form ``intervals`` list
on those algorithms with a single ``quality`` choice knob.
"""

from __future__ import annotations

from typing import Final

QUALITY_INTERVALS: Final[dict[str, tuple[int, ...]]] = {
    "unison": (0,),
    "power": (0, 7),
    "minor": (0, 3, 7),
    "major": (0, 4, 7),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "min7": (0, 3, 7, 10),
    "maj7": (0, 4, 7, 11),
    "dom7": (0, 4, 7, 10),
    "min9": (0, 3, 7, 10, 14),
    "add9": (0, 4, 7, 14),
}

QUALITY_CHOICES: Final[tuple[str, ...]] = tuple(QUALITY_INTERVALS.keys())


def intervals_for(quality: str) -> tuple[int, ...]:
    """Return the semitone intervals for ``quality``, defaulting to ``minor``."""
    return QUALITY_INTERVALS.get(quality, QUALITY_INTERVALS["minor"])
