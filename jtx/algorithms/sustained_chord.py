"""``sustained_chord`` — long-gated polyphonic chord voicing.

Holds a chord shape across the bar. Pitches stack on the current
``ctx.chord_root_semitones`` so the chord follows the macro progression
when the resolver feeds it; with progression off (default), the chord
sits on the song tonic.

Covers slackbeatz's ``triad_sustain`` / ``pad_drift`` / ``sustained_dyad`` /
``atmos_pad`` in one knob-driven algorithm.

Knobs:

* ``intervals`` — semitones above the chord root for each chord tone.
  Default ``[0, 3, 7]`` (minor triad). ``[0, 7]`` = power chord;
  ``[0, 3, 7, 10]`` = m7; ``[0, 4, 7, 11]`` = maj7.
* ``gate`` (0.95) — fraction of bar the chord holds.
* ``octave`` (0) — register shift; default 0 = octave 4 (pad register).
* ``base_vel`` (75) — pads sit a touch quieter than leads by default.
* ``velocity_spread`` (5) — random ±N per voice for slight humanisation.
* ``drift_prob`` (0.0) — chance one voice drops by an octave on this
  bar (pad_drift flavour).
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn

_DEFAULT_INTERVALS: tuple[int, ...] = (0, 3, 7)


class SustainedChord(Algorithm):
    """Long-gated polyphonic chord voicing."""

    name: ClassVar[str] = "sustained_chord"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        raw_intervals = knobs.get("intervals", list(_DEFAULT_INTERVALS))
        intervals = _coerce_intervals(raw_intervals)

        gate = float(knobs.get("gate", 0.95))
        octave_shift = int(knobs.get("octave", 0))
        base_vel = int(knobs.get("base_vel", 75))
        vel_spread = max(0, int(knobs.get("velocity_spread", 5)))
        drift_prob = float(knobs.get("drift_prob", 0.0))

        register_octave = 4 + octave_shift
        root_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones
        duration = max(1, int(ctx.ticks_per_bar * gate))

        # Decide if a voice drifts down an octave this bar.
        drift_index: int | None = None
        if drift_prob > 0 and intervals and rng.random() < drift_prob:
            drift_index = rng.randrange(len(intervals))

        events: list[Event] = []
        for idx, interval in enumerate(intervals):
            pitch = root_midi + interval
            if idx == drift_index:
                pitch -= 12
            pitch = max(0, min(127, pitch))
            jitter = rng.randint(-vel_spread, vel_spread) if vel_spread else 0
            vel = max(1, min(127, base_vel + jitter))
            events.append(NoteOn(tick=0, channel=self.midi_channel, note=pitch, velocity=vel))
            events.append(NoteOff(tick=duration, channel=self.midi_channel, note=pitch))
        return events


class ChordStab(Algorithm):
    """Short-gated chord on a configurable step list."""

    name: ClassVar[str] = "chord_stab"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        raw_intervals = knobs.get("intervals", list(_DEFAULT_INTERVALS))
        intervals = _coerce_intervals(raw_intervals)

        raw_steps = knobs.get("steps", [2, 6, 10, 14])  # off-beat 16ths
        if not isinstance(raw_steps, list):
            raise TypeError(f"chord_stab: 'steps' must be a list, got {type(raw_steps).__name__}")

        gate = float(knobs.get("gate", 0.4))
        octave_shift = int(knobs.get("octave", 0))
        base_vel = int(knobs.get("base_vel", 90))
        vel_spread = max(0, int(knobs.get("velocity_spread", 6)))
        drop_prob = float(knobs.get("drop_prob", 0.0))

        from jtx.algorithms._steps import step_ticks, steps_per_bar

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(s * gate))

        register_octave = 4 + octave_shift
        root_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones

        events: list[Event] = []
        for raw in raw_steps:
            step = int(raw)
            if not (0 <= step < total_steps):
                continue
            if drop_prob > 0 and rng.random() < drop_prob:
                continue
            tick = step * s
            for interval in intervals:
                pitch = max(0, min(127, root_midi + interval))
                jitter = rng.randint(-vel_spread, vel_spread) if vel_spread else 0
                vel = max(1, min(127, base_vel + jitter))
                events.append(
                    NoteOn(tick=tick, channel=self.midi_channel, note=pitch, velocity=vel)
                )
                events.append(NoteOff(tick=tick + duration, channel=self.midi_channel, note=pitch))
        return events


def _coerce_intervals(raw: object) -> tuple[int, ...]:
    if isinstance(raw, list) and raw:
        return tuple(int(i) for i in raw)
    return _DEFAULT_INTERVALS
