"""``reese_bass`` — held bass with rhythmic filter + detune modulation.

The classic "reese": two detuned saw oscillators held long, with
cutoff wobble and detune-amount modulation to keep the sound moving.
``acid_bass`` covers 303-style step lines; ``sub_drone`` covers held
root/fifth subs; ``reese_bass`` covers the modern dub-techno /
half-time bass that sits between them.

Schema v3: MIDI-naive. One :class:`Note` per bar at tick 0, held for
``gate`` of the bar; :class:`Param` events drive the cutoff wobble +
detune LFO (the voice's parameter_map / DEFAULT_PARAM_MAP route to
the actual CC numbers).

Knobs:

* ``gate`` (0.95) — note length as a fraction of the bar.
* ``wobble_subdiv`` (``"8"``) — subdivision the cutoff wobble runs on.
* ``wobble_depth`` (0.7) — cutoff modulation depth (0..1).
* ``wobble_phase`` (0.0) — initial phase of the wobble (0..1).
* ``cutoff_min`` (35), ``cutoff_max`` (110) — cutoff range (0..127).
* ``detune_depth`` (0.4) — detune modulation depth (0..1).
* ``detune_cycle_bars`` (2.0) — slow LFO period; phase anchored to
  ``ctx.bar_index`` for cross-bar continuity.
* ``base_vel`` (95).
* ``octave`` (0) — register shift; default 0 = octave 1.
* ``bars_per_chord`` (2) — cell length for chord-following.
* ``fifth_prob`` (0.0) — per-bar chance the cell jumps to the fifth.
"""

from __future__ import annotations

import math
from typing import ClassVar

from jtx.algorithms._subdivision import subdivision_grid
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note, Param
from jtx.model.parameter_target import CCTarget, ParameterTarget


class ReeseBass(Algorithm):
    """Modulating wobble-bass with cutoff wobble + detune LFO."""

    name: ClassVar[str] = "reese_bass"
    DEFAULT_PARAM_MAP: ClassVar[dict[str, ParameterTarget]] = {
        "cutoff": CCTarget(74),
        "detune": CCTarget(1),
    }

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        gate = float(knobs.get("gate", 0.95))
        wobble_subdiv = str(knobs.get("wobble_subdiv", "8"))
        wobble_depth = float(knobs.get("wobble_depth", 0.7))
        wobble_phase = float(knobs.get("wobble_phase", 0.0))
        cutoff_min = max(0, min(127, int(knobs.get("cutoff_min", 35))))
        cutoff_max = max(0, min(127, int(knobs.get("cutoff_max", 110))))
        detune_depth = float(knobs.get("detune_depth", 0.4))
        detune_cycle_bars = float(knobs.get("detune_cycle_bars", 2.0))
        base_vel = int(knobs.get("base_vel", 95))
        octave_shift = int(knobs.get("octave", 0))
        bars_per_chord = max(1, int(knobs.get("bars_per_chord", 2)))
        fifth_prob = float(knobs.get("fifth_prob", 0.0))

        register_octave = 1 + octave_shift
        root_raw = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones
        fifth_raw = root_raw + 7

        cell_position = (ctx.bar_index // bars_per_chord) % 2
        if fifth_prob > 0 and rng.random() < fifth_prob:
            pitch = fifth_raw
        else:
            pitch = fifth_raw if cell_position == 1 else root_raw
        pitch = max(0, min(127, pitch))

        velocity = max(1, min(127, base_vel + rng.randint(-3, 3)))
        duration = max(1, int(ctx.ticks_per_bar * gate))

        events: list[AbstractEvent] = [
            Note(pitch=pitch, velocity=velocity, duration_ticks=duration, tick=0)
        ]

        cutoff_centre = (cutoff_min + cutoff_max) / 2.0
        cutoff_amp = (cutoff_max - cutoff_min) / 2.0 * wobble_depth
        if cutoff_amp > 0:
            spacing, positions = subdivision_grid(wobble_subdiv, ctx.ticks_per_bar, ctx.ppq)
            for i in range(positions):
                tick = i * spacing
                theta = math.tau * (i / positions + wobble_phase)
                value = cutoff_centre + cutoff_amp * math.sin(theta)
                value_int = max(0, min(127, int(round(value))))
                events.append(Param(name="cutoff", value=value_int / 127.0, tick=tick))

        if detune_depth > 0 and detune_cycle_bars > 0:
            cycle_ticks = max(1, int(detune_cycle_bars * ctx.ticks_per_bar))
            detune_samples = max(2, int(knobs.get("detune_samples_per_bar", 8)))
            step = max(1, ctx.ticks_per_bar // detune_samples)
            for i in range(detune_samples):
                tick = i * step
                absolute_tick = ctx.bar_index * ctx.ticks_per_bar + tick
                theta = math.tau * absolute_tick / cycle_ticks
                value = 64 + 63 * detune_depth * math.sin(theta)
                value_int = max(0, min(127, int(round(value))))
                events.append(Param(name="detune", value=value_int / 127.0, tick=tick))

        return events
