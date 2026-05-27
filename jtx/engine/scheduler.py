"""Bar-by-bar regeneration loop — the heart of the engine.

The scheduler holds a :class:`ClockSource` and a :class:`Sink` and
walks an arrangement bar-by-bar. For each bar it asks a
:data:`BarGenerator` callable to produce the events for that bar,
sorts them by tick, then dispatches them through the sink at the
right absolute tick.

The lookahead happens between bars: bar N+1 is generated *immediately
after* bar N's final event has been dispatched. This means knob tweaks
during bar N's playback land in bar N+1, satisfying the spec's "~1 bar
latency" commitment without ever rendering a whole part up-front. There
is no whole-part render path in jtx — bar-by-bar is the only mode.

For v1 the scheduler is single-threaded: ``run`` blocks while playing.
A future GUI integration will run it on a worker thread and surface
``stop`` via a flag.
"""

from __future__ import annotations

from collections.abc import Callable

from jtx.engine.clock_source import ClockSource
from jtx.engine.events import Event
from jtx.engine.sink import Sink

BarGenerator = Callable[[int], list[Event]]
"""Given a 0-based bar index, return the events for that bar.

Tick fields on the returned events are *relative to bar start* — the
scheduler adds the absolute tick offset before dispatch.
"""


class Scheduler:
    """Walks an arrangement bar-by-bar, dispatching events to a sink."""

    def __init__(self, clock: ClockSource, sink: Sink) -> None:
        self.clock = clock
        self.sink = sink
        self._stopping = False

    def request_stop(self) -> None:
        """Ask :meth:`run` to bail at the next bar boundary."""
        self._stopping = True

    def run(
        self,
        bar_count: int,
        ticks_per_bar: int,
        bar_generator: BarGenerator,
    ) -> None:
        """Play ``bar_count`` bars, calling *bar_generator* for each.

        Lookahead model: the next bar's events are generated *after*
        the previous bar's last event has dispatched. Knob changes that
        land during bar N's playback are therefore visible to bar N+1's
        generator call, giving the ~1-bar response latency the spec
        commits to.
        """
        if bar_count <= 0:
            return

        self._stopping = False
        self.clock.start()
        self.sink.start()
        try:
            events = bar_generator(0)
            for bar_idx in range(bar_count):
                # Sort events for this bar by relative tick, then by
                # event type for stable ordering between bars sharing
                # the same tick value (e.g. NoteOff then NoteOn at the
                # same step — keep the off first to avoid stuck notes).
                events.sort(key=_sort_key)
                bar_start = bar_idx * ticks_per_bar
                for ev in events:
                    self.clock.wait_until(bar_start + ev.tick)
                    self.sink.emit(ev)
                if self._stopping:
                    return
                if bar_idx + 1 < bar_count:
                    # Generate the next bar *now*, after this bar's
                    # last event has dispatched — captures any knob
                    # tweaks that landed during this bar.
                    events = bar_generator(bar_idx + 1)
        finally:
            self.sink.stop()
            self.clock.stop()


# NoteOff before NoteOn at the same tick prevents a stuck note when
# the off and on belong to the same pitch on the same channel — the
# scheduler doesn't know whether they do, but ordering off-first is
# always safe (the off either lands on a held note and releases it,
# or lands on nothing and is harmless).
_KIND_ORDER = {
    "NoteOff": 0,
    "ControlChange": 1,
    "PitchBend": 1,
    "NoteOn": 2,
}


def _sort_key(event: Event) -> tuple[int, int]:
    return event.tick, _KIND_ORDER.get(type(event).__name__, 3)
