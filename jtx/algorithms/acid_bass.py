"""``acid_bass`` — TB-303-style step sequencer.

One bar at a time. 16 step slots by default; each step rolls dice to
decide:

* fire or rest (``1 - drop_prob`` chance of firing);
* root / octave-up / minor-third pitch (driven by knob probabilities);
* slide from previous note (``slide_prob`` chance) via CC 65/5;
* pitch-bend wobble (``bend`` ticks of pitchwheel around 0);
* note duration shaped by ``gate``.

``triplet_prob`` rolls per-beat: when it fires, the four 16ths in that
beat are replaced with three independently-rolled triplet positions
(``triplet_subdiv``, default ``"16t"``). Each triplet position runs the
same pitch/drop/accent rules — independent rolls, not a clone of one
host beat. Use sparingly: classic acid breakdown roll-into-the-drop
flavour at ``triplet_prob`` ≈ 0.05–0.12.

CC 74 (filter cutoff) + CC 71 (resonance) are emitted on every quarter
note as a sine LFO whose period is ``cycle`` bars; phase is anchored to
``ctx.bar_index`` so the LFO is continuous across bars. ``cycle=0``
silences the built-in LFO so an external LFO system can drive the same
CC without two sources fighting.

Accent every 4 steps (downbeat of each beat) gets +15 velocity — the
unmistakable acid accent pattern. On triplet beats the first triplet
position is the accent.

Slides land within the same bar only: the algorithm is stateless across
bars so it can't see the last note of the previous bar. In practice
that's fine — slide is most musical between consecutive close notes
and almost all acid lines have plenty of those inside one bar.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._subdivision import subdivision_grid
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend

# Pitch-pick probabilities once a step has been decided to fire.
_OCTAVE_UP_PROB = 0.20
_MINOR_THIRD_PROB = 0.10

# CC controller numbers (MIDI standard defaults). A voice slot's
# ``cc_map`` can remap any of these by function name — useful when the
# DAW target wants a different CC number on a specific instrument.
_DEFAULT_CC: dict[str, int] = {
    "portamento_time": 5,
    "filter_cutoff": 74,
    "resonance": 71,
    "portamento_on_off": 65,
}


class AcidBass(Algorithm):
    """TB-303 line: 16-step probabilistic, with CC74/71 + pitch-bend."""

    name: ClassVar[str] = "acid_bass"
    DEFAULT_CC: ClassVar[dict[str, int]] = dict(_DEFAULT_CC)
    """Function → CC number; mirrored on the class for setup-editor lookup."""

    def __init__(
        self,
        *,
        midi_channel: int,
        cc_map: dict[str, int] | None = None,
    ) -> None:
        self.midi_channel = midi_channel
        self._cc_map = dict(cc_map) if cc_map else {}

    def _cc(self, function: str) -> int:
        return int(self._cc_map.get(function, _DEFAULT_CC[function]))

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
                    cc=self._cc("portamento_on_off"),
                    value=127,
                )
            )
            events.append(
                ControlChange(
                    tick=0,
                    channel=self.midi_channel,
                    cc=self._cc("portamento_time"),
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
                        cc=self._cc("filter_cutoff"),
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
                            cc=self._cc("resonance"),
                            value=max(0, min(127, resonance)),
                        )
                    )

        # Note pattern — 16 steps probabilistic, with per-beat triplet
        # insertion if triplet_prob fires.
        triplet_prob = float(knobs.get("triplet_prob", 0.0))
        triplet_subdiv = str(knobs.get("triplet_subdiv", "16t"))

        # Decide which beats become triplet beats up-front.
        beats_per_bar = ctx.ticks_per_bar // ctx.ppq
        triplet_beats: set[int] = set()
        if triplet_prob > 0:
            for beat in range(beats_per_bar):
                if rng.random() < triplet_prob:
                    triplet_beats.add(beat)

        triplet_spacing = 0
        if triplet_beats:
            triplet_spacing, _ = subdivision_grid(triplet_subdiv, ctx.ticks_per_bar, ctx.ppq)

        prev_pitch: int | None = None
        for step in range(total_steps):
            beat = step // 4
            if beat in triplet_beats:
                # Skip the base 16ths for this beat; the triplet loop
                # below fills it in.
                continue
            if rng.random() < drop_prob:
                continue
            pitch = _roll_pitch(rng, root_pitch, octave_pitch, minor_third_pitch)
            tick = step * s
            is_accent = step % 4 == 0
            prev_pitch = _emit_acid_note(
                events,
                cc_fn=self._cc,
                channel=self.midi_channel,
                tick=tick,
                pitch=pitch,
                duration=duration,
                base_vel=base_vel,
                intensity=intensity,
                is_accent=is_accent,
                bend_amount=bend_amount,
                slide_prob=slide_prob,
                prev_pitch=prev_pitch,
                rng=rng,
            )

        # Triplet insertions — each fired beat gets 3 independent rolls.
        for beat in sorted(triplet_beats):
            beat_start = beat * ctx.ppq
            beat_prev_pitch: int | None = prev_pitch
            for i in range(3):
                tick = beat_start + i * triplet_spacing
                if tick >= ctx.ticks_per_bar:
                    break
                if rng.random() < drop_prob:
                    continue
                pitch = _roll_pitch(rng, root_pitch, octave_pitch, minor_third_pitch)
                tri_duration = max(1, int(triplet_spacing * gate))
                beat_prev_pitch = _emit_acid_note(
                    events,
                    cc_fn=self._cc,
                    channel=self.midi_channel,
                    tick=tick,
                    pitch=pitch,
                    duration=tri_duration,
                    base_vel=base_vel,
                    intensity=intensity,
                    is_accent=(i == 0),
                    bend_amount=bend_amount,
                    slide_prob=slide_prob,
                    prev_pitch=beat_prev_pitch,
                    rng=rng,
                )
            prev_pitch = beat_prev_pitch

        events.sort(key=lambda e: e.tick)
        return events


def _roll_pitch(rng: random.Random, root: int, octave_up: int, minor_third: int) -> int:
    roll = rng.random()
    if roll < _OCTAVE_UP_PROB:
        return octave_up
    if roll < _OCTAVE_UP_PROB + _MINOR_THIRD_PROB:
        return minor_third
    return root


def _emit_acid_note(
    events: list[Event],
    *,
    cc_fn: Callable[[str], int],
    channel: int,
    tick: int,
    pitch: int,
    duration: int,
    base_vel: int,
    intensity: float,
    is_accent: bool,
    bend_amount: int,
    slide_prob: float,
    prev_pitch: int | None,
    rng: random.Random,
) -> int:
    """Append one acid-bass note (with slide/bend) and return its pitch."""
    accent = 15 if is_accent else 0
    jitter = rng.randint(-4, 4)
    vel = max(1, min(127, int(base_vel * intensity) + jitter + accent))

    if slide_prob > 0 and prev_pitch is not None and prev_pitch != pitch:
        glide = 30 if rng.random() < slide_prob else 0
        events.append(
            ControlChange(
                tick=max(0, tick - 2),
                channel=channel,
                cc=cc_fn("portamento_time"),
                value=glide,
            )
        )

    if bend_amount > 0:
        events.append(
            PitchBend(
                tick=max(0, tick - 1),
                channel=channel,
                value=rng.randint(-bend_amount, bend_amount),
            )
        )
    clamped_pitch = max(0, min(127, pitch))
    events.append(NoteOn(tick=tick, channel=channel, note=clamped_pitch, velocity=vel))
    events.append(NoteOff(tick=tick + duration, channel=channel, note=clamped_pitch))
    if bend_amount > 0:
        events.append(PitchBend(tick=tick + duration, channel=channel, value=0))
    return pitch
