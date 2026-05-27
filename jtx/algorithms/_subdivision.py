"""Subdivision parser shared by triplet-aware algorithms.

A *subdivision* string names a regular grid relative to the quarter
note. Straight grids: ``"4"`` (quarters), ``"8"`` (8ths), ``"16"``
(16ths), ``"32"`` (32nds). Triplet grids: ``"4t"`` (quarter triplets =
3 notes per half), ``"8t"`` (8th triplets = 3 notes per quarter),
``"16t"`` (16th triplets = 3 per 8th), ``"32t"`` (32nd triplets = 3
per 16th).

The parser returns the tick spacing between successive positions and
the number of positions per bar at the active PPQ + meter. Algorithms
loop ``range(positions_per_bar)`` and place events at ``i * spacing``.

PPQ=480 (the engine default) divides every supported subdivision
cleanly into integer ticks; ``ValueError`` is raised when the
combination produces a fractional spacing so the algorithm fails fast
rather than emitting drifting events.
"""

from __future__ import annotations

# (numerator, denominator) over ticks per quarter — spacing = ppq * num/den.
# Quarter = ppq * 1/1; 8th = ppq * 1/2; 8th-triplet = ppq * 1/3; etc.
_SUBDIVISIONS: dict[str, tuple[int, int]] = {
    "2": (2, 1),  # half notes
    "4": (1, 1),  # quarters
    "8": (1, 2),  # 8ths
    "16": (1, 4),  # 16ths
    "32": (1, 8),  # 32nds
    "2t": (4, 3),  # half-note triplets (three per double-whole; in 4/4 = 3 per 2 bars)
    "4t": (2, 3),  # quarter triplets (three per half)
    "8t": (1, 3),  # 8th triplets (three per quarter)
    "16t": (1, 6),  # 16th triplets (three per 8th)
    "32t": (1, 12),  # 32nd triplets (three per 16th)
}

SUBDIVISION_CHOICES: tuple[str, ...] = tuple(_SUBDIVISIONS.keys())


def subdivision_grid(subdivision: str, ticks_per_bar: int, ppq: int) -> tuple[int, int]:
    """Return ``(spacing_ticks, positions_per_bar)`` for *subdivision*.

    Raises ``ValueError`` if the subdivision is unknown or the PPQ +
    meter combination doesn't produce integer-tick spacing.
    """
    if subdivision not in _SUBDIVISIONS:
        raise ValueError(
            f"unknown subdivision {subdivision!r} (expected one of {SUBDIVISION_CHOICES})"
        )
    num, den = _SUBDIVISIONS[subdivision]
    if (ppq * num) % den != 0:
        raise ValueError(
            f"subdivision {subdivision!r} not integer-tick at ppq={ppq}: spacing = ppq*{num}/{den}"
        )
    spacing = (ppq * num) // den
    if ticks_per_bar % spacing != 0:
        raise ValueError(
            f"subdivision {subdivision!r} spacing {spacing} does not divide bar {ticks_per_bar}"
        )
    return spacing, ticks_per_bar // spacing


def is_triplet(subdivision: str) -> bool:
    return subdivision.endswith("t")
