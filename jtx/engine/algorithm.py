"""Algorithm abstract base class.

Every generator type in :mod:`jtx.algorithms` subclasses :class:`Algorithm`
and implements :meth:`generate_bar` — given a :class:`BarContext`, return
the events for that bar.

Algorithms are stateless across bars in v1. Anything that needs to
remember (e.g. an arpeggiator's step position) gets re-derived from
``ctx.bar_index`` and ``ctx.rng``. This is what makes bar-by-bar regen
work cleanly: rewriting a bar is just calling ``generate_bar`` again.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from jtx.engine.context import BarContext
from jtx.engine.events import Event


class Algorithm(ABC):
    """Per-voice MIDI generator."""

    @abstractmethod
    def generate_bar(self, ctx: BarContext) -> list[Event]:
        """Return the events for one bar.

        Each event's ``tick`` is **relative to the bar start** — i.e.
        in ``[0, ctx.ticks_per_bar)``. The scheduler adds
        ``ctx.tick_offset`` before dispatching so the resulting absolute
        tick lines up with the active :class:`ClockSource`.
        """
