"""Offline MIDI file sink — records arrangement playback to a ``.mid``.

Used by the "Render to MIDI file" button (docs/SPEC.md §Offline MIDI
File Export). Events are buffered in absolute-tick form during
playback; on ``stop()`` they're sorted, delta-encoded, and written as
a Type-0 MIDI file at ``ticks_per_beat = ppq``.

This is single-track on purpose — every event already carries its own
channel, so Ableton (and most DAWs) demultiplex correctly on import.
A multi-track variant can come later if user feedback says otherwise.
"""

from __future__ import annotations

from pathlib import Path

from jtx.engine.events import Event
from jtx.engine.sink import Sink
from jtx.sinks._mido_convert import event_to_mido


class MidiFileSink(Sink):
    """Captures emitted events and writes a Type-0 ``.mid`` on stop."""

    def __init__(self, path: Path | str, ppq: int = 480) -> None:
        self.path = Path(path)
        self.ppq = ppq
        self._events: list[Event] = []

    def start(self) -> None:
        self._events.clear()

    def emit(self, event: Event) -> None:
        self._events.append(event)

    def stop(self) -> None:
        import mido

        midi = mido.MidiFile(ticks_per_beat=self.ppq, type=0)
        track = mido.MidiTrack()
        midi.tracks.append(track)

        events = sorted(self._events, key=lambda e: e.tick)
        last_tick = 0
        for ev in events:
            msg = event_to_mido(ev)
            msg.time = ev.tick - last_tick
            track.append(msg)
            last_tick = ev.tick

        # End-of-track meta event so the file is well-formed even with
        # no real events.
        track.append(mido.MetaMessage("end_of_track", time=0))

        midi.save(self.path)
