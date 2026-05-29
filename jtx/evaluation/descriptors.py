"""Pure descriptor functions over abstract-event streams.

Each descriptor reads either:

* a single voice's events (``list[AbstractEvent]``), or
* a parameter trajectory by name (filtered from the events).

All descriptors are deterministic and side-effect free. They return
``float`` so they compose cleanly with the scoring math in
:mod:`jtx.evaluation.scoring`.

Aggregation across multiple bars is the scorer's job — descriptors
operate on a single bar's events to keep the unit small.
"""

from __future__ import annotations

from collections.abc import Iterable

from jtx.model.events import AbstractEvent, Hit, Note, Param


def hit_count(events: Iterable[AbstractEvent]) -> int:
    """Number of ``Hit`` events in *events*."""
    return sum(1 for e in events if isinstance(e, Hit))


def note_count(events: Iterable[AbstractEvent]) -> int:
    """Number of ``Note`` events in *events*."""
    return sum(1 for e in events if isinstance(e, Note))


def onset_count(events: Iterable[AbstractEvent]) -> int:
    """Number of ``Hit`` + ``Note`` events (each counts once as an onset)."""
    return sum(1 for e in events if isinstance(e, (Hit, Note)))


def _velocities(events: Iterable[AbstractEvent]) -> list[int]:
    return [e.velocity for e in events if isinstance(e, (Hit, Note))]


def velocity_mean(events: Iterable[AbstractEvent]) -> float:
    vs = _velocities(events)
    if not vs:
        return 0.0
    return sum(vs) / len(vs)


def velocity_variance(events: Iterable[AbstractEvent]) -> float:
    """Population variance of Hit + Note velocities. Empty → 0.0."""
    vs = _velocities(events)
    if not vs:
        return 0.0
    mean = sum(vs) / len(vs)
    return sum((v - mean) ** 2 for v in vs) / len(vs)


def sixteenth_grid_coverage(
    events: Iterable[AbstractEvent], ticks_per_bar: int
) -> float:
    """Fraction of 16th-note slots in the bar that have at least one onset.

    Range ``[0, 1]``. Acid (16ths-heavy) lands near 1.0; sparse pad
    parts land near 0.0.
    """
    if ticks_per_bar <= 0:
        return 0.0
    slot_size = ticks_per_bar / 16
    slots: set[int] = set()
    for e in events:
        if isinstance(e, (Hit, Note)):
            slots.add(int(e.tick // slot_size))
    return min(1.0, len(slots) / 16.0)


def param_values(events: Iterable[AbstractEvent], name: str) -> list[float]:
    """Extract Param values for a given function name, time-ordered."""
    params = sorted(
        (e for e in events if isinstance(e, Param) and e.name == name),
        key=lambda p: p.tick,
    )
    return [p.value for p in params]


def param_count(events: Iterable[AbstractEvent], name: str) -> int:
    return sum(1 for e in events if isinstance(e, Param) and e.name == name)


def param_trajectory_variance(
    events: Iterable[AbstractEvent], name: str
) -> float:
    """Population variance of a Param's value sequence over the bar."""
    vs = param_values(events, name)
    if not vs:
        return 0.0
    mean = sum(vs) / len(vs)
    return sum((v - mean) ** 2 for v in vs) / len(vs)


def param_trajectory_range(
    events: Iterable[AbstractEvent], name: str
) -> float:
    """``max - min`` of a Param's value sequence. Empty → 0.0."""
    vs = param_values(events, name)
    if not vs:
        return 0.0
    return max(vs) - min(vs)


def voice_active(events: Iterable[AbstractEvent]) -> bool:
    """True iff the voice emitted any Hit, Note, Param, or PolyAftertouch."""
    for _ in events:
        return True
    return False


__all__ = [
    "hit_count",
    "note_count",
    "onset_count",
    "param_count",
    "param_trajectory_range",
    "param_trajectory_variance",
    "param_values",
    "sixteenth_grid_coverage",
    "velocity_mean",
    "velocity_variance",
    "voice_active",
]
