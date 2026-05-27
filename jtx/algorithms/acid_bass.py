"""``acid_bass`` — TB-303-style step sequencer.

One bar at a time. 16 step slots; each step rolls dice to decide:

* fire or rest (``1 - drop_prob`` chance of firing);
* root / octave-up / minor-third pitch (driven by knob probabilities);
* slide from previous note (``slide_prob`` chance) via CC 65/5;
* pitch-bend wobble (``bend`` ticks of pitchwheel around 0);
* note duration shaped by ``gate``.

CC 74 (filter cutoff) + CC 71 (resonance) are emitted on every quarter
note as a sine LFO whose period is ``cycle`` bars; phase is anchored to
``ctx.bar_index`` so the LFO is continuous across bars. ``cycle=0``
silences the built-in LFO so an external LFO system can drive the same
CC without two sources fighting.

Accent every 4 steps (downbeat of each beat) gets +15 velocity — the
unmistakable acid accent pattern.

Slides land within the same bar only: the algorithm is stateless across
bars so it can't see the last note of the previous bar. In practice
that's fine — slide is most musical between consecutive close notes
and almost all acid lines have plenty of those inside one bar.
"""

from __future__ import annotations

import math
from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend

# Pitch-pick probabilities once a step has been decided to fire.
_OCTAVE_UP_PROB = 0.20
_MINOR_THIRD_PROB = 0.10

# CC controller numbers (MIDI standard).
_CC_PORTAMENTO_TIME = 5
_CC_FILTER_CUTOFF = 74
_CC_RESONANCE = 71
_CC_PORTAMENTO_ON_OFF = 65


class AcidBass(Algorithm):
    """TB-303 line: 16-step probabilistic, with CC74/71 + pitch-bend."""

    name: ClassVar[str] = "acid_bass"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        drop_prob = float(knobs.get("drop_prob", 0.35))
        slide_prob = float(knobs.get("slide_prob", 0.0))
        octave_shift = int(knobs.get("octave", 0))
        base_vel = int(knobs.get("base_vel", 90))
        intensity = float(knobs.get("intensity", 1.0))
        gate = float(knobs.get("gate", 0.75))
        bend_amount = int(knobs.get("bend", 80))
        lfo_cycles = int(knobs.get("cycle", 2))
        resonance_ceiling = int(knobs.get("resonance", 100))

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(s * gate))

        # Root at register-2 (TB-303 lead-bass territory: A2 ≈ 110 Hz).
        register_octave = 2 + octave_shift
        root_raw = note_to_midi(ctx.key.tonic, register_octave)
        root_pitch = root_raw + ctx.chord_root_semitones
        minor_third_pitch = root_pitch + 3
        octave_pitch = root_pitch + 12

        events: list[Event] = []

        # First bar of the part: latch portamento on (the per-note CC5
        # toggle then decides whether each note actually slides).
        if slide_prob > 0 and ctx.bar_index == 0:
            events.append(
                ControlChange(
                    tick=0,
                    channel=self.midi_channel,
                    cc=_CC_PORTAMENTO_ON_OFF,
                    value=127,
                )
            )
            events.append(
                ControlChange(
                    tick=0,
                    channel=self.midi_channel,
                    cc=_CC_PORTAMENTO_TIME,
                    value=0,
                )
            )

        # CC74 / CC71 sine LFO, one event per quarter note. Phase is
        # continuous across bars by anchoring to absolute tick.
        if lfo_cycles > 0:
            cycle_ticks = max(1, lfo_cycles * ctx.ticks_per_bar)
            for q in range(ctx.ticks_per_bar // ctx.ppq):
                tick = q * ctx.ppq
                absolute_tick = ctx.bar_index * ctx.ticks_per_bar + tick
                theta = math.tau * absolute_tick / cycle_ticks
                lfo = (math.sin(theta) + 1.0) / 2.0
                cutoff = 30 + int(round(80 * lfo * intensity))
                events.append(
                    ControlChange(
                        tick=tick,
                        channel=self.midi_channel,
                        cc=_CC_FILTER_CUTOFF,
                        value=max(0, min(127, cutoff)),
                    )
                )
                if resonance_ceiling > 0:
                    res_lfo = (math.sin(theta + math.pi / 3) + 1.0) / 2.0
                    resonance = 40 + int(round((resonance_ceiling - 40) * res_lfo))
                    events.append(
                        ControlChange(
                            tick=tick,
                            channel=self.midi_channel,
                            cc=_CC_RESONANCE,
                            value=max(0, min(127, resonance)),
                        )
                    )

        # Note pattern — 16 steps probabilistic.
        prev_pitch: int | None = None
        for step in range(total_steps):
            if rng.random() < drop_prob:
                continue
            roll = rng.random()
            if roll < _OCTAVE_UP_PROB:
                pitch = octave_pitch
            elif roll < _OCTAVE_UP_PROB + _MINOR_THIRD_PROB:
                pitch = minor_third_pitch
            else:
                pitch = root_pitch

            tick = step * s
            accent = 15 if step % 4 == 0 else 0
            jitter = rng.randint(-4, 4)
            vel = max(1, min(127, int(base_vel * intensity) + jitter + accent))

            # Slide: portamento time toggled per-note. Only meaningful on
            # pitch changes inside this bar (algorithm is bar-stateless).
            if slide_prob > 0 and prev_pitch is not None and prev_pitch != pitch:
                glide = 30 if rng.random() < slide_prob else 0
                events.append(
                    ControlChange(
                        tick=max(0, tick - 2),
                        channel=self.midi_channel,
                        cc=_CC_PORTAMENTO_TIME,
                        value=glide,
                    )
                )

            # Pitch-bend wobble before the note, recentre after.
            if bend_amount > 0:
                events.append(
                    PitchBend(
                        tick=max(0, tick - 1),
                        channel=self.midi_channel,
                        value=rng.randint(-bend_amount, bend_amount),
                    )
                )
            events.append(
                NoteOn(
                    tick=tick,
                    channel=self.midi_channel,
                    note=max(0, min(127, pitch)),
                    velocity=vel,
                )
            )
            events.append(
                NoteOff(
                    tick=tick + duration,
                    channel=self.midi_channel,
                    note=max(0, min(127, pitch)),
                )
            )
            if bend_amount > 0:
                events.append(
                    PitchBend(
                        tick=tick + duration,
                        channel=self.midi_channel,
                        value=0,
                    )
                )
            prev_pitch = pitch

        return events
