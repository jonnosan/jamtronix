"""``drum_one_shot`` — single hits at configured step positions.

Use for claps, crashes, cowbells, vocal stabs — anything that fires
on a small fixed set of steps inside the bar rather than running a
sequence. The ``steps`` knob is a list of step indices (e.g. ``[0]``
for a crash on beat 1, ``[4, 12]`` for snare on 2 and 4).

Optional ``flam_ticks`` knob (list of tick offsets) adds extra hits
at small offsets after each main hit, each one quieter than the
previous by ``flam_decay`` (default 0.7). Used to recreate the
TR-909 / TR-707 clap's tape-flam character (tight cluster of 3 hits
within ~30ms) — set ``flam_ticks: [12, 24]`` for two extra clap-style
hits at ~25ms and ~50ms after the main at 124 BPM / PPQ 480.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn


class DrumOneShot(Algorithm):
    """One drum piece, hits only on the configured ``steps``."""

    name: ClassVar[str] = "drum_one_shot"

    def __init__(self, *, midi_channel: int, midi_note: int) -> None:
        self.midi_channel = midi_channel
        self.midi_note = midi_note

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        raw_steps = knobs.get("steps", [])
        if not isinstance(raw_steps, list):
            raise TypeError(
                f"drum_one_shot: 'steps' must be a list, got {type(raw_steps).__name__}"
            )

        raw_flam = knobs.get("flam_ticks", [])
        if not isinstance(raw_flam, list):
            raise TypeError(
                f"drum_one_shot: 'flam_ticks' must be a list, got {type(raw_flam).__name__}"
            )
        flam_decay = float(knobs.get("flam_decay", 0.7))

        velocity = int(knobs.get("velocity", 110))
        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = int(knobs.get("duration_ticks", max(1, s // 2)))

        v = max(1, min(127, velocity))
        events: list[Event] = []
        for raw in raw_steps:
            step = int(raw)
            if not (0 <= step < total_steps):
                continue
            tick = step * s
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
            # Flam hits: each one quieter than the previous by flam_decay.
            flam_vel = float(v)
            for offset_raw in raw_flam:
                flam_vel *= flam_decay
                vel_int = max(1, int(round(flam_vel)))
                ftick = tick + int(offset_raw)
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
