"""TransportService — drives playback from the Live view on a worker thread.

Wraps the engine's bar-by-bar loop:

* The service owns a :class:`Setup`, a current :class:`Song`, and an
  output port name. It builds an :class:`InternalClock` and a
  :class:`RealtimeMidiSink` on start.
* On a dedicated QThread, ``_PlaybackWorker`` walks the active part
  bar by bar. Between bars it checks for a queued-part swap and
  rebuilds its :class:`SongPlayer` if so.
* All state-change signalling (bar boundary, part switch, stop,
  errors) crosses the thread boundary as Qt signals, so the GUI
  thread can update widgets safely.

What we deliberately *don't* do here:

* Walking ``song.arrangement`` as a finite playlist. The Live view
  treats each click as "queue this part next"; if no part is queued
  when the current one ends, we hold the current part. The richer
  "return to arrangement after override" behaviour from
  ``docs/SPEC.md`` §Live Override is deferred — the rest of the GUI
  has to land first.
* MIDI Clock slave / Ableton Link. Those land with the toolbar in
  #21 and route through the same TransportService.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from jtx.engine.clock_source import (
    AbletonLinkClock,
    ClockSource,
    InternalClock,
    MidiClockSlaveClock,
)
from jtx.engine.events import Event
from jtx.engine.sink import Sink
from jtx.model import ClockMode, Setup, Song
from jtx.player import SongPlayer
from jtx.sinks.realtime import RealtimeMidiSink


@dataclass(frozen=True)
class BarTick:
    """Snapshot emitted at every bar boundary."""

    part_name: str
    bar_index: int  # 0-based within the part
    part_bars: int  # the part's total bar count


SinkFactory = Callable[[str | None], Sink]
"""Builds a Sink for an output port name. Default = RealtimeMidiSink."""


def _default_sink_factory(port_name: str | None) -> Sink:
    return RealtimeMidiSink(port_name=port_name)


class TransportService(QObject):
    """Owns the playback worker thread and exposes start / stop / queue."""

    bar_changed = Signal(BarTick)
    """Fires at every bar boundary (worker thread → main thread)."""

    part_changed = Signal(str)
    """Fires when the active part swaps to a queued part."""

    queued_changed = Signal(object)
    """``str | None`` — current queue contents. ``None`` clears the queue."""

    started = Signal()
    stopped = Signal()
    error = Signal(str)
    """User-facing error string; the worker has already stopped."""

    def __init__(
        self,
        *,
        sink_factory: SinkFactory | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sink_factory = sink_factory or _default_sink_factory
        self._thread: QThread | None = None
        self._worker: _PlaybackWorker | None = None
        self._current_part: str | None = None
        self._queued_part: str | None = None

    # ----- public state ----------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def current_part(self) -> str | None:
        return self._current_part

    @property
    def queued_part(self) -> str | None:
        return self._queued_part

    # ----- start / stop ----------------------------------------------------

    def start(
        self,
        *,
        song: Song,
        setup: Setup,
        part_name: str,
        port_name: str | None,
        clock_mode: ClockMode | None = None,
        clock_in_port: str | None = None,
    ) -> None:
        """Begin playback at ``part_name``. No-op if already running."""
        if self.is_running:
            return
        if part_name not in song.parts:
            self.error.emit(f"Part {part_name!r} doesn't exist in this song.")
            return

        try:
            sink = self._sink_factory(port_name or setup.default_midi_port)
        except Exception as exc:  # noqa: BLE001 — surface any port-open failure verbatim
            self.error.emit(f"Couldn't open MIDI port: {exc}")
            return

        mode: ClockMode = clock_mode or setup.clock_mode
        slave_port = clock_in_port or setup.midi_clock_in_port
        try:
            clock = _build_clock(mode, song_tempo=song.tempo, midi_clock_in_port=slave_port)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Couldn't start clock ({mode}): {exc}")
            return

        worker = _PlaybackWorker(
            song=song,
            setup=setup,
            initial_part=part_name,
            sink=sink,
            clock=clock,
        )
        thread = QThread(self)
        worker.moveToThread(thread)

        # Wire signals.
        worker.bar_changed.connect(self._on_bar_changed)
        worker.part_changed.connect(self._on_part_changed)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._on_worker_finished)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)

        self._thread = thread
        self._worker = worker
        self._current_part = part_name
        self._queued_part = None
        thread.start()
        self.started.emit()
        self.part_changed.emit(part_name)

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()

    def stop_and_wait(self, timeout_ms: int = 3000) -> None:
        """Stop the worker and block until the thread exits.

        Use this from MainWindow.closeEvent — without it, Qt destroys
        the running QThread on app exit (emitting
        ``QThread: Destroyed while thread is still running``) and the
        worker's ``finally`` block never gets to fire its
        all-notes-off CC, so notes linger in the DAW.
        """
        if self._worker is not None:
            self._worker.request_stop()
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.wait(timeout_ms)
        self._thread = None
        self._worker = None
        self._current_part = None
        self._queued_part = None

    def queue_part(self, part_name: str | None) -> None:
        """Queue ``part_name`` to take over at the next bar boundary."""
        if self._worker is None:
            return
        self._worker.queue_part(part_name)
        self._queued_part = part_name
        self.queued_changed.emit(part_name)

    # ----- worker callbacks (cross-thread via signals) ---------------------

    def _on_bar_changed(self, tick: BarTick) -> None:
        self.bar_changed.emit(tick)

    def _on_part_changed(self, name: str) -> None:
        self._current_part = name
        if self._queued_part == name:
            self._queued_part = None
            self.queued_changed.emit(None)
        self.part_changed.emit(name)

    def _on_worker_error(self, msg: str) -> None:
        self.error.emit(msg)

    def _on_worker_finished(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = None
        self._worker = None
        self._current_part = None
        self._queued_part = None
        self.queued_changed.emit(None)
        self.stopped.emit()


# --------------------------------------------------------------------------
#                          playback worker
# --------------------------------------------------------------------------


class _PlaybackWorker(QObject):
    """Runs the bar loop. Lives on a QThread; never touches widgets directly."""

    bar_changed = Signal(BarTick)
    part_changed = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        *,
        song: Song,
        setup: Setup,
        initial_part: str,
        sink: Sink,
        clock: ClockSource,
    ) -> None:
        super().__init__()
        self._song = song
        self._setup = setup
        self._part = initial_part
        self._queued: str | None = None
        self._stop_requested = False
        self._sink = sink
        self._clock = clock

    def request_stop(self) -> None:
        self._stop_requested = True
        # If the clock supports interrupt (InternalClock does), wake
        # any in-flight wait_until so the worker can exit promptly.
        interrupt = getattr(self._clock, "request_interrupt", None)
        if callable(interrupt):
            interrupt()

    def queue_part(self, part_name: str | None) -> None:
        self._queued = part_name

    # ----- main loop ------------------------------------------------------

    def run(self) -> None:
        try:
            self._clock.start()
            self._sink.start()
            try:
                self._loop()
            finally:
                self._sink.stop()
                self._clock.stop()
        except Exception as exc:  # noqa: BLE001 — surface as a friendly error
            self.error.emit(f"Playback failed: {exc}")
        finally:
            self.finished.emit()

    def _loop(self) -> None:
        """Walk the parts list, looping or advancing per ``Part.loop``.

        At every bar boundary:
        * if a click landed via :meth:`queue_part`, jump to that part;
        * else if the current part's last bar just played and ``loop``
          is on, restart the same part from bar 0;
        * else advance to the next part in ``song.parts`` dict order,
          wrapping at the end (steady jam mode — playback never stops
          on its own).
        """
        player = self._build_player(self._part)
        self._apply_part_tempo(self._song.parts[self._part])
        bar_index = 0
        absolute_tick = 0
        while not self._stop_requested:
            # Honour any queued part swap at the bar boundary first.
            if self._queued is not None:
                if self._queued in self._song.parts and self._queued != self._part:
                    self._part = self._queued
                    player = self._build_player(self._part)
                    self._apply_part_tempo(self._song.parts[self._part])
                    bar_index = 0
                    self.part_changed.emit(self._part)
                self._queued = None

            part = self._song.parts[self._part]
            part_bars = max(1, part.bars)

            # If we've fallen off the end of the part, either loop or
            # advance per ``Part.loop``.
            if bar_index >= part_bars:
                if part.loop:
                    bar_index = 0
                else:
                    next_part = self._next_part_after(self._part)
                    if next_part is not None and next_part != self._part:
                        self._part = next_part
                        player = self._build_player(self._part)
                        self._apply_part_tempo(self._song.parts[self._part])
                        self.part_changed.emit(self._part)
                    bar_index = 0
                    part = self._song.parts[self._part]
                    part_bars = max(1, part.bars)

            ticks_per_bar = player.ticks_per_bar
            self.bar_changed.emit(
                BarTick(
                    part_name=self._part,
                    bar_index=bar_index,
                    part_bars=part.bars,
                )
            )
            events: list[Event] = player.events_for_bar(bar_index)
            events.sort(key=lambda e: e.tick)
            for ev in events:
                if self._stop_requested:
                    return
                self._clock.wait_until(absolute_tick + ev.tick)
                self._sink.emit(ev)
            absolute_tick += ticks_per_bar
            bar_index += 1

    def _apply_part_tempo(self, part: object) -> None:
        """Push the part's tempo override (if any) to the clock.

        Only InternalClock supports ``set_tempo``; MIDI-clock-slave
        and Ableton-Link clocks take their tempo from external, so
        we leave them untouched.
        """
        override = getattr(part, "tempo", None)
        if override is None:
            override = self._song.tempo
        setter = getattr(self._clock, "set_tempo", None)
        if callable(setter):
            setter(float(override))

    def _next_part_after(self, current: str) -> str | None:
        """Return the part following ``current`` in dict order (wraps)."""
        keys = list(self._song.parts.keys())
        if not keys:
            return None
        try:
            idx = keys.index(current)
        except ValueError:
            return keys[0]
        return keys[(idx + 1) % len(keys)]

    def _build_player(self, part_name: str) -> SongPlayer:
        return SongPlayer(self._song, self._setup, part_name)


def _build_clock(
    mode: ClockMode,
    *,
    song_tempo: float,
    midi_clock_in_port: str | None,
) -> ClockSource:
    if mode == "internal_master":
        return InternalClock(tempo_bpm=float(song_tempo))
    if mode == "midi_clock_slave":
        if not midi_clock_in_port:
            raise ValueError("midi_clock_slave requires an input port name")
        return MidiClockSlaveClock(midi_clock_in_port)
    if mode == "ableton_link":
        return AbletonLinkClock()
    raise ValueError(f"unknown clock mode: {mode!r}")
