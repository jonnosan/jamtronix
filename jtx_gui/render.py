"""Offline render — walk a song's arrangement into a Type-0 .mid file.

Mirrors the playback bar loop in :mod:`jtx_gui.transport` but feeds a
:class:`MidiFileSink` instead of a realtime sink and runs straight
through the arrangement without any clock source. Same engine,
deterministic output.

Used by the toolbar's "Render to MIDI" button. The user picks a target
path; we open the sink, walk every part once in arrangement order, and
close. No live overrides — pure playlist, per the spec.
"""

from __future__ import annotations

from pathlib import Path

from jtx.engine.events import Event
from jtx.model import Setup, Song
from jtx.player import SongPlayer
from jtx.sinks.midifile import MidiFileSink


def render_song_to_midi(
    song: Song,
    setup: Setup,
    path: Path,
    *,
    ppq: int = 480,
) -> Path:
    """Render ``song`` to ``path`` as a Type-0 .mid file."""
    sink = MidiFileSink(path, ppq=ppq)
    sink.start()
    try:
        absolute_tick = 0
        # Empty arrangements fall back to playing every part once in
        # voices order — keeps a brand-new song renderable.
        arrangement = song.arrangement or list(song.parts.keys())
        for part_name in arrangement:
            if part_name not in song.parts:
                continue
            player = SongPlayer(song, setup, part_name, ppq=ppq)
            part = song.parts[part_name]
            for bar_index in range(max(1, part.bars)):
                events: list[Event] = player.events_for_bar(bar_index)
                events.sort(key=lambda e: e.tick)
                for ev in events:
                    # Push each event's absolute tick into the sink via
                    # an Event copy so the sink doesn't mutate the
                    # algorithm's relative ticks.
                    abs_ev = _retick(ev, absolute_tick + ev.tick)
                    sink.emit(abs_ev)
                absolute_tick += player.ticks_per_bar
    finally:
        sink.stop()
    return path


def _retick(event: Event, absolute_tick: int) -> Event:
    """Return a copy of ``event`` with ``tick`` set to ``absolute_tick``."""
    from dataclasses import replace

    return replace(event, tick=absolute_tick)
