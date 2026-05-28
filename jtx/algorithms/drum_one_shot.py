"""``drum_one_shot`` — single hits at euclid-distributed step positions.

Use for claps, crashes, cowbells, vocal stabs — anything that fires
on a small fixed set of steps inside the bar rather than running a
sequence. ``pulses`` and ``offset`` drive an even euclid distribution
across the bar's 16 steps (``pulses=2, offset=4`` = backbeat clap).

Optional flam cluster: ``flam_count`` extra hits per main hit, each
``flam_spacing_ticks`` ticks apart and ``flam_decay`` quieter than
the last (TR-909 / TR-707 clap character).

Optional triplet roll fill — same knobs as ``drum_pattern.roll_*``.
Best for tom rolls into a drop: ``roll_pos="last_bar_of_8"``,
``roll_subdiv="16t"``, ``roll_depth=0.8``.

Each NoteOff lands a fixed 30 ticks after its NoteOn — purely MIDI-
protocol housekeeping. Drum samples ignore note-off and play their
internal envelope, so there's no knob for this.
"""

from __future__ import annotations

import random
from typing import ClassVar

from jtx.algorithms._euclid import euclid
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._subdivision import subdivision_grid
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Hit

_NOTE_OFF_OFFSET_TICKS = 30


class DrumOneShot(Algorithm):
    """One drum piece, hits distributed by euclid(pulses, offset).

    MIDI-naive: emits :class:`Hit` events; the voicing stage resolves
    each hit to ``(slot.midi_channel, slot.note)``.
    """

    name: ClassVar[str] = "drum_one_shot"

    def __init__(self, *, instrument_name: str | None = None) -> None:
        self._instrument_name = instrument_name

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
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
        events: list[AbstractEvent] = []
        for step_idx, fires in enumerate(pattern):
            if not fires:
                continue
            tick = step_idx * s
            events.append(self._hit(tick, v, duration))
            flam_vel = float(v)
            for flam_idx in range(flam_count):
                flam_vel *= flam_decay
                vel_int = max(1, int(round(flam_vel)))
                ftick = tick + (flam_idx + 1) * flam_spacing
                events.append(self._hit(ftick, vel_int, duration))

        roll_pos = str(knobs.get("roll_pos", "none"))
        if roll_pos != "none" and _roll_active(roll_pos, ctx.bar_index, ctx.rng):
            roll_subdiv = str(knobs.get("roll_subdiv", "16t"))
            roll_depth = float(knobs.get("roll_depth", 0.6))
            spacing, positions = subdivision_grid(roll_subdiv, ctx.ticks_per_bar, ctx.ppq)
            beats_per_bar = ctx.ticks_per_bar // ctx.ppq
            roll_start = (beats_per_bar - 1) * ctx.ppq
            roll_end = ctx.ticks_per_bar
            for i in range(positions):
                tick = i * spacing
                if tick < roll_start or tick >= roll_end:
                    continue
                if ctx.rng.random() >= roll_depth:
                    continue
                window_progress = (tick - roll_start) / max(1, roll_end - roll_start)
                vel_mult = 0.7 + 0.4 * window_progress
                roll_vel = max(1, min(127, int(v * vel_mult)))
                events.append(self._hit(tick, roll_vel, duration))

        return events

    def _hit(self, tick: int, velocity: int, duration: int) -> Hit:
        return Hit(
            instrument=self._instrument_name,
            velocity=max(1, min(127, velocity)),
            duration_ticks=duration,
            tick=tick,
        )


_ROLL_POSITIONS = ("none", "last_beat", "last_bar_of_4", "last_bar_of_8", "random_sparse")


def _roll_active(roll_pos: str, bar_index: int, rng: random.Random) -> bool:
    if roll_pos == "none":
        return False
    if roll_pos == "last_beat":
        return True
    if roll_pos == "last_bar_of_4":
        return bar_index % 4 == 3
    if roll_pos == "last_bar_of_8":
        return bar_index % 8 == 7
    if roll_pos == "random_sparse":
        return rng.random() < 0.125
    raise ValueError(
        f"drum_one_shot: unknown roll_pos {roll_pos!r} (expected one of {_ROLL_POSITIONS})"
    )
