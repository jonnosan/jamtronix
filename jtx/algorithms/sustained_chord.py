"""``sustained_chord`` and ``chord_stab`` — chord-quality + euclid driven.

``sustained_chord`` holds a chord voicing across the bar.
``chord_stab`` fires the same voicing at euclid-distributed steps.

Both pick the chord shape from a single ``quality`` knob (minor,
major, sus4, maj7, …) rather than a free-form intervals list. Pitches
stack on the current ``ctx.chord_root_semitones`` so the chord follows
the macro progression bar-to-bar.

MIDI-naive: both emit :class:`Note` events; the voicing stage adds
the channel from the voice slot.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._chords import intervals_for
from jtx.algorithms._euclid import euclid
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note


class SustainedChord(Algorithm):
    """Long-gated polyphonic chord voicing."""

    name: ClassVar[str] = "sustained_chord"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        quality = str(knobs.get("quality", "minor"))
        intervals = intervals_for(quality)

        gate = float(knobs.get("gate", 0.95))
        octave_shift = int(knobs.get("octave", 0))
        base_vel = int(knobs.get("base_vel", 75))
        vel_spread = max(0, int(knobs.get("velocity_spread", 5)))
        drift_prob = float(knobs.get("drift_prob", 0.0))

        register_octave = 4 + octave_shift
        root_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones
        duration = max(1, int(ctx.ticks_per_bar * gate))

        drift_index: int | None = None
        if drift_prob > 0 and intervals and rng.random() < drift_prob:
            drift_index = rng.randrange(len(intervals))

        events: list[AbstractEvent] = []
        for idx, interval in enumerate(intervals):
            pitch = root_midi + interval
            if idx == drift_index:
                pitch -= 12
            pitch = max(0, min(127, pitch))
            jitter = rng.randint(-vel_spread, vel_spread) if vel_spread else 0
            vel = max(1, min(127, base_vel + jitter))
            events.append(
                Note(pitch=pitch, velocity=vel, duration_ticks=duration, tick=0)
            )
        return events


class ChordStab(Algorithm):
    """Short-gated chord on euclid-distributed steps."""

    name: ClassVar[str] = "chord_stab"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        quality = str(knobs.get("quality", "minor"))
        intervals = intervals_for(quality)

        pulses = int(knobs.get("pulses", 4))
        offset = int(knobs.get("offset", 2))  # off-beat 16ths by default
        gate = float(knobs.get("gate", 0.4))
        octave_shift = int(knobs.get("octave", 0))
        base_vel = int(knobs.get("base_vel", 90))
        vel_spread = max(0, int(knobs.get("velocity_spread", 6)))
        drop_prob = float(knobs.get("drop_prob", 0.0))

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(s * gate))

        register_octave = 4 + octave_shift
        root_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones

        pattern = euclid(pulses, total_steps, offset)
        events: list[AbstractEvent] = []
        for step_idx, fires in enumerate(pattern):
            if not fires:
                continue
            if drop_prob > 0 and rng.random() < drop_prob:
                continue
            tick = step_idx * s
            for interval in intervals:
                pitch = max(0, min(127, root_midi + interval))
                jitter = rng.randint(-vel_spread, vel_spread) if vel_spread else 0
                vel = max(1, min(127, base_vel + jitter))
                events.append(
                    Note(pitch=pitch, velocity=vel, duration_ticks=duration, tick=tick)
                )
        return events
