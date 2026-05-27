"""Scale-degree palettes for ``melodic_line``.

Each palette is a tuple of scale degrees the line will draw from
(0 = root, 7 = root one octave up, etc.). Named presets cover the
common melodic shapes; the user picks one via the ``palette`` knob.
"""

from __future__ import annotations

from typing import Final

PALETTES: Final[dict[str, tuple[int, ...]]] = {
    "triad": (0, 2, 4),  # 1-3-5
    "tones_only": (0, 2, 4, 5, 7),  # chord-tone safe set
    "pentatonic": (0, 2, 4, 5, 7),  # major/minor pentatonic shape
    "full": (0, 1, 2, 3, 4, 5, 6),  # every scale degree
    "passing_only": (1, 3, 6),  # non-chord tones
    "high": (4, 5, 7, 9, 11),  # weighted toward upper register
    "low": (-3, -1, 0, 2, 4),  # weighted toward lower register
}

PALETTE_CHOICES: Final[tuple[str, ...]] = tuple(PALETTES.keys())


def palette_for(name: str) -> tuple[int, ...]:
    """Return the scale-degree tuple for ``name``, defaulting to ``tones_only``."""
    return PALETTES.get(name, PALETTES["tones_only"])
