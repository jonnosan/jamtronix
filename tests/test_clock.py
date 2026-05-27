"""InternalClock behaviour.

Uses a high tempo so the wall-clock waits stay sub-millisecond. The
exact tick-vs-time math is exercised; jitter is loose because we're
on a non-realtime OS.
"""

from __future__ import annotations

import time

import pytest

from jtx.engine.clock_source import InternalClock


def test_internal_clock_not_started_returns_zero() -> None:
    clock = InternalClock(tempo_bpm=120, ppq=480)
    assert clock.now_tick() == 0


def test_internal_clock_wait_before_start_raises() -> None:
    clock = InternalClock(tempo_bpm=120, ppq=480)
    with pytest.raises(RuntimeError, match="not started"):
        clock.wait_until(10)


def test_internal_clock_start_then_tick_advances() -> None:
    # 6000 BPM, PPQ 100 → 1 tick = 60 / (6000 * 100) s = 100 µs.
    # 5000 ticks ≈ 0.5 s — long enough to be measurable but fast.
    clock = InternalClock(tempo_bpm=6000, ppq=100)
    clock.start()
    time.sleep(0.05)
    tick = clock.now_tick()
    # 0.05 s / 100µs per tick = 500 ticks expected; allow ±100 for jitter.
    assert 400 <= tick <= 600


def test_internal_clock_wait_until_actually_waits() -> None:
    clock = InternalClock(tempo_bpm=6000, ppq=100)
    clock.start()
    t0 = time.perf_counter()
    clock.wait_until(1000)  # 1000 * 100µs = 100ms
    elapsed = time.perf_counter() - t0
    assert 0.08 <= elapsed <= 0.18  # 100ms ± 80ms slop


def test_internal_clock_wait_until_past_target_returns_immediately() -> None:
    clock = InternalClock(tempo_bpm=120, ppq=480)
    clock.start()
    time.sleep(0.05)
    t0 = time.perf_counter()
    clock.wait_until(1)  # tick 1 was in the past
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.01


def test_internal_clock_stop_resets() -> None:
    clock = InternalClock(tempo_bpm=120, ppq=480)
    clock.start()
    clock.stop()
    assert clock.now_tick() == 0


def test_internal_clock_set_tempo() -> None:
    clock = InternalClock(tempo_bpm=120, ppq=480)
    clock.set_tempo(140)
    assert clock.tempo_bpm() == 140


def test_internal_clock_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError):
        InternalClock(tempo_bpm=0, ppq=480)
    with pytest.raises(ValueError):
        InternalClock(tempo_bpm=120, ppq=0)
    clock = InternalClock(tempo_bpm=120)
    with pytest.raises(ValueError):
        clock.set_tempo(-1)
