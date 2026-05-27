"""jtx_player — developer CLI for playing or rendering a .jtx song.

Not the v1 user surface (that's the PySide6 GUI). Useful for smoke-
testing songs against a real CoreMIDI port (or against a .mid file
for offline inspection in a DAW).

Usage examples:

    # List the MIDI output ports the OS exposes.
    python tools/jtx_player.py --list-ports

    # Play the song's full arrangement once.
    python tools/jtx_player.py examples/phuture_test.jtx

    # Loop the arrangement forever until Ctrl-C.
    python tools/jtx_player.py examples/phuture_test.jtx --loop

    # Play just one part (e.g. for previewing a drop in isolation).
    python tools/jtx_player.py examples/phuture_test.jtx --part drop --loop

    # Render the arrangement to a .mid file (no audio, just MIDI).
    python tools/jtx_player.py examples/phuture_test.jtx \
        --render /tmp/phuture.mid

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
from jtx.engine.events import Event
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


def _preflight_midi_port(port_name: str, parser: argparse.ArgumentParser) -> None:
    """Surface a helpful error before we hit mido's terse OSError.

    macOS exposes no CoreMIDI output ports by default — IAC Driver
    has to be turned on manually. This catches the common case and
    points the user at Audio MIDI Setup instead of dropping a stack
    trace from rtmidi.
    """
    import mido

    available = mido.get_output_names()
    if not available:
        parser.error(
            "no MIDI output ports found.\n"
            "  On macOS, enable IAC Driver:\n"
            "    1. Open 'Audio MIDI Setup' (Applications → Utilities)\n"
            "    2. Window → Show MIDI Studio (⌘2)\n"
            "    3. Double-click 'IAC Driver'\n"
            "    4. Tick 'Device is online'\n"
            "    5. Default bus 'Bus 1' is fine\n"
            "  Then re-run, or pass --port with one of: --list-ports"
        )
    if port_name not in available:
        listing = "\n    ".join(sorted(available))
        parser.error(
            f"MIDI output port {port_name!r} not found.\n"
            f"  Available ports:\n    {listing}\n"
            "  Use --port to pick one, or --list-ports to see them all."
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
        help="Single part to play (default: walk the full arrangement)",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=None,
        help="Total bar cap (default: full sequence; unbounded with --loop)",
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
        "--loop",
        action="store_true",
        help="Loop the arrangement (or --part) until Ctrl-C (ignored with --render)",
    )
    parser.add_argument(
        "--open-daw",
        action="store_true",
        help="Open setup.daw_template_path via macOS 'open' before playback",
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

    bpm = args.bpm if args.bpm is not None else float(song.tempo)

    # Build the playback sequence: [(part_name, bars_for_that_part), ...].
    sequence: list[tuple[str, int]]
    if args.part is not None:
        if args.part not in song.parts:
            parser.error(f"part {args.part!r} not in song {song.title!r}")
        sequence = [(args.part, song.parts[args.part].bars)]
    elif song.arrangement:
        missing = [p for p in song.arrangement if p not in song.parts]
        if missing:
            parser.error(f"arrangement references unknown parts: {missing}")
        sequence = [(p, song.parts[p].bars) for p in song.arrangement]
    elif song.parts:
        sequence = [(name, part.bars) for name, part in song.parts.items()]
    else:
        parser.error(f"song {song.title!r} has no parts")
        return 2  # unreachable; appeases mypy

    seq_bars = sum(b for _, b in sequence)
    seq_label = " → ".join(f"{n}({b})" for n, b in sequence)

    # One SongPlayer per unique part. PPQ + ticks_per_bar come from
    # the song header today (per-part meter overrides are deferred).
    players: dict[str, SongPlayer] = {}
    for part_name, _ in sequence:
        if part_name not in players:
            players[part_name] = SongPlayer(song, setup, part_name)
    ppq = next(iter(players.values())).ppq
    ticks_per_bar = next(iter(players.values())).ticks_per_bar

    def resolve_bar(abs_bar: int) -> tuple[SongPlayer, int]:
        """Map an absolute scheduler bar index to (part-player, local bar)."""
        cursor = abs_bar % seq_bars if args.loop else abs_bar
        for part_name, part_bars in sequence:
            if cursor < part_bars:
                return players[part_name], cursor
            cursor -= part_bars
        # Should be unreachable: the scheduler stops at bar_count.
        raise IndexError(f"bar {abs_bar} past end of sequence")

    def bar_gen(abs_bar: int) -> list[Event]:
        player, local_bar = resolve_bar(abs_bar)
        return player.events_for_bar(local_bar)

    if args.render is not None:
        if args.loop:
            parser.error("--loop and --render are mutually exclusive")
        # Offline render always uses the internal master — the
        # generator runs as fast as possible into the MIDI file.
        bar_count = args.bars if args.bars is not None else seq_bars
        sink: MidiFileSink | RealtimeMidiSink = MidiFileSink(args.render, ppq=ppq)
        clock: ClockSource = InternalClock(tempo_bpm=bpm, ppq=ppq)
        Scheduler(clock, sink).run(
            bar_count=bar_count, ticks_per_bar=ticks_per_bar, bar_generator=bar_gen
        )
        print(f"rendered {bar_count} bars of {song.title!r} ({seq_label}) to {args.render}")
        return 0

    port_name = args.port or setup.default_midi_port
    _preflight_midi_port(port_name, parser)

    if args.open_daw:
        if not setup.daw_template_path:
            parser.error("--open-daw was set but setup has no daw_template_path")
        daw_path = Path(setup.daw_template_path)
        if not daw_path.exists():
            parser.error(f"DAW template not found: {daw_path}")
        import subprocess

        print(f"opening DAW template: {daw_path}")
        subprocess.run(["open", str(daw_path)], check=False)

    sink = RealtimeMidiSink(port_name=port_name)

    mode: ClockMode = args.clock or setup.clock_mode
    midi_clock_in = args.midi_clock_in or setup.midi_clock_in_port
    try:
        clock = _build_clock(
            mode,
            tempo_bpm=bpm,
            ppq=ppq,
            midi_clock_in_port=midi_clock_in,
        )
    except (NotImplementedError, ValueError) as exc:
        parser.error(str(exc))

    if args.loop:
        bar_count = args.bars if args.bars is not None else sys.maxsize
        loop_label = (
            "looping forever" if args.bars is None else f"looping (capped at {args.bars} bars)"
        )
    else:
        bar_count = args.bars if args.bars is not None else seq_bars
        loop_label = f"{bar_count} bars"

    print(
        f"playing {song.title!r} [{seq_label}] — {loop_label} at "
        f"{bpm:.1f} BPM via {port_name!r} (clock: {mode}; Ctrl-C to stop)"
    )
    try:
        Scheduler(clock, sink).run(
            bar_count=bar_count, ticks_per_bar=ticks_per_bar, bar_generator=bar_gen
        )
    except KeyboardInterrupt:
        print("\nstopped — sending all-notes-off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
