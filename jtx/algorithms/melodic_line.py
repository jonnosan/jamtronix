"""``melodic_line`` — step-sequenced scale-walk riff.

Picks notes from the active scale at each position. Each position picks
randomly from a configurable palette of scale degrees (default
``[0, 2, 4, 5]`` — root, 3rd, 5th, 6th — a safe melodic shape).
Per-position "drop" probability controls density; the algorithm doesn't
implement motif memory in v1 (that's a future refinement once the
GUI lets us audition results), but bar-level reproducibility still
holds via ``ctx.rng``.

Covers slackbeatz's ``rolling`` / ``gallop`` / ``mellow_pick`` /
``rhodes_phrase`` / ``acid_lead`` / ``psy_lead`` in one knob-driven
algorithm.

Knobs:

* ``drop_prob`` (0.5) — chance any position is silent.
* ``subdivision`` (``"16"``) — grid the line walks on; ``"16t"`` /
  ``"8t"`` etc. turn the whole line into a triplet phrase.
* ``triplet_prob`` (0.0) — chance each beat (quarter) gets replaced by
  a triplet-grid micro-roll. Each triplet position rolls fresh against
  drop_prob + palette. Defaults to ``"16t"`` triplets; override via
  ``triplet_subdiv`` (``"8t"``, ``"32t"`` also valid).
* ``triplet_subdiv`` (``"16t"``) — triplet grid used for inserted rolls.
* ``degree_palette`` — list of scale degrees to draw from. Negative
  degrees go below the root, positive above. Default ``[0, 2, 4, 5]``.
* ``octave`` (0) — register shift; default 0 = octave 4 (lead range).
* ``gate`` (0.5) — note length as a fraction of position width.
* ``base_vel`` (90).
* ``intensity`` (1.0).
* ``passing_prob`` (0.0) — chance of inserting a chromatic neighbour
  between consecutive notes (acid / psy lead flavour).
"""

from __future__ import annotations

import random
from typing import ClassVar

from jtx.algorithms._palettes import palette_for
from jtx.algorithms._subdivision import subdivision_grid
from jtx.algorithms._theory import note_to_midi, scale_intervals
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn


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
        triplet_prob = float(knobs.get("triplet_prob", 0.0))

        subdivision = str(knobs.get("subdivision", "16"))
        triplet_subdiv = str(knobs.get("triplet_subdiv", "16t"))

        palette = palette_for(str(knobs.get("palette", "tones_only")))

        base_spacing, base_positions = subdivision_grid(subdivision, ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(base_spacing * gate))

        scale = scale_intervals(ctx.key.scale)
        register_octave = 4 + octave_shift
        tonic_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones

        events: list[Event] = []
        prev_pitch: int | None = None

        # Build a "skip" mask for positions that fall inside an inserted
        # triplet beat (so they don't double up with the base grid).
        triplet_starts: list[int] = []
        triplet_end_ticks: list[int] = []
        if triplet_prob > 0:
            beats_per_bar = ctx.ticks_per_bar // ctx.ppq
            for beat in range(beats_per_bar):
                if rng.random() < triplet_prob:
                    triplet_starts.append(beat * ctx.ppq)
                    triplet_end_ticks.append((beat + 1) * ctx.ppq)

        def _inside_triplet(tick: int) -> bool:
            return any(
                start <= tick < end
                for start, end in zip(triplet_starts, triplet_end_ticks, strict=True)
            )

        # Base grid pass.
        for position in range(base_positions):
            tick = position * base_spacing
            if _inside_triplet(tick):
                continue
            note = _roll_note(
                rng=rng,
                drop_prob=drop_prob,
                palette=palette,
                scale=scale,
                tonic_midi=tonic_midi,
                base_vel=base_vel,
                intensity=intensity,
            )
            if note is None:
                prev_pitch = None
                continue
            pitch, vel = note
            _emit_note(
                events,
                channel=self.midi_channel,
                tick=tick,
                pitch=pitch,
                velocity=vel,
                duration=duration,
                passing_prob=passing_prob,
                base_spacing=base_spacing,
                prev_pitch=prev_pitch,
                rng=rng,
            )
            prev_pitch = pitch

        # Triplet inserts — each beat that won the roll gets three
        # independently-rolled positions on the triplet grid.
        if triplet_starts:
            triplet_spacing, _ = subdivision_grid(triplet_subdiv, ctx.ticks_per_bar, ctx.ppq)
            for start in triplet_starts:
                for i in range(3):
                    tick = start + i * triplet_spacing
                    if tick >= ctx.ticks_per_bar:
                        break
                    note = _roll_note(
                        rng=rng,
                        drop_prob=drop_prob,
                        palette=palette,
                        scale=scale,
                        tonic_midi=tonic_midi,
                        base_vel=base_vel,
                        intensity=intensity,
                    )
                    if note is None:
                        prev_pitch = None
                        continue
                    pitch, vel = note
                    triplet_duration = max(1, int(triplet_spacing * gate))
                    _emit_note(
                        events,
                        channel=self.midi_channel,
                        tick=tick,
                        pitch=pitch,
                        velocity=vel,
                        duration=triplet_duration,
                        passing_prob=0.0,  # no passing tones inside triplet bursts
                        base_spacing=triplet_spacing,
                        prev_pitch=prev_pitch,
                        rng=rng,
                    )
                    prev_pitch = pitch

        events.sort(key=lambda e: e.tick)
        return events


def _roll_note(
    *,
    rng: random.Random,
    drop_prob: float,
    palette: tuple[int, ...] | list[int],
    scale: tuple[int, ...],
    tonic_midi: int,
    base_vel: int,
    intensity: float,
) -> tuple[int, int] | None:
    """One roll against drop_prob + palette; ``None`` on a rest."""
    if rng.random() < drop_prob:
        return None
    degree = palette[rng.randrange(len(palette))]
    pitch = tonic_midi + _degree_to_semitones(degree, scale)
    pitch = max(0, min(127, pitch))
    jitter = rng.randint(-5, 5)
    vel = max(1, min(127, int(base_vel * intensity) + jitter))
    return pitch, vel


def _emit_note(
    events: list[Event],
    *,
    channel: int,
    tick: int,
    pitch: int,
    velocity: int,
    duration: int,
    passing_prob: float,
    base_spacing: int,
    prev_pitch: int | None,
    rng: random.Random,
) -> None:
    if (
        passing_prob > 0
        and prev_pitch is not None
        and abs(pitch - prev_pitch) >= 2
        and rng.random() < passing_prob
    ):
        direction = 1 if pitch > prev_pitch else -1
        passing_pitch = max(0, min(127, pitch - direction))
        passing_tick = max(0, tick - base_spacing // 4)
        events.append(
            NoteOn(
                tick=passing_tick,
                channel=channel,
                note=passing_pitch,
                velocity=max(1, velocity - 20),
            )
        )
        events.append(NoteOff(tick=tick - 1, channel=channel, note=passing_pitch))

    events.append(NoteOn(tick=tick, channel=channel, note=pitch, velocity=velocity))
    events.append(NoteOff(tick=tick + duration, channel=channel, note=pitch))


def _degree_to_semitones(degree: int, scale: tuple[int, ...]) -> int:
    """Resolve a (possibly negative, possibly multi-octave) scale degree.

    Degree 0 = root; degree 7 = root one octave up; degree -1 = the
    pitch just below the root (= scale[-1] one octave down).
    """
    octaves, idx = divmod(degree, len(scale))
    return octaves * 12 + scale[idx]
