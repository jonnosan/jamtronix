"""Step-grid math for drum + step-sequenced algorithms.

A *step* is a 16th note. ``step_ticks(ppq)`` returns the tick width of
one step at the active PPQ; ``steps_per_bar(ticks_per_bar, ppq)`` gives
the count for a bar of the active meter.
"""

from __future__ import annotations


def step_ticks(ppq: int) -> int:
    """Ticks per 16th note. PPQ must be divisible by 4."""
    if ppq % 4 != 0:
        raise ValueError(f"PPQ {ppq} must be divisible by 4 to land 16ths on integers")
    return ppq // 4


def steps_per_bar(ticks_per_bar_value: int, ppq: int) -> int:
    """16th-note steps in one bar at this PPQ and meter."""
    s = step_ticks(ppq)
    if ticks_per_bar_value % s != 0:
        raise ValueError(f"ticks_per_bar {ticks_per_bar_value} not divisible by step_ticks {s}")
    return ticks_per_bar_value // s
