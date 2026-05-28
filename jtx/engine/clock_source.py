"""Clock source ABC + the three clock modes (internal / MIDI slave / Link).

Three clock modes (see ``docs/SPEC.md`` §Clock Modes):

* :class:`InternalClock` — perf-counter master (default).
* :class:`MidiClockSlaveClock` — listens for 0xF8 ticks on a MIDI-in
  port, accumulates them at 24 MIDI clocks per quarter note.
* :class:`AbletonLinkClock` — placeholder. The Link binding choice is
  flagged as an open item in the spec; instantiating this class raises
  until that's resolved.

The scheduler is written against :class:`ClockSource` only, so swapping
modes is a constructor change.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


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
        self._interrupted = False

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
        self._interrupted = False

    def stop(self) -> None:
        self._t0 = None

    def request_interrupt(self) -> None:
        """Wake any in-flight :meth:`wait_until` early.

        Useful for a clean shutdown — the worker can ask the clock to
        unblock so it can drop out of its loop without waiting up to a
        whole bar at slow tempos. Reads/writes of a plain ``bool``
        attribute are atomic under CPython's GIL, so no extra lock.
        """
        self._interrupted = True

    def now_tick(self) -> int:
        if self._t0 is None:
            return 0
        elapsed = time.perf_counter() - self._t0
        return int(elapsed / self._tick_seconds())

    def wait_until(self, target_tick: int) -> None:
        if self._t0 is None:
            raise RuntimeError("InternalClock not started")
        target_time = self._t0 + target_tick * self._tick_seconds()
        while not self._interrupted:
            remaining = target_time - time.perf_counter()
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))


# 24 MIDI clock messages per quarter note — fixed by the MIDI spec.
_MIDI_CLOCKS_PER_QUARTER = 24


InputPortFactory = Callable[[str, Callable[[Any], None]], Any]
"""Open a mido in-port that calls *callback* on every incoming message.

Default = a thin wrapper over ``mido.open_input``. Tests inject a
fake that exposes a hook for synthesised messages.
"""


def _default_input_factory(port_name: str, callback: Callable[[Any], None]) -> Any:
    import mido

    return mido.open_input(port_name, callback=callback)


class MidiClockSlaveClock(ClockSource):
    """Listens to 0xF8 / 0xFA / 0xFB / 0xFC on a MIDI-in port.

    24 MIDI clocks make a quarter note, so each clock tick advances
    ``now_tick`` by ``ppq // 24`` jtx ticks. PPQ must divide evenly by
    24 (480 / 96 / 192 all work; 100 does not — constructor will reject).
    Tempo is exponentially smoothed across incoming clock gaps.

    The mido callback runs on a background thread; this class is
    thread-safe via a single condition variable. ``wait_until`` blocks
    until enough clock messages have accumulated, woken up on each
    incoming tick.
    """

    def __init__(
        self,
        port_name: str,
        ppq: int = 480,
        *,
        port_factory: InputPortFactory | None = None,
    ) -> None:
        if ppq <= 0:
            raise ValueError(f"ppq must be > 0, got {ppq}")
        if ppq % _MIDI_CLOCKS_PER_QUARTER != 0:
            raise ValueError(
                f"ppq {ppq} must be a multiple of {_MIDI_CLOCKS_PER_QUARTER} "
                "(MIDI clock = 24 ticks per quarter note)"
            )
        self.port_name = port_name
        self.ppq = ppq
        self._port_factory: InputPortFactory = port_factory or _default_input_factory
        self._port: Any = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._clock_count = 0
        self._running = False
        self._last_clock_time: float | None = None
        self._tempo_bpm = 120.0
        self._jtx_per_midi_clock = ppq // _MIDI_CLOCKS_PER_QUARTER

    def tempo_bpm(self) -> float:
        with self._lock:
            return self._tempo_bpm

    def start(self) -> None:
        if self._port is not None:
            return
        self._port = self._port_factory(self.port_name, self._on_message)

    def stop(self) -> None:
        port = self._port
        self._port = None
        if port is not None:
            port.close()
        with self._cond:
            self._clock_count = 0
            self._running = False
            self._last_clock_time = None
            self._cond.notify_all()

    def now_tick(self) -> int:
        with self._lock:
            return self._clock_count * self._jtx_per_midi_clock

    def wait_until(self, target_tick: int) -> None:
        # Ceiling-divide so we wait for the first MIDI clock that
        # equals or passes the target.
        target_clocks = -(-target_tick // self._jtx_per_midi_clock)
        with self._cond:
            while self._port is not None and self._clock_count < target_clocks:
                self._cond.wait()

    def _on_message(self, msg: Any) -> None:
        msg_type = getattr(msg, "type", None)
        if msg_type == "clock":
            now = time.perf_counter()
            with self._cond:
                self._clock_count += 1
                if self._last_clock_time is not None:
                    dt = now - self._last_clock_time
                    if dt > 0:
                        instant_bpm = 60.0 / (_MIDI_CLOCKS_PER_QUARTER * dt)
                        # Exponential smoothing dampens jitter from the
                        # OS scheduler and host-side clock drift.
                        self._tempo_bpm = 0.9 * self._tempo_bpm + 0.1 * instant_bpm
                self._last_clock_time = now
                self._cond.notify_all()
        elif msg_type == "start":
            with self._cond:
                self._clock_count = 0
                self._running = True
                self._last_clock_time = None
                self._cond.notify_all()
        elif msg_type == "continue":
            with self._cond:
                self._running = True
                self._cond.notify_all()
        elif msg_type == "stop":
            with self._cond:
                self._running = False
                self._cond.notify_all()


LinkFactory = Callable[[float], Any]
"""Construct a ``link.Link``-shaped object given an initial tempo (BPM).

Default = ``link.Link`` from ``LinkPython-extern``. Tests inject a
:class:`FakeLink`-style stub to avoid joining a real Link peer
session.
"""


def _default_link_factory(tempo_bpm: float) -> Any:
    # ``link`` is the optional LinkPython-extern dependency. When it's
    # not installed we surface a clear install hint; when it is, mypy
    # would otherwise flag the lack of type stubs — silence both with a
    # broad ignore (also re-silenced when the import succeeds at type-
    # check time, which would otherwise trigger an unused-ignore warning).
    try:
        import link  # type: ignore[import-not-found,import-untyped,unused-ignore]
    except ImportError as exc:  # pragma: no cover — env-dependent
        raise ImportError(
            "Ableton Link clock requires the optional LinkPython-extern "
            "package. Install with: pip install 'jamtronix[link]'."
        ) from exc
    return link.Link(tempo_bpm)


class AbletonLinkClock(ClockSource):
    """Ableton Link mode — backed by ``LinkPython-extern``.

    Wraps a single ``link.Link`` instance with a
    :class:`MidiClockSlaveClock`-style threading layer so the
    scheduler's blocking ``wait_until`` works against Link's pull-API.

    Tempo + start-stop changes from the Link session are picked up via
    ``setTempoCallback`` / ``setStartStopCallback``; ``wait_until``
    polls the link clock with a short timeout so tempo changes from
    other Link peers shorten / lengthen the remaining wait promptly.

    The optional ``link_factory`` kwarg lets tests inject a
    :class:`FakeLink`-style stub that drives time deterministically.
    """

    ppq: int

    def __init__(
        self,
        ppq: int = 480,
        tempo_bpm: float = 120.0,
        *,
        quantum: float = 4.0,
        link_factory: LinkFactory | None = None,
    ) -> None:
        if ppq <= 0:
            raise ValueError(f"ppq must be > 0, got {ppq}")
        if tempo_bpm <= 0:
            raise ValueError(f"tempo_bpm must be > 0, got {tempo_bpm}")
        self.ppq = ppq
        self._quantum = float(quantum)
        self._link: Any = (link_factory or _default_link_factory)(tempo_bpm)
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._tempo_bpm = float(tempo_bpm)
        # Beat offset of the moment :meth:`start` was called; ``None``
        # until the clock is started, again after :meth:`stop`.
        self._start_beat: float | None = None
        self._is_playing: bool = False
        self._link.setTempoCallback(self._on_tempo)
        self._link.setStartStopCallback(self._on_start_stop)

    def tempo_bpm(self) -> float:
        with self._lock:
            return self._tempo_bpm

    def start(self) -> None:
        # Joining the Link session is idempotent: setting ``enabled``
        # multiple times is harmless. ``startStopSyncEnabled`` opts us
        # into the shared transport so other Link peers see our
        # start/stop events.
        self._link.enabled = True
        self._link.startStopSyncEnabled = True
        state = self._link.captureSessionState()
        clock = self._link.clock()
        with self._cond:
            self._start_beat = state.beatAtTime(clock.micros(), self._quantum)
            self._tempo_bpm = state.tempo()
            self._cond.notify_all()

    def stop(self) -> None:
        with self._cond:
            self._start_beat = None
            self._cond.notify_all()
        # We deliberately don't disable Link here — the user may want
        # to remain in the Link session while transport is paused so
        # other peers' tempo / start / stop events keep flowing.

    def now_tick(self) -> int:
        with self._lock:
            if self._start_beat is None:
                return 0
            start_beat = self._start_beat
        state = self._link.captureSessionState()
        clock = self._link.clock()
        beat = state.beatAtTime(clock.micros(), self._quantum)
        return max(0, int(round((beat - start_beat) * self.ppq)))

    def wait_until(self, target_tick: int) -> None:
        if self._start_beat is None:
            raise RuntimeError("AbletonLinkClock not started")
        target_beat_offset = target_tick / self.ppq
        with self._cond:
            while True:
                if self._start_beat is None:
                    return  # stopped while waiting — bail cleanly
                state = self._link.captureSessionState()
                clock = self._link.clock()
                current = state.beatAtTime(clock.micros(), self._quantum) - self._start_beat
                if current >= target_beat_offset:
                    return
                # Sleep with a short cap so tempo callbacks shorten /
                # lengthen the remaining wait promptly. 5ms matches
                # the polling resolution InternalClock uses for its
                # request_interrupt path.
                tempo = self._tempo_bpm or 120.0
                remaining_beats = target_beat_offset - current
                remaining_seconds = remaining_beats * 60.0 / tempo
                self._cond.wait(timeout=min(0.005, max(0.0, remaining_seconds)))

    # ---------------------------------------------------- Link callbacks

    def _on_tempo(self, new_tempo: float) -> None:
        with self._cond:
            self._tempo_bpm = float(new_tempo)
            self._cond.notify_all()

    def _on_start_stop(self, is_playing: bool) -> None:
        with self._cond:
            self._is_playing = bool(is_playing)
            self._cond.notify_all()
