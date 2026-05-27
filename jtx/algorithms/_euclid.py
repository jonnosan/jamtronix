"""Even-distribution rhythm helpers used by drum algorithms.

The function :func:`euclid` spreads ``pulses`` hits as evenly as possible
across ``steps`` slots. This is not strict Bjorklund (it uses the simpler
floor-increment approximation which produces the same patterns for the
small pulse/step counts a drum sequencer needs) — if a future user needs
the canonical Bjorklund neckaces, we can swap implementations without
changing the API.
"""

from __future__ import annotations


def euclid(pulses: int, steps: int, offset: int = 0) -> list[bool]:
    """Distribute *pulses* hits evenly across *steps* slots.

    Returns a ``list[bool]`` of length ``steps``. Out-of-range pulses
    are clamped: ``pulses <= 0`` returns all-False, ``pulses >= steps``
    returns all-True. The *offset* rotates the pattern right by that
    many steps (so ``offset=4`` puts the first hit on step 4).
    """
    if steps <= 0:
        return []
    if pulses <= 0:
        return [False] * steps
    if pulses >= steps:
        return [True] * steps

    pattern = [False] * steps
    last_bucket = -1
    for i in range(steps):
        bucket = (i * pulses) // steps
        if bucket != last_bucket:
            pattern[i] = True
            last_bucket = bucket

    if offset:
        offset %= steps
        if offset:
            pattern = pattern[-offset:] + pattern[:-offset]
    return pattern
