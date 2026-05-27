"""Pitch-contour curves for ``motif_phrase``.

A contour takes:
- the number of firing positions in the motif
- the palette (tuple of allowed scale degrees, e.g. ``(0, 2, 4, 5, 7)``)
- a starting palette index
- the phrase RNG (for any per-contour randomness)

…and returns one scale-degree pick per position. Contours encode
recognisable shapes (``arc``, ``acid_zig``) so the motif sounds
*intentional* rather than random-walk.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable

CONTOUR_NAMES: tuple[str, ...] = (
    "pulse",
    "up",
    "down",
    "arc",
    "valley",
    "jagged",
    "psy_climb",
    "acid_zig",
)
"""Choice list (excluding the ``auto`` sentinel handled by the algorithm)."""


def apply_contour(
    name: str,
    positions: int,
    palette: tuple[int, ...] | list[int],
    start_index: int,
    rng: random.Random,
) -> tuple[int, ...]:
    """Generate ``positions`` scale-degree picks for *name*.

    Unknown names fall through to ``pulse`` rather than crashing —
    keeps a typo from blowing up playback.
    """
    if positions <= 0 or not palette:
        return ()
    fn = _CONTOURS.get(name, _pulse)
    return fn(positions, tuple(palette), start_index, rng)


def pick_contour(
    knob_value: str,
    motif_complexity: float,
    rng: random.Random,
) -> str:
    """Resolve the ``contour`` knob, mapping ``"auto"`` to a complexity-weighted pick."""
    if knob_value in _CONTOUR_BY_NAME:
        return knob_value
    # auto / unknown → sample weighted by closeness to motif_complexity.
    sigma = 0.3
    weights = [math.exp(-(((c - motif_complexity) / sigma) ** 2)) for c in _CONTOUR_COMPLEXITY]
    total = sum(weights)
    if total <= 0:
        return "pulse"
    roll = rng.random() * total
    acc = 0.0
    for name, w in zip(CONTOUR_NAMES, weights, strict=True):
        acc += w
        if roll < acc:
            return name
    return CONTOUR_NAMES[-1]


def _pulse(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    degree = palette[start % len(palette)]
    return tuple(degree for _ in range(positions))


def _up(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    return tuple(palette[(start + i) % len(palette)] for i in range(positions))


def _down(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    return tuple(palette[(start - i) % len(palette)] for i in range(positions))


def _arc(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    if positions == 1:
        return (palette[start % len(palette)],)
    half = positions // 2
    rising = [palette[(start + i) % len(palette)] for i in range(half + 1)]
    falling = [palette[(start + half - i) % len(palette)] for i in range(1, positions - half)]
    return tuple(rising + falling)


def _valley(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    if positions == 1:
        return (palette[start % len(palette)],)
    half = positions // 2
    falling = [palette[(start - i) % len(palette)] for i in range(half + 1)]
    rising = [palette[(start - half + i) % len(palette)] for i in range(1, positions - half)]
    return tuple(falling + rising)


def _jagged(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    out: list[int] = []
    direction = 1
    idx = start
    for _ in range(positions):
        out.append(palette[idx % len(palette)])
        idx = idx + direction
        direction = -direction
        if direction == 1:
            idx += 1  # net upward drift so the line doesn't loop on itself
    return tuple(out)


def _psy_climb(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    # Anchor root then climb the palette. Anchor every 4th note.
    out: list[int] = []
    for i in range(positions):
        if i % 4 == 0:
            out.append(palette[start % len(palette)])
        else:
            out.append(palette[(start + i) % len(palette)])
    return tuple(out)


def _acid_zig(
    positions: int,
    palette: tuple[int, ...],
    start: int,
    _rng: random.Random,
) -> tuple[int, ...]:
    # Classic TB-303 zig-zag: a, a+1, a, a+2, a, a+1, …
    out: list[int] = []
    pattern = (0, 1, 0, 2)
    for i in range(positions):
        out.append(palette[(start + pattern[i % 4]) % len(palette)])
    return tuple(out)


_CONTOURS: dict[str, Callable[..., tuple[int, ...]]] = {
    "pulse": _pulse,
    "up": _up,
    "down": _down,
    "arc": _arc,
    "valley": _valley,
    "jagged": _jagged,
    "psy_climb": _psy_climb,
    "acid_zig": _acid_zig,
}
_CONTOUR_BY_NAME = set(_CONTOURS.keys())

# Complexity scores parallel to CONTOUR_NAMES (used by auto selection).
_CONTOUR_COMPLEXITY: tuple[float, ...] = (
    0.05,  # pulse
    0.25,  # up
    0.25,  # down
    0.45,  # arc
    0.50,  # valley
    0.80,  # jagged
    0.65,  # psy_climb
    0.75,  # acid_zig
)
