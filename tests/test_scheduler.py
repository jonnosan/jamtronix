"""Scheduler dispatch + bar-by-bar lookahead semantics.

Uses a fake clock so tests don't actually wait — we only care that the
scheduler asked the right ticks in the right order. A small helper
``WaitOnlyClock`` records each ``wait_until`` call and immediately
returns; ``now_tick`` is unused by the scheduler today.
"""

from __future__ import annotations

from jtx.engine.clock_source import ClockSource
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn
from jtx.engine.scheduler import Scheduler
from jtx.engine.sink import MemorySink


class WaitOnlyClock(ClockSource):
    """Records the ticks the scheduler waits for, never actually sleeps."""

    ppq = 480

    def __init__(self) -> None:
        self.waited_ticks: list[int] = []
        self.started = False
        self.stopped = False

    def tempo_bpm(self) -> float:
        return 120.0

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def now_tick(self) -> int:
        return 0

    def wait_until(self, target_tick: int) -> None:
        self.waited_ticks.append(target_tick)


def test_scheduler_zero_bars_is_noop() -> None:
    clock, sink = WaitOnlyClock(), MemorySink()
    Scheduler(clock, sink).run(0, 1920, lambda _bar: [])
    assert sink.events == []
    assert clock.waited_ticks == []


def test_scheduler_dispatches_events_in_tick_order() -> None:
    clock, sink = WaitOnlyClock(), MemorySink()

    def gen(bar: int) -> list[Event]:
        if bar == 0:
            # Deliberately out of order to prove the scheduler sorts.
            return [
                NoteOn(tick=480, channel=1, note=60, velocity=100),
                NoteOff(tick=240, channel=1, note=50),
                NoteOn(tick=0, channel=1, note=50, velocity=80),
            ]
        return []

    Scheduler(clock, sink).run(1, 1920, gen)

    ticks_emitted = [e.tick for e in sink.events]
    assert ticks_emitted == [0, 240, 480]
    assert clock.waited_ticks == [0, 240, 480]


def test_scheduler_adds_bar_offset_to_wait_ticks() -> None:
    clock, sink = WaitOnlyClock(), MemorySink()

    def gen(bar: int) -> list[Event]:
        return [NoteOn(tick=0, channel=1, note=60 + bar, velocity=100)]

    Scheduler(clock, sink).run(3, 1920, gen)

    # Three bars × one event at relative tick 0 → waits at 0, 1920, 3840.
    assert clock.waited_ticks == [0, 1920, 3840]
    assert [e.note for e in sink.events] == [60, 61, 62]


def test_scheduler_sorts_noteoff_before_noteon_at_same_tick() -> None:
    """NoteOff before NoteOn at the same tick prevents stuck notes."""
    clock, sink = WaitOnlyClock(), MemorySink()

    def gen(bar: int) -> list[Event]:
        return [
            NoteOn(tick=240, channel=1, note=60, velocity=100),
            NoteOff(tick=240, channel=1, note=60),
        ]

    Scheduler(clock, sink).run(1, 1920, gen)

    assert isinstance(sink.events[0], NoteOff)
    assert isinstance(sink.events[1], NoteOn)


def test_scheduler_lookahead_generates_after_previous_bars_last_event() -> None:
    """Bar N+1 must be generated *after* bar N's last event dispatches.

    That's what gives knob tweaks during bar N a chance to reach bar
    N+1's generator call — the spec's ~1-bar latency commitment.
    """
    clock = WaitOnlyClock()
    call_log: list[tuple[str, int]] = []

    def gen(bar: int) -> list[Event]:
        call_log.append(("gen", bar))
        return [
            NoteOn(tick=0, channel=1, note=60, velocity=100),
            NoteOn(tick=1000, channel=1, note=72, velocity=100),
        ]

    class LoggingSink(MemorySink):
        def emit(self, event: Event) -> None:
            call_log.append(("emit", event.tick))
            super().emit(event)

    sink2 = LoggingSink()
    Scheduler(clock, sink2).run(2, 1920, gen)

    # Expected ordering:
    #   gen(0)        — pre-loop kickoff
    #   emit(0)
    #   emit(1000)    — last event of bar 0
    #   gen(1)        — lookahead: AFTER bar 0's final emit
    #   emit(0)
    #   emit(1000)
    assert call_log == [
        ("gen", 0),
        ("emit", 0),
        ("emit", 1000),
        ("gen", 1),
        ("emit", 0),
        ("emit", 1000),
    ]


def test_scheduler_request_stop_bails_at_bar_boundary() -> None:
    clock, sink = WaitOnlyClock(), MemorySink()
    scheduler = Scheduler(clock, sink)

    def gen(bar: int) -> list[Event]:
        # On the first bar, ask the scheduler to stop.
        if bar == 0:
            scheduler.request_stop()
        return [NoteOn(tick=0, channel=1, note=60 + bar, velocity=100)]

    scheduler.run(5, 1920, gen)

    # Bar 0's events should still dispatch (stop is checked after the
    # current bar finishes), then the loop bails.
    assert [e.note for e in sink.events] == [60]


def test_scheduler_handles_control_change_events() -> None:
    clock, sink = WaitOnlyClock(), MemorySink()

    def gen(_bar: int) -> list[Event]:
        return [
            ControlChange(tick=0, channel=2, cc=74, value=64),
            ControlChange(tick=480, channel=2, cc=74, value=100),
        ]

    Scheduler(clock, sink).run(1, 1920, gen)
    assert len(sink.events) == 2
    assert all(isinstance(e, ControlChange) for e in sink.events)


def test_scheduler_starts_and_stops_clock_and_sink() -> None:
    clock, sink = WaitOnlyClock(), MemorySink()
    Scheduler(clock, sink).run(1, 1920, lambda _b: [])
    assert clock.started
    assert clock.stopped
