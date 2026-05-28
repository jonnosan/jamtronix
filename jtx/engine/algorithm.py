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
from typing import ClassVar

from jtx.engine.context import BarContext
from jtx.engine.events import Event
from jtx.model.parameter_target import ParameterTarget


class Algorithm(ABC):
    """Per-voice MIDI generator."""

    DEFAULT_PARAM_MAP: ClassVar[dict[str, ParameterTarget]] = {}
    """Function-name → target fallback used by the sink-side parameter router.

    Algorithms that emit function-tagged events (``ControlChange`` /
    ``PitchBend`` / ``ChannelPressure`` with ``function="..."``) declare
    their natural target here. The router consults
    ``voice_slot.parameter_map`` first; if no per-voice override exists,
    it falls back to this dict. If neither has an entry, the event
    passes through unchanged.
    """

    @abstractmethod
    def generate_bar(self, ctx: BarContext) -> list[Event]:
        """Return the events for one bar.

        Each event's ``tick`` is **relative to the bar start** — i.e.
        in ``[0, ctx.ticks_per_bar)``. The scheduler adds
        ``ctx.tick_offset`` before dispatching so the resulting absolute
        tick lines up with the active :class:`ClockSource`.
        """
