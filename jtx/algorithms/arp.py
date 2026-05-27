"""``arp`` — chord-tone arpeggiator.

Cycles through a chord shape (root + 3rd + 5th by default) at a
configurable rate. Mode picks the order — ``up``, ``down``,
``up_down``, ``random``, or ``walk`` (random ± 1 step from the last
position). Octaves expand the range vertically.

Covers slackbeatz's ``sh101_arp`` + ``arp_walk`` in one algorithm.

Knobs:

* ``mode`` — ``up`` (default) / ``down`` / ``up_down`` / ``random`` / ``walk``.
* ``rate_steps`` — number of 16th-note steps between successive notes
  (default 1 = 16th-note arp; 2 = 8th; 4 = quarter).
* ``octaves`` (1) — how many octaves the arp spans.
* ``chord_intervals`` — semitones above the root for each chord tone.
  Default ``[0, 3, 7]`` (minor triad); ``[0, 4, 7]`` for major,
  ``[0, 3, 7, 10]`` for minor 7, etc.
* ``gate`` (0.7).
* ``base_vel`` (95).
* ``octave`` (0) — register shift; default 0 = octave 4.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn

_DEFAULT_INTERVALS: tuple[int, ...] = (0, 3, 7)


class Arp(Algorithm):
    """Chord-tone arpeggiator."""

    name: ClassVar[str] = "arp"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        mode = str(knobs.get("mode", "up"))
        rate_steps = max(1, int(knobs.get("rate_steps", 1)))
        octaves = max(1, int(knobs.get("octaves", 1)))
        gate = float(knobs.get("gate", 0.7))
        base_vel = int(knobs.get("base_vel", 95))
        octave_shift = int(knobs.get("octave", 0))

        raw_intervals = knobs.get("chord_intervals", list(_DEFAULT_INTERVALS))
        if not isinstance(raw_intervals, list) or not raw_intervals:
            intervals: tuple[int, ...] = _DEFAULT_INTERVALS
        else:
            intervals = tuple(int(i) for i in raw_intervals)

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(s * rate_steps * gate))

        register_octave = 4 + octave_shift
        root_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones

        # Build the ladder of pitches: each interval × each octave.
        ladder: list[int] = []
        for octave in range(octaves):
            for interval in intervals:
                ladder.append(root_midi + octave * 12 + interval)

        if not ladder:
            return []

        sequence = _build_sequence(mode, ladder, total_steps, rate_steps, rng)

        events: list[Event] = []
        for arp_idx, step in enumerate(range(0, total_steps, rate_steps)):
            pitch = sequence[arp_idx]
            pitch = max(0, min(127, pitch))
            tick = step * s
            jitter = rng.randint(-3, 3)
            vel = max(1, min(127, base_vel + jitter))
            events.append(NoteOn(tick=tick, channel=self.midi_channel, note=pitch, velocity=vel))
            events.append(NoteOff(tick=tick + duration, channel=self.midi_channel, note=pitch))

        return events


def _build_sequence(
    mode: str, ladder: list[int], total_steps: int, rate_steps: int, rng: object
) -> list[int]:
    """Return one pitch per arp step, cycling the ladder in *mode*."""
    import random as _random

    rng_random = rng if isinstance(rng, _random.Random) else _random.Random()
    n_arp_steps = (total_steps + rate_steps - 1) // rate_steps

    if mode == "up":
        return [ladder[i % len(ladder)] for i in range(n_arp_steps)]
    if mode == "down":
        return [ladder[(-i - 1) % len(ladder)] for i in range(n_arp_steps)]
    if mode == "up_down":
        cycle = ladder + ladder[-2:0:-1]  # up, then down without re-doubling top/bottom
        if not cycle:
            cycle = ladder
        return [cycle[i % len(cycle)] for i in range(n_arp_steps)]
    if mode == "random":
        return [ladder[rng_random.randrange(len(ladder))] for _ in range(n_arp_steps)]
    if mode == "walk":
        out: list[int] = []
        idx = 0
        for _ in range(n_arp_steps):
            out.append(ladder[idx])
            delta = rng_random.choice([-1, 1])
            idx = max(0, min(len(ladder) - 1, idx + delta))
        return out
    raise ValueError(f"arp: unknown mode {mode!r} (expected up | down | up_down | random | walk)")
