"""``reese_bass`` — held bass with rhythmic filter + detune modulation.

The classic "reese": two detuned saw oscillators held long, with CC-
driven filter wobble and detune-amount modulation to keep the sound
moving. ``acid_bass`` covers 303-style step lines; ``sub_drone`` covers
held root/fifth subs; ``reese_bass`` covers the modern dub-techno /
half-time bass that sits between them.

The patch on the receiving end is expected to map ``wobble_cc`` to
filter cutoff (default CC74) and ``detune_cc`` to the detune-amount of
its two oscillators (default modwheel, CC1 — the most common patch
routing). Both default to the GM-friendly choices but the per-voice
``cc_map`` can remap.

One NoteOn per bar at tick 0, held for ``gate`` of the bar; rhythmic
CC74 modulation on the chosen ``wobble_subdiv`` grid, smooth detune
LFO at a slower rate (``detune_cycle_bars``).

Knobs:

* ``gate`` (0.95) — note length as a fraction of the bar.
* ``wobble_subdiv`` (``"8"``) — subdivision the cutoff wobble runs on.
  ``"8t"`` or ``"16t"`` for triplet-feel reese.
* ``wobble_depth`` (0.7) — CC74 modulation depth (0..1; 1 = full
  ``[cutoff_min, cutoff_max]`` swing).
* ``wobble_phase`` (0.0) — initial phase of the wobble (0..1).
* ``cutoff_min`` (35), ``cutoff_max`` (110) — CC74 range.
* ``detune_depth`` (0.4) — modwheel modulation depth (0..1).
* ``detune_cycle_bars`` (2.0) — slow LFO period for the detune
  modulation; phase anchored to ``ctx.bar_index`` so it's continuous
  across bars.
* ``base_vel`` (95).
* ``octave`` (0) — register shift; default 0 = octave 1 (E1≈41Hz at A
  minor, classic reese register).
* ``bars_per_chord`` (2) — cell length for chord-following. Same idea
  as ``sub_drone``: root vs. fifth alternates every cell.
* ``fifth_prob`` (0.0) — per-bar chance the cell jumps to the fifth.
"""

from __future__ import annotations

import math
from typing import ClassVar

from jtx.algorithms._subdivision import subdivision_grid
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn

_DEFAULT_CC: dict[str, int] = {"filter_cutoff": 74, "detune": 1}


class ReeseBass(Algorithm):
    """Modulating wobble-bass with CC74 wobble + CC1 detune LFO."""

    name: ClassVar[str] = "reese_bass"
    DEFAULT_CC: ClassVar[dict[str, int]] = dict(_DEFAULT_CC)

    def __init__(self, *, midi_channel: int, cc_map: dict[str, int] | None = None) -> None:
        self.midi_channel = midi_channel
        self._cc_map = dict(cc_map) if cc_map else {}

    def _cc(self, function: str) -> int:
        return int(self._cc_map.get(function, _DEFAULT_CC[function]))

    def generate_bar(self, ctx: BarContext) -> list[Event]:
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

        # Register 1 by default — E1/A1 territory, classic reese range.
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

        events: list[Event] = [
            NoteOn(tick=0, channel=self.midi_channel, note=pitch, velocity=velocity),
            NoteOff(tick=duration, channel=self.midi_channel, note=pitch),
        ]

        # Cutoff wobble — sine-LFO sampled on the wobble subdivision grid.
        wobble_cc_num = self._cc("filter_cutoff")
        cutoff_centre = (cutoff_min + cutoff_max) / 2.0
        cutoff_amp = (cutoff_max - cutoff_min) / 2.0 * wobble_depth
        if cutoff_amp > 0:
            spacing, positions = subdivision_grid(wobble_subdiv, ctx.ticks_per_bar, ctx.ppq)
            for i in range(positions):
                tick = i * spacing
                # One full sine cycle across the bar at this subdivision.
                theta = math.tau * (i / positions + wobble_phase)
                value = cutoff_centre + cutoff_amp * math.sin(theta)
                events.append(
                    ControlChange(
                        tick=tick,
                        channel=self.midi_channel,
                        cc=wobble_cc_num,
                        value=max(0, min(127, int(round(value)))),
                    )
                )

        # Detune LFO — smooth slow sine across detune_cycle_bars, phase
        # anchored to absolute bar index so continuous across bars.
        if detune_depth > 0 and detune_cycle_bars > 0:
            detune_cc_num = self._cc("detune")
            cycle_ticks = max(1, int(detune_cycle_bars * ctx.ticks_per_bar))
            detune_samples = max(2, int(knobs.get("detune_samples_per_bar", 8)))
            step = max(1, ctx.ticks_per_bar // detune_samples)
            for i in range(detune_samples):
                tick = i * step
                absolute_tick = ctx.bar_index * ctx.ticks_per_bar + tick
                theta = math.tau * absolute_tick / cycle_ticks
                # 0..127 centred on 64, full swing scaled by detune_depth.
                value = 64 + 63 * detune_depth * math.sin(theta)
                events.append(
                    ControlChange(
                        tick=tick,
                        channel=self.midi_channel,
                        cc=detune_cc_num,
                        value=max(0, min(127, int(round(value)))),
                    )
                )

        return events
