"""jtx_player — developer CLI for playing or rendering a .jtx song.

Not the v1 user surface (that's the PySide6 GUI). Useful for smoke-
testing songs against a real CoreMIDI port (or against a .mid file
for offline inspection in a DAW).

Usage examples:

    # List the MIDI output ports the OS exposes.
    python tools/jtx_player.py --list-ports

    # Play examples/phuture_test.jtx through IAC Bus 1 for 16 bars.
    python tools/jtx_player.py examples/phuture_test.jtx \
        --port "IAC Driver Bus 1" --bars 16

    # Render the same song to a .mid file (no audio, just MIDI).
    python tools/jtx_player.py examples/phuture_test.jtx \
        --render /tmp/phuture.mid --bars 32

Setup resolution: if ``--setup`` isn't given, the CLI looks for
``<song-dir>/<song.setup_ref>.jtx-setup`` next to the song file.

Stop playback with Ctrl-C — the all-notes-off CC fires on every
channel as part of ``RealtimeMidiSink.stop`` so no stuck notes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jtx.engine.clock_source import (
    AbletonLinkClock,
    ClockSource,
    InternalClock,
    MidiClockSlaveClock,
)
from jtx.engine.scheduler import Scheduler
from jtx.model.types import ClockMode
from jtx.persist.json_io import load_setup, load_song
from jtx.player import SongPlayer
from jtx.sinks.midifile import MidiFileSink
from jtx.sinks.realtime import RealtimeMidiSink

_CLOCK_CHOICES: tuple[ClockMode, ...] = (
    "internal_master",
    "midi_clock_slave",
    "ableton_link",
)


def _build_clock(
    mode: ClockMode,
    *,
    tempo_bpm: float,
    ppq: int,
    midi_clock_in_port: str | None,
) -> ClockSource:
    if mode == "internal_master":
        return InternalClock(tempo_bpm=tempo_bpm, ppq=ppq)
    if mode == "midi_clock_slave":
        if not midi_clock_in_port:
            raise ValueError(
                "midi_clock_slave requires a MIDI-in port "
                "(setup.midi_clock_in_port or --midi-clock-in)"
            )
        return MidiClockSlaveClock(midi_clock_in_port, ppq=ppq)
    if mode == "ableton_link":
        return AbletonLinkClock()  # raises NotImplementedError today
    raise ValueError(f"unknown clock_mode {mode!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jtx_player",
        description="Play or render a .jtx song.",
    )
    parser.add_argument("song", nargs="?", type=Path, help=".jtx song file")
    parser.add_argument(
        "--setup",
        type=Path,
        default=None,
        help=".jtx-setup file (default: '<song-dir>/<setup_ref>.jtx-setup')",
    )
    parser.add_argument(
        "--port",
        default=None,
        help="MIDI output port name (default: setup's default_midi_port)",
    )
    parser.add_argument(
        "--part",
        default=None,
        help="Part name to play (default: first part in arrangement)",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=None,
        help="How many bars to play (default: the part's bar count)",
    )
    parser.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="Override the song's tempo",
    )
    parser.add_argument(
        "--render",
        type=Path,
        default=None,
        help="Render to a .mid file instead of playing",
    )
    parser.add_argument(
        "--clock",
        choices=_CLOCK_CHOICES,
        default=None,
        help="Clock source override (default: setup.clock_mode)",
    )
    parser.add_argument(
        "--midi-clock-in",
        default=None,
        help="MIDI-in port for 'midi_clock_slave' (default: setup.midi_clock_in_port)",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List available MIDI output ports and exit",
    )

    args = parser.parse_args(argv)

    if args.list_ports:
        import mido

        for name in mido.get_output_names():
            print(name)
        return 0

    if args.song is None:
        parser.error("song is required (or pass --list-ports)")

    song = load_song(args.song)
    setup_path = args.setup or args.song.parent / f"{song.setup_ref}.jtx-setup"
    if not setup_path.exists():
        parser.error(f"setup file not found: {setup_path}")
    setup = load_setup(setup_path)

    if args.part is not None:
        part_name = args.part
    elif song.arrangement:
        part_name = song.arrangement[0]
    elif song.parts:
        part_name = next(iter(song.parts))
    else:
        parser.error(f"song {song.title!r} has no parts")
        return 2  # unreachable; appeases mypy

    if part_name not in song.parts:
        parser.error(f"part {part_name!r} not in song {song.title!r}")

    bars = args.bars if args.bars is not None else song.parts[part_name].bars
    bpm = args.bpm if args.bpm is not None else float(song.tempo)

    player = SongPlayer(song, setup, part_name)

    if args.render is not None:
        # Offline render always uses the internal master — the
        # generator runs as fast as possible into the MIDI file.
        sink: MidiFileSink | RealtimeMidiSink = MidiFileSink(args.render, ppq=player.ppq)
        clock: ClockSource = InternalClock(tempo_bpm=bpm, ppq=player.ppq)
        Scheduler(clock, sink).run(
            bar_count=bars,
            ticks_per_bar=player.ticks_per_bar,
            bar_generator=player.bar_generator(),
        )
        print(f"rendered {bars} bars of {song.title!r} to {args.render}")
        return 0

    port_name = args.port or setup.default_midi_port
    sink = RealtimeMidiSink(port_name=port_name)

    mode: ClockMode = args.clock or setup.clock_mode
    midi_clock_in = args.midi_clock_in or setup.midi_clock_in_port
    try:
        clock = _build_clock(
            mode,
            tempo_bpm=bpm,
            ppq=player.ppq,
            midi_clock_in_port=midi_clock_in,
        )
    except (NotImplementedError, ValueError) as exc:
        parser.error(str(exc))

    print(
        f"playing {song.title!r} part {part_name!r} for {bars} bars at "
        f"{bpm:.1f} BPM via {port_name!r} (clock: {mode}; Ctrl-C to stop)"
    )
    try:
        Scheduler(clock, sink).run(
            bar_count=bars,
            ticks_per_bar=player.ticks_per_bar,
            bar_generator=player.bar_generator(),
        )
    except KeyboardInterrupt:
        print("\nstopped — sending all-notes-off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
