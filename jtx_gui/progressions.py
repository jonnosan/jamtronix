"""Named chord-progression families for the Song view.

Replaces the free-text Roman-numeral input with a 'family + rotation'
pair of knobs. Each named family lists its degrees in canonical order;
the rotation knob picks which slot starts the bar.

The actual model field stays as ``ChordProgression.degrees`` (list of
Roman-numeral strings) — family + rotation is purely a UI shortcut
that regenerates the list on each change. Reverse lookup (degrees →
family + rotation) lets the GUI restore the picker state when loading
a song.
"""

from __future__ import annotations

from typing import Final

# Family name → canonical degree list, in starting order.
# Picked to span common minor + major jam styles. All are 3–4 chords
# so the rotation knob has a meaningful (small) range.
FAMILIES: Final[dict[str, tuple[str, ...]]] = {
    "static": ("i",),
    "andalusian": ("i", "VII", "VI", "V"),  # flamenco / phrygian descent
    "andante": ("i", "VI", "III", "VII"),  # Phuture-style minor
    "minor_descent": ("i", "VII", "VI", "VII"),  # descent + return
    "dark_circle": ("i", "v", "III", "VII"),  # moody minor
    "tonic_subdom": ("i", "iv", "V", "i"),  # classic minor cadence
    "phrygian_pull": ("i", "II", "i", "VII"),  # phrygian half-step pull
    "axis": ("I", "V", "vi", "IV"),  # 'Don't Stop Believin'
    "pop_circle": ("vi", "IV", "I", "V"),  # pop ballad turnaround
    "doo_wop": ("I", "vi", "IV", "V"),  # 50s changes
    "blues": ("I", "I", "IV", "V"),  # 12-bar blues compressed to 4
}

FAMILY_CHOICES: Final[tuple[str, ...]] = tuple(FAMILIES.keys())


def rotate(degrees: tuple[str, ...], rotation: int) -> list[str]:
    """Return ``degrees`` rotated so position ``rotation`` becomes first."""
    if not degrees:
        return []
    r = rotation % len(degrees)
    return list(degrees[r:]) + list(degrees[:r])


def degrees_for(family: str, rotation: int) -> list[str]:
    """Resolve (family, rotation) → degree list for the song model."""
    base = FAMILIES.get(family, FAMILIES["static"])
    return rotate(base, rotation)


def lookup(degrees: list[str]) -> tuple[str, int] | None:
    """Reverse lookup: which (family, rotation) produces these degrees?

    Returns the first match found, or None if no family generates this
    sequence at any rotation. The GUI uses this to restore the picker
    state when opening an existing song.
    """
    target = tuple(degrees)
    if not target:
        return None
    for family, base in FAMILIES.items():
        if len(base) != len(target):
            continue
        for r in range(len(base)):
            if tuple(rotate(base, r)) == target:
                return (family, r)
    return None


def rotation_count(family: str) -> int:
    """How many distinct rotations exist for ``family``."""
    return max(1, len(FAMILIES.get(family, FAMILIES["static"])))
