"""MidiClockSlaveClock + AbletonLinkClock stub.

InternalClock has its own test file (test_clock.py). This file covers
the two new clock sources from issue #6.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from jtx.engine.clock_source import AbletonLinkClock, MidiClockSlaveClock


class FakeMessage:
    """Stand-in for mido.Message — only `type` matters here."""

    def __init__(self, msg_type: str) -> None:
        self.type = msg_type


class FakeInputPort:
    """Captures the callback so tests can fire messages on demand."""

    def __init__(self, callback: Callable[[Any], None]) -> None:
        self.callback = callback
        self.closed = False

    def fire(self, msg_type: str) -> None:
        self.callback(FakeMessage(msg_type))

    def close(self) -> None:
        self.closed = True


def _make_slave(ppq: int = 480) -> tuple[MidiClockSlaveClock, FakeInputPort]:
    holder: list[FakeInputPort] = []

    def factory(_name: str, callback: Callable[[Any], None]) -> Any:
        port = FakeInputPort(callback)
        holder.append(port)
        return port

    clock = MidiClockSlaveClock("FakeIn", ppq=ppq, port_factory=factory)
    clock.start()
    return clock, holder[0]


def test_slave_rejects_ppq_not_divisible_by_24() -> None:
    with pytest.raises(ValueError, match="multiple of 24"):
        MidiClockSlaveClock("Fake", ppq=100)


def test_slave_accepts_divisible_ppq() -> None:
    for ppq in (24, 48, 96, 192, 480, 960):
        MidiClockSlaveClock("Fake", ppq=ppq, port_factory=lambda _n, _cb: None)


def test_slave_now_tick_advances_with_clock_messages() -> None:
    clock, port = _make_slave(ppq=480)
    # Each MIDI clock = 480/24 = 20 jtx ticks.
    assert clock.now_tick() == 0
    port.fire("clock")
    assert clock.now_tick() == 20
    for _ in range(23):
        port.fire("clock")
    # 24 clocks = one quarter note = 480 jtx ticks.
    assert clock.now_tick() == 480


def test_slave_start_resets_clock_count() -> None:
    clock, port = _make_slave()
    for _ in range(50):
        port.fire("clock")
    assert clock.now_tick() > 0
    port.fire("start")
    assert clock.now_tick() == 0


def test_slave_estimates_tempo_from_clock_gaps() -> None:
    """Fire 24 clocks across 0.5 s → 120 BPM (one quarter = 0.5 s)."""
    clock, port = _make_slave()
    # Seed the estimator with the first tick (no gap yet).
    port.fire("clock")
    # Then 23 more, each 0.5/24 s apart.
    interval = 0.5 / 24
    for _ in range(23):
        time.sleep(interval)
        port.fire("clock")
    # Exponential smoothing won't have fully converged from 120 default,
    # and ``time.sleep`` jitter on a non-realtime OS adds noise — but
    # the estimate must be in the right ballpark.
    assert 70 <= clock.tempo_bpm() <= 170


def test_slave_wait_until_blocks_until_clocks_arrive() -> None:
    clock, port = _make_slave(ppq=480)
    # Need 2 MIDI clocks to reach jtx tick 40 (each clock = 20 ticks).
    barrier = threading.Event()

    def waiter() -> None:
        clock.wait_until(40)
        barrier.set()

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.02)
    assert not barrier.is_set()  # waiting for clocks
    port.fire("clock")
    time.sleep(0.02)
    assert not barrier.is_set()  # only 20 ticks yet
    port.fire("clock")
    barrier.wait(timeout=1.0)
    assert barrier.is_set()
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_slave_wait_until_returns_when_already_past() -> None:
    clock, port = _make_slave(ppq=480)
    for _ in range(10):
        port.fire("clock")  # 200 jtx ticks accumulated
    t0 = time.perf_counter()
    clock.wait_until(50)  # already past
    assert (time.perf_counter() - t0) < 0.01


def test_slave_stop_closes_port_and_wakes_waiters() -> None:
    clock, port = _make_slave()
    barrier = threading.Event()

    def waiter() -> None:
        clock.wait_until(10_000)
        barrier.set()

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.02)
    clock.stop()
    barrier.wait(timeout=1.0)
    assert barrier.is_set()
    assert port.closed
    assert clock.now_tick() == 0
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_slave_ignores_unknown_messages() -> None:
    clock, port = _make_slave()
    port.fire("note_on")
    port.fire("songpos")
    port.fire("clock")
    # Only the one clock should have advanced the counter.
    assert clock.now_tick() == 20


def test_link_clock_construction_raises() -> None:
    with pytest.raises(NotImplementedError, match="deferred"):
        AbletonLinkClock()


def test_link_clock_methods_raise() -> None:
    """Direct method calls on the unconstructed class also raise so a
    future user of the type doesn't accidentally call into a no-op."""

    class _Bypass(AbletonLinkClock):
        def __init__(self) -> None:
            pass  # skip the placeholder __init__

    c = _Bypass()
    with pytest.raises(NotImplementedError):
        c.tempo_bpm()
    with pytest.raises(NotImplementedError):
        c.start()
    with pytest.raises(NotImplementedError):
        c.stop()
    with pytest.raises(NotImplementedError):
        c.now_tick()
    with pytest.raises(NotImplementedError):
        c.wait_until(0)
