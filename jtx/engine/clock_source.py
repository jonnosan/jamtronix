"""Clock source ABC + the internal master clock.

Three clock modes are planned (see ``docs/SPEC.md`` §Clock Modes):

* :class:`InternalClock` — perf-counter master (this file).
* MIDI Clock slave — issue #6.
* Ableton Link — issue #6.

The scheduler is written against :class:`ClockSource` only, so swapping
modes is a constructor change.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod


class ClockSource(ABC):
    """Tick-time source for the scheduler.

    All implementations carry a :attr:`ppq` (ticks per quarter note).
    PPQ is fixed at construction time; tempo can change at runtime
    (knob, MIDI tempo, or Link).
    """

    ppq: int

    @abstractmethod
    def tempo_bpm(self) -> float:
        """Current effective tempo in beats per minute."""

    @abstractmethod
    def start(self) -> None:
        """Latch tick 0 to now. Idempotent after first call."""

    @abstractmethod
    def stop(self) -> None:
        """Release the latch. ``now_tick`` returns 0 after stop."""

    @abstractmethod
    def now_tick(self) -> int:
        """Absolute tick since :meth:`start`. Returns 0 if not started."""

    @abstractmethod
    def wait_until(self, target_tick: int) -> None:
        """Block until ``now_tick() >= target_tick``.

        For internal master clocks this is a ``time.sleep``; for slaves
        it may be event-driven. Returns immediately if the target tick
        is already past.
        """


class InternalClock(ClockSource):
    """Perf-counter driven master clock — default mode.

    Tick duration is ``60 / (bpm * ppq)`` seconds. ``time.perf_counter``
    is the monotonic source; ``time.sleep`` blocks until the next event.
    """

    def __init__(self, tempo_bpm: float = 120.0, ppq: int = 480) -> None:
        if tempo_bpm <= 0:
            raise ValueError(f"tempo_bpm must be > 0, got {tempo_bpm}")
        if ppq <= 0:
            raise ValueError(f"ppq must be > 0, got {ppq}")
        self._tempo_bpm = float(tempo_bpm)
        self.ppq = ppq
        self._t0: float | None = None

    def tempo_bpm(self) -> float:
        return self._tempo_bpm

    def set_tempo(self, bpm: float) -> None:
        """Snap the tempo to *bpm*.

        Naive: doesn't re-anchor ``t0`` to keep the current tick
        continuous, so a mid-playback tempo change causes a one-tick
        jump in absolute tick. Acceptable for v1 because tempo changes
        during a jam are rare and audibly indistinguishable from any
        other tempo change.
        """
        if bpm <= 0:
            raise ValueError(f"tempo_bpm must be > 0, got {bpm}")
        self._tempo_bpm = float(bpm)

    def _tick_seconds(self) -> float:
        return 60.0 / (self._tempo_bpm * self.ppq)

    def start(self) -> None:
        if self._t0 is None:
            self._t0 = time.perf_counter()

    def stop(self) -> None:
        self._t0 = None

    def now_tick(self) -> int:
        if self._t0 is None:
            return 0
        elapsed = time.perf_counter() - self._t0
        return int(elapsed / self._tick_seconds())

    def wait_until(self, target_tick: int) -> None:
        if self._t0 is None:
            raise RuntimeError("InternalClock not started")
        target_time = self._t0 + target_tick * self._tick_seconds()
        delay = target_time - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
