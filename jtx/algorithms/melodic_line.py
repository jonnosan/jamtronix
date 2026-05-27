"""``melodic_line`` — step-sequenced scale-walk riff.

Picks notes from the active scale at each step. Each step picks
randomly from a configurable palette of scale degrees (default
``[0, 2, 4, 5]`` — root, 3rd, 5th, 6th — a safe melodic shape).
Per-step "drop" probability controls density; the algorithm doesn't
implement motif memory in v1 (that's a future refinement once the
GUI lets us audition results), but bar-level reproducibility still
holds via ``ctx.rng``.

Covers slackbeatz's ``rolling`` / ``gallop`` / ``mellow_pick`` /
``rhodes_phrase`` / ``acid_lead`` / ``psy_lead`` in one knob-driven
algorithm.

Knobs:

* ``drop_prob`` (0.5) — chance any step is silent.
* ``degree_palette`` — list of scale degrees to draw from. Negative
  degrees go below the root, positive above. Default ``[0, 2, 4, 5]``.
* ``octave`` (0) — register shift; default 0 = octave 4 (lead range).
* ``gate`` (0.5) — note length as a fraction of step.
* ``base_vel`` (90).
* ``intensity`` (1.0).
* ``passing_prob`` (0.0) — chance of inserting a chromatic neighbour
  between consecutive notes (acid / psy lead flavour).
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi, scale_intervals
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn

_DEFAULT_PALETTE: tuple[int, ...] = (0, 2, 4, 5)


class MelodicLine(Algorithm):
    """Step-sequenced melodic line drawing from a scale-degree palette."""

    name: ClassVar[str] = "melodic_line"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        drop_prob = float(knobs.get("drop_prob", 0.5))
        octave_shift = int(knobs.get("octave", 0))
        gate = float(knobs.get("gate", 0.5))
        base_vel = int(knobs.get("base_vel", 90))
        intensity = float(knobs.get("intensity", 1.0))
        passing_prob = float(knobs.get("passing_prob", 0.0))

        raw_palette = knobs.get("degree_palette", list(_DEFAULT_PALETTE))
        if not isinstance(raw_palette, list) or not raw_palette:
            palette: tuple[int, ...] = _DEFAULT_PALETTE
        else:
            palette = tuple(int(d) for d in raw_palette)

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(s * gate))

        scale = scale_intervals(ctx.key.scale)
        register_octave = 4 + octave_shift
        tonic_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones

        events: list[Event] = []
        prev_pitch: int | None = None

        for step in range(total_steps):
            if rng.random() < drop_prob:
                continue
            degree = palette[rng.randrange(len(palette))]
            pitch = tonic_midi + _degree_to_semitones(degree, scale)
            pitch = max(0, min(127, pitch))

            tick = step * s
            jitter = rng.randint(-5, 5)
            vel = max(1, min(127, int(base_vel * intensity) + jitter))

            # Optional chromatic neighbour just before this note.
            if (
                passing_prob > 0
                and prev_pitch is not None
                and abs(pitch - prev_pitch) >= 2
                and rng.random() < passing_prob
            ):
                direction = 1 if pitch > prev_pitch else -1
                passing_pitch = max(0, min(127, pitch - direction))
                passing_tick = max(0, tick - s // 4)
                events.append(
                    NoteOn(
                        tick=passing_tick,
                        channel=self.midi_channel,
                        note=passing_pitch,
                        velocity=max(1, vel - 20),
                    )
                )
                events.append(
                    NoteOff(
                        tick=tick - 1,
                        channel=self.midi_channel,
                        note=passing_pitch,
                    )
                )

            events.append(NoteOn(tick=tick, channel=self.midi_channel, note=pitch, velocity=vel))
            events.append(NoteOff(tick=tick + duration, channel=self.midi_channel, note=pitch))
            prev_pitch = pitch

        return events


def _degree_to_semitones(degree: int, scale: tuple[int, ...]) -> int:
    """Resolve a (possibly negative, possibly multi-octave) scale degree.

    Degree 0 = root; degree 7 = root one octave up; degree -1 = the
    pitch just below the root (= scale[-1] one octave down).
    """
    octaves, idx = divmod(degree, len(scale))
    return octaves * 12 + scale[idx]
