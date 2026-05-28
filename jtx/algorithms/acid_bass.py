"""``acid_bass`` — TB-303-style step sequencer.

One bar at a time. 16 step slots by default; each step rolls dice to
decide:

* fire or rest (``1 - drop_prob`` chance of firing);
* root / octave-up / minor-third pitch (driven by knob probabilities);
* slide from previous note (``slide_prob`` chance) via ``glide`` Param;
* pitch-bend wobble (``bend`` ticks of pitchwheel around 0);
* note duration shaped by ``gate``.

``triplet_prob`` rolls per-beat: when it fires, the four 16ths in that
beat are replaced with three independently-rolled triplet positions
(``triplet_subdiv``, default ``"16t"``). Each triplet position runs the
same pitch/drop/accent rules — independent rolls, not a clone of one
host beat. Use sparingly: classic acid breakdown roll-into-the-drop
flavour at ``triplet_prob`` ≈ 0.05–0.12.

The cutoff (74) + resonance (71) sine LFO emits Param events on every
quarter note; phase is anchored to ``ctx.bar_index`` so the LFO is
continuous across bars. ``cycle=0`` silences the built-in LFO so an
external LFO system can drive the same parameter without two sources
fighting.

Accent every 4 steps (downbeat of each beat) gets +15 velocity — the
unmistakable acid accent pattern.

Schema v3: MIDI-naive. Emits :class:`Note` for note events,
:class:`Param` for cutoff / resonance / glide / glide_on / bend. The
voicing stage routes each Param via ``DEFAULT_PARAM_MAP`` /
``slot.parameter_map``.
"""

from __future__ import annotations

import math
import random
from typing import ClassVar

from jtx.algorithms._cycle import parse_cycle_bars
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._subdivision import subdivision_grid
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note, Param
from jtx.model.parameter_target import CCTarget, ParameterTarget

# Pitch-pick probabilities once a step has been decided to fire.
_OCTAVE_UP_PROB = 0.20
_MINOR_THIRD_PROB = 0.10


class AcidBass(Algorithm):
    """TB-303 line: 16-step probabilistic, with cutoff/resonance + bend."""

    name: ClassVar[str] = "acid_bass"
    DEFAULT_PARAM_MAP: ClassVar[dict[str, ParameterTarget]] = {
        "cutoff": CCTarget(74),
        "resonance": CCTarget(71),
        "glide": CCTarget(5),
        "glide_on": CCTarget(65),
        # "bend" deliberately omitted: routes to PitchBend directly.
    }

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        jitter_rng = ctx.rng
        pitch_rng = ctx.rng_loop(parse_cycle_bars(knobs.get("pitch_cycle_bars", "off")))
        rhythm_rng = ctx.rng_loop(parse_cycle_bars(knobs.get("rhythm_cycle_bars", "off")))

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

        register_octave = 2 + octave_shift
        root_raw = note_to_midi(ctx.key.tonic, register_octave)
        root_pitch = root_raw + ctx.chord_root_semitones
        minor_third_pitch = root_pitch + 3
        octave_pitch = root_pitch + 12

        events: list[AbstractEvent] = []

        # First bar of the part: latch portamento on (the per-note
        # glide toggle below decides whether each note actually slides).
        if slide_prob > 0 and ctx.bar_index == 0:
            events.append(Param(name="glide_on", value=127 / 127.0, tick=0))
            events.append(Param(name="glide", value=0.0, tick=0))

        if lfo_cycles > 0:
            cycle_ticks = max(1, lfo_cycles * ctx.ticks_per_bar)
            for q in range(ctx.ticks_per_bar // ctx.ppq):
                tick = q * ctx.ppq
                absolute_tick = ctx.bar_index * ctx.ticks_per_bar + tick
                theta = math.tau * absolute_tick / cycle_ticks
                lfo = (math.sin(theta) + 1.0) / 2.0
                cutoff = 30 + int(round(80 * lfo * intensity))
                cutoff = max(0, min(127, cutoff))
                events.append(Param(name="cutoff", value=cutoff / 127.0, tick=tick))
                if resonance_ceiling > 0:
                    res_lfo = (math.sin(theta + math.pi / 3) + 1.0) / 2.0
                    resonance = 40 + int(round((resonance_ceiling - 40) * res_lfo))
                    resonance = max(0, min(127, resonance))
                    events.append(
                        Param(name="resonance", value=resonance / 127.0, tick=tick)
                    )

        triplet_prob = float(knobs.get("triplet_prob", 0.0))
        triplet_subdiv = str(knobs.get("triplet_subdiv", "16t"))

        beats_per_bar = ctx.ticks_per_bar // ctx.ppq
        triplet_beats: set[int] = set()
        if triplet_prob > 0:
            for beat in range(beats_per_bar):
                if rhythm_rng.random() < triplet_prob:
                    triplet_beats.add(beat)

        triplet_spacing = 0
        if triplet_beats:
            triplet_spacing, _ = subdivision_grid(triplet_subdiv, ctx.ticks_per_bar, ctx.ppq)

        prev_pitch: int | None = None
        for step in range(total_steps):
            beat = step // 4
            if beat in triplet_beats:
                continue
            if rhythm_rng.random() < drop_prob:
                continue
            pitch = _roll_pitch(pitch_rng, root_pitch, octave_pitch, minor_third_pitch)
            tick = step * s
            is_accent = step % 4 == 0
            prev_pitch = _emit_acid_note(
                events,
                tick=tick,
                pitch=pitch,
                duration=duration,
                base_vel=base_vel,
                intensity=intensity,
                is_accent=is_accent,
                bend_amount=bend_amount,
                slide_prob=slide_prob,
                prev_pitch=prev_pitch,
                pitch_rng=pitch_rng,
                rhythm_rng=rhythm_rng,
                jitter_rng=jitter_rng,
            )

        for beat in sorted(triplet_beats):
            beat_start = beat * ctx.ppq
            beat_prev_pitch: int | None = prev_pitch
            for i in range(3):
                tick = beat_start + i * triplet_spacing
                if tick >= ctx.ticks_per_bar:
                    break
                if rhythm_rng.random() < drop_prob:
                    continue
                pitch = _roll_pitch(pitch_rng, root_pitch, octave_pitch, minor_third_pitch)
                tri_duration = max(1, int(triplet_spacing * gate))
                beat_prev_pitch = _emit_acid_note(
                    events,
                    tick=tick,
                    pitch=pitch,
                    duration=tri_duration,
                    base_vel=base_vel,
                    intensity=intensity,
                    is_accent=(i == 0),
                    bend_amount=bend_amount,
                    slide_prob=slide_prob,
                    prev_pitch=beat_prev_pitch,
                    pitch_rng=pitch_rng,
                    rhythm_rng=rhythm_rng,
                    jitter_rng=jitter_rng,
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
    events: list[AbstractEvent],
    *,
    tick: int,
    pitch: int,
    duration: int,
    base_vel: int,
    intensity: float,
    is_accent: bool,
    bend_amount: int,
    slide_prob: float,
    prev_pitch: int | None,
    pitch_rng: random.Random,
    rhythm_rng: random.Random,
    jitter_rng: random.Random,
) -> int:
    """Append one acid-bass note (with slide/bend) and return its pitch."""
    accent = 15 if is_accent else 0
    jitter = jitter_rng.randint(-4, 4)
    vel = max(1, min(127, int(base_vel * intensity) + jitter + accent))

    if slide_prob > 0 and prev_pitch is not None and prev_pitch != pitch:
        glide = 30 if rhythm_rng.random() < slide_prob else 0
        events.append(
            Param(name="glide", value=glide / 127.0, tick=max(0, tick - 2))
        )

    if bend_amount > 0:
        bend_value = pitch_rng.randint(-bend_amount, bend_amount)
        # Normalise to ±1 — voicing stage scales to PitchBend's 14-bit range.
        events.append(Param(name="bend", value=bend_value / 8192.0, tick=max(0, tick - 1)))

    clamped_pitch = max(0, min(127, pitch))
    events.append(
        Note(pitch=clamped_pitch, velocity=vel, duration_ticks=duration, tick=tick)
    )
    if bend_amount > 0:
        events.append(Param(name="bend", value=0.0, tick=tick + duration))
    return pitch
