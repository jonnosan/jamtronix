"""Rhythm template library for ``motif_phrase``.

Each template defines the *fire positions* within one beat as fractions
in ``[0, 1)`` plus a gate multiplier and a complexity score. ``motif_phrase``
stacks the template across the motif's beats and resolves fractional
positions to ticks at runtime.

The library is intentionally a curated set — adding templates is the way
to grow the algorithm. ``auto`` selection picks a template weighted by
``motif_complexity`` (lower complexity → simpler templates).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RhythmTemplate:
    """One rhythmic cell (defined per beat; stacks across motif beats)."""

    name: str
    positions: tuple[float, ...]
    """Fire positions within one beat, expressed as fractions in [0, 1)."""

    duration_mult: float
    """Gate multiplier — multiplied against ``gate * position_spacing``.
    >1 gives long sustained notes (``tied_long``); 1 is the natural fit."""

    complexity: float
    """Auto-selection weight (0 simple → 1 dense / syncopated)."""

    accents: tuple[bool, ...] | None = None
    """Optional per-position accent flag; ``None`` = no template-level accents."""


# Standard library. Order doesn't matter for selection (we pick by name or
# by complexity weighting), but kept roughly low→high here for readability.
_LIBRARY: tuple[RhythmTemplate, ...] = (
    RhythmTemplate("quarter", (0.0,), duration_mult=1.0, complexity=0.05),
    RhythmTemplate("tied_long", (0.0,), duration_mult=2.5, complexity=0.10),
    RhythmTemplate("eighth_eighth", (0.0, 0.5), duration_mult=1.0, complexity=0.20),
    RhythmTemplate(
        "gallop",
        (0.0, 0.5, 0.75),
        duration_mult=1.0,
        complexity=0.45,
        accents=(True, False, False),
    ),
    RhythmTemplate(
        "anacrusis",
        (0.25, 0.5, 0.75),
        duration_mult=1.0,
        complexity=0.55,
        accents=(False, False, True),
    ),
    RhythmTemplate(
        "syncopated",
        (0.0, 0.375, 0.75),
        duration_mult=1.0,
        complexity=0.70,
        accents=(False, True, False),
    ),
    RhythmTemplate(
        "triplet_run",
        (0.0, 1.0 / 3.0, 2.0 / 3.0),
        duration_mult=1.0,
        complexity=0.65,
    ),
    RhythmTemplate(
        "triplet_burst_last_beat",
        (1.0 / 3.0, 2.0 / 3.0),
        duration_mult=1.0,
        complexity=0.80,
        accents=(False, True),
    ),
)

TEMPLATE_NAMES: tuple[str, ...] = tuple(t.name for t in _LIBRARY)
"""Choice list (excluding the ``auto`` sentinel handled by the algorithm)."""

_BY_NAME: dict[str, RhythmTemplate] = {t.name: t for t in _LIBRARY}


def pick_template(
    knob_value: str,
    motif_complexity: float,
    rng: random.Random,
) -> RhythmTemplate:
    """Resolve the ``rhythm_template`` knob.

    ``"auto"`` weights the library by closeness to ``motif_complexity``
    (Gaussian falloff) and samples; any explicit name returns directly.
    Unknown explicit names fall through to ``auto`` so a typo doesn't
    crash playback.
    """
    if knob_value in _BY_NAME:
        return _BY_NAME[knob_value]
    # auto / unknown → sample weighted by motif_complexity.
    # sigma=0.25 means the bulk of the weight sits within ±0.5 of target.
    sigma = 0.25
    weights = [math.exp(-(((t.complexity - motif_complexity) / sigma) ** 2)) for t in _LIBRARY]
    return _weighted_choice(_LIBRARY, weights, rng)


def min_position_spacing(template: RhythmTemplate, ppq: int) -> int:
    """Smallest tick gap between consecutive fire positions in one beat.

    Used by ``motif_phrase`` to derive the per-note gate. For single-hit
    templates we fall back to one beat (ppq) — gate is then relative to a
    beat, not a sub-beat.
    """
    if len(template.positions) <= 1:
        return ppq
    sorted_positions = sorted(template.positions)
    gaps = [b - a for a, b in zip(sorted_positions, sorted_positions[1:], strict=False)]
    # Wrap-around gap into the next beat's first position.
    gaps.append((sorted_positions[0] + 1.0) - sorted_positions[-1])
    min_frac = min(gaps)
    return max(1, int(round(min_frac * ppq)))


def _weighted_choice(
    items: tuple[RhythmTemplate, ...],
    weights: list[float],
    rng: random.Random,
) -> RhythmTemplate:
    total = sum(weights)
    if total <= 0:
        return items[0]
    roll = rng.random() * total
    acc = 0.0
    for item, w in zip(items, weights, strict=True):
        acc += w
        if roll < acc:
            return item
    return items[-1]
