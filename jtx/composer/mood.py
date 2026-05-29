"""Mood = (valence, energy, chaos) on the [-1, 1] plane plus a chaos scalar.

Valence runs sad↔happy on the X axis; energy runs calm↔intense on the
Y axis. The 7 named anchors below are the snap targets exposed by the
Composer view's mood pad (PR 4).

Chaos is independent of position on the pad and influences how widely
the composer perturbs picks around the recipe's centre (knob ranges,
algorithm shortlists, weird-pick probability). Anchors default to
``chaos=0.0``; the Composer view's chaos slider supplies the actual
value at generate time.
"""

from __future__ import annotations

from dataclasses import dataclass


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


MOOD_ANCHORS: dict[str, MoodSpec] = {
    "happy": MoodSpec(valence=0.6, energy=0.4),
    "sad": MoodSpec(valence=-0.6, energy=-0.4),
    "scared": MoodSpec(valence=-0.4, energy=0.5),
    "angry": MoodSpec(valence=0.2, energy=0.85),
    "dreamy": MoodSpec(valence=0.2, energy=-0.5),
    "euphoric": MoodSpec(valence=0.85, energy=0.85),
    "brooding": MoodSpec(valence=-0.5, energy=-0.1),
}
"""Seven canonical mood targets on the valence × energy plane."""


__all__ = ["MOOD_ANCHORS", "MoodSpec"]
