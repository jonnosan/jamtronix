"""Discoverable list of CC functions per algorithm.

The setup editor surfaces these as the function names you can remap on
a voice slot. They're derived from the algorithm classes' ``DEFAULT_CC``
class attribute so adding a new mappable CC to an algorithm is a
one-line change without touching the GUI.
"""

from __future__ import annotations

from jtx.algorithms import AcidBass, SubDrone

# Algorithm name → {function name: default CC number}.
# Algorithms not in this map have no CC mappings to override.
CC_FUNCTIONS: dict[str, dict[str, int]] = {
    AcidBass.name: dict(AcidBass.DEFAULT_CC),
    SubDrone.name: dict(SubDrone.DEFAULT_CC),
}


def functions_for(algorithm_name: str) -> dict[str, int]:
    """Return the default CC mapping for ``algorithm_name`` (empty if none)."""
    return dict(CC_FUNCTIONS.get(algorithm_name, {}))


def all_functions_used_by(*algorithm_names: str) -> dict[str, int]:
    """Union of CC functions across the named algorithms.

    Useful when a voice slot doesn't pin to one algorithm (an override
    may swap the algorithm per-part). The merged dict uses the *first*
    default seen for any duplicated function name.
    """
    merged: dict[str, int] = {}
    for name in algorithm_names:
        for func, default in CC_FUNCTIONS.get(name, {}).items():
            merged.setdefault(func, default)
    return merged
