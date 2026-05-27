"""``drum_one_shot`` — single hits at euclid-distributed step positions.

Use for claps, crashes, cowbells, vocal stabs — anything that fires
on a small fixed set of steps inside the bar rather than running a
sequence. ``pulses`` and ``offset`` drive an even euclid distribution
across the bar's 16 steps (``pulses=2, offset=4`` = backbeat clap).

Optional flam cluster: ``flam_count`` extra hits per main hit, each
``flam_spacing_ticks`` ticks apart and ``flam_decay`` quieter than
the last (TR-909 / TR-707 clap character).

Each NoteOff lands a fixed 30 ticks after its NoteOn — purely MIDI-
protocol housekeeping. Drum samples ignore note-off and play their
internal envelope, so there's no knob for this.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._euclid import euclid
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn

_NOTE_OFF_OFFSET_TICKS = 30


class DrumOneShot(Algorithm):
    """One drum piece, hits distributed by euclid(pulses, offset)."""

    name: ClassVar[str] = "drum_one_shot"

    def __init__(self, *, midi_channel: int, midi_note: int) -> None:
        self.midi_channel = midi_channel
        self.midi_note = midi_note

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs

        pulses = int(knobs.get("pulses", 1))
        offset = int(knobs.get("offset", 0))
        velocity = int(knobs.get("velocity", 110))
        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        # NoteOff is housekeeping only — drum samples ignore it. 30
        # ticks ≈ 32nd note, short enough that any DAW that *does*
        # respect note-off (rare) sees a tight, percussive hit.
        duration = _NOTE_OFF_OFFSET_TICKS

        flam_count = max(0, int(knobs.get("flam_count", 0)))
        flam_spacing = max(0, int(knobs.get("flam_spacing_ticks", 12)))
        flam_decay = float(knobs.get("flam_decay", 0.7))

        pattern = euclid(pulses, total_steps, offset)
        v = max(1, min(127, velocity))
        events: list[Event] = []
        for step_idx, fires in enumerate(pattern):
            if not fires:
                continue
            tick = step_idx * s
            events.append(
                NoteOn(tick=tick, channel=self.midi_channel, note=self.midi_note, velocity=v)
            )
            events.append(
                NoteOff(
                    tick=tick + duration,
                    channel=self.midi_channel,
                    note=self.midi_note,
                )
            )
            flam_vel = float(v)
            for flam_idx in range(flam_count):
                flam_vel *= flam_decay
                vel_int = max(1, int(round(flam_vel)))
                ftick = tick + (flam_idx + 1) * flam_spacing
                events.append(
                    NoteOn(
                        tick=ftick,
                        channel=self.midi_channel,
                        note=self.midi_note,
                        velocity=vel_int,
                    )
                )
                events.append(
                    NoteOff(
                        tick=ftick + duration,
                        channel=self.midi_channel,
                        note=self.midi_note,
                    )
                )
        return events
