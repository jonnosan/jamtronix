"""Composer-shared types that need to live below :mod:`jtx.composer`.

:class:`MoodSpec`, :data:`FormatType`, :data:`FIXED_PALETTE`, and
:data:`UTILITY_VOICES` are referenced by both :mod:`jtx.composer` and
:mod:`jtx.model` (`Song.mood` / `Song.format`, palette validation).
They live in :mod:`jtx.model` to keep the composer→model import edge
one-directional — putting them in :mod:`jtx.composer` would cycle.

:mod:`jtx.composer.mood`, :mod:`jtx.composer.format`, and
:mod:`jtx.composer.voices` re-export these names so the composer-facing
import surface stays unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FormatType = Literal["sting", "jingle", "loop", "ramp", "song", "anthem"]
"""Format literal accepted by :func:`jtx.composer.compose` and stored on
:attr:`jtx.model.Song.format`."""


@dataclass(frozen=True)
class MoodSpec:
    """Point on the mood pad plus a chaos amount.

    ``valence`` and ``energy`` are both in ``[-1, 1]``; ``chaos`` is in
    ``[0, 1]``. The composer clamps out-of-range values silently — the
    GUI is the source of truth for range enforcement.
    """

    valence: float
    energy: float
    chaos: float = 0.0


FIXED_PALETTE: tuple[str, ...] = (
    "drumkit",
    "bass",
    "sub",
    "lead",
    "pad",
    "chord",
    "arp",
    "stabs",
    "fx",
)
"""The 9 musical voices every composer song carries.

Note ``chord`` is singular (matches the ``Role`` literal in
:mod:`jtx.model.types`); ``stabs`` is plural to disambiguate from the
existing ``stab`` role.
"""

UTILITY_VOICES: tuple[str, ...] = ("filter", "root_ref", "chord_ref")
"""Modulator + follower voices wired by every composer song.

* ``filter`` — modulator broadcasting CC74-style cutoff sweeps.
* ``root_ref`` — follower mirroring the bass voice's root pitch so
  downstream MIDI devices can latch to the song's harmonic state.
* ``chord_ref`` — follower mirroring the chord voice for the same.
"""


__all__ = [
    "FIXED_PALETTE",
    "UTILITY_VOICES",
    "FormatType",
    "MoodSpec",
]
