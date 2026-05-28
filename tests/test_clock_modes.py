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


# ---------------------------------------------------- AbletonLinkClock


class _FakeSessionState:
    """In-memory Link session state for tests.

    Beat advances at a deterministic rate dictated by ``tempo`` and a
    ``time`` counter we control directly from the test.
    """

    def __init__(self, link: _FakeLink) -> None:
        self._link = link

    def tempo(self) -> float:
        return self._link.tempo

    def beatAtTime(self, micros: int, _quantum: float) -> float:
        # beats = micros * tempo / 60_000_000
        return micros * self._link.tempo / 60_000_000.0


class _FakeClock:
    def __init__(self, link: _FakeLink) -> None:
        self._link = link

    def micros(self) -> int:
        return self._link.now_micros


class _FakeLink:
    """Minimal in-memory Link for tests — no real Link peer involved."""

    def __init__(self, tempo: float = 120.0) -> None:
        self.tempo = float(tempo)
        self.now_micros = 0
        self.enabled = False
        self.startStopSyncEnabled = False
        self._tempo_callback: Callable[[float], None] | None = None
        self._start_stop_callback: Callable[[bool], None] | None = None

    def captureSessionState(self) -> _FakeSessionState:
        return _FakeSessionState(self)

    def clock(self) -> _FakeClock:
        return _FakeClock(self)

    def setTempoCallback(self, fn: Callable[[float], None]) -> None:
        self._tempo_callback = fn

    def setStartStopCallback(self, fn: Callable[[bool], None]) -> None:
        self._start_stop_callback = fn

    # --- test helpers (not part of the real link.Link API) -----------

    def advance_micros(self, micros: int) -> None:
        self.now_micros += micros

    def fire_tempo(self, new_tempo: float) -> None:
        self.tempo = float(new_tempo)
        if self._tempo_callback is not None:
            self._tempo_callback(self.tempo)

    def fire_start_stop(self, is_playing: bool) -> None:
        if self._start_stop_callback is not None:
            self._start_stop_callback(is_playing)


def _make_link_clock(*, ppq: int = 480, tempo: float = 120.0) -> tuple[AbletonLinkClock, _FakeLink]:
    holder: list[_FakeLink] = []

    def factory(initial_tempo: float) -> _FakeLink:
        link_obj = _FakeLink(initial_tempo)
        holder.append(link_obj)
        return link_obj

    clock = AbletonLinkClock(ppq=ppq, tempo_bpm=tempo, link_factory=factory)
    return clock, holder[0]


def test_link_clock_reports_session_tempo() -> None:
    clock, link = _make_link_clock(tempo=120.0)
    assert clock.tempo_bpm() == 120.0
    link.fire_tempo(140.0)
    assert clock.tempo_bpm() == 140.0


def test_link_clock_now_tick_is_zero_before_start() -> None:
    clock, _link = _make_link_clock()
    assert clock.now_tick() == 0


def test_link_clock_now_tick_advances_with_link_time() -> None:
    clock, link = _make_link_clock(ppq=480, tempo=120.0)
    clock.start()
    # At 120 BPM, 1 beat = 500_000 micros; 1 beat = 480 ticks.
    link.advance_micros(500_000)
    assert clock.now_tick() == 480


def test_link_clock_stop_resets_now_tick_to_zero() -> None:
    clock, link = _make_link_clock(tempo=120.0)
    clock.start()
    link.advance_micros(1_000_000)
    assert clock.now_tick() > 0
    clock.stop()
    assert clock.now_tick() == 0


def test_link_clock_wait_until_returns_when_already_past() -> None:
    clock, link = _make_link_clock(ppq=480, tempo=120.0)
    clock.start()
    link.advance_micros(1_000_000)  # 2 beats = 960 ticks
    # No real waiting; the loop should see we're past target and
    # return on the first iteration.
    clock.wait_until(100)


def test_link_clock_wait_until_raises_when_not_started() -> None:
    clock, _link = _make_link_clock()
    with pytest.raises(RuntimeError, match="not started"):
        clock.wait_until(100)


def test_link_clock_responds_to_start_stop_callback() -> None:
    """A start/stop event from the Link session updates is_playing state."""
    clock, link = _make_link_clock()
    # Initial: not playing.
    assert clock._is_playing is False
    link.fire_start_stop(True)
    assert clock._is_playing is True
    link.fire_start_stop(False)
    assert clock._is_playing is False


def test_link_clock_rejects_bad_ppq() -> None:
    with pytest.raises(ValueError, match="ppq must be > 0"):
        AbletonLinkClock(ppq=0, link_factory=_FakeLink)


def test_link_clock_rejects_bad_tempo() -> None:
    with pytest.raises(ValueError, match="tempo_bpm must be > 0"):
        AbletonLinkClock(tempo_bpm=0, link_factory=_FakeLink)
