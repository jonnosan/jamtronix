"""``arp`` — chord-tone arpeggiator.

Cycles through a chord shape (root + 3rd + 5th by default) at a
configurable rate. Mode picks the order — ``up``, ``down``,
``up_down``, ``random``, or ``walk`` (random ± 1 step from the last
position). Octaves expand the range vertically.

Covers slackbeatz's ``sh101_arp`` + ``arp_walk`` in one algorithm.

Knobs:

* ``mode`` — ``up`` (default) / ``down`` / ``up_down`` / ``random`` / ``walk``.
* ``subdivision`` — grid the arp runs on. ``"16"`` (default) =
  16th-note arp; ``"8"`` = 8ths; ``"4"`` = quarters; ``"8t"`` = 8th
  triplets; ``"16t"`` = 16th triplets; ``"4t"`` / ``"32"`` / ``"32t"``
  also accepted (see :mod:`jtx.algorithms._subdivision`).
* ``octaves`` (1) — how many octaves the arp spans.
* ``chord_intervals`` — semitones above the root for each chord tone.
  Default ``[0, 3, 7]`` (minor triad); ``[0, 4, 7]`` for major,
  ``[0, 3, 7, 10]`` for minor 7, etc.
* ``gate`` (0.7) — note length as a fraction of the chosen subdivision.
* ``base_vel`` (95).
* ``octave`` (0) — register shift; default 0 = octave 4.
* ``pitch_cycle_bars`` (``"off"``) — loop the random pitch picks in
  ``random`` / ``walk`` modes on an N-bar cycle. No effect on the
  deterministic ``up`` / ``down`` / ``up_down`` modes. ``"4"`` makes a
  random-mode arp repeat as a 4-bar pattern.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._chords import intervals_for
from jtx.algorithms._cycle import parse_cycle_bars
from jtx.algorithms._subdivision import subdivision_grid
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note


class Arp(Algorithm):
    """Chord-tone arpeggiator. MIDI-naive — emits :class:`Note` events."""

    name: ClassVar[str] = "arp"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        jitter_rng = ctx.rng
        pitch_rng = ctx.rng_loop(parse_cycle_bars(knobs.get("pitch_cycle_bars", "off")))

        mode = str(knobs.get("mode", "up"))
        subdivision = str(knobs.get("subdivision", "16"))
        octaves = max(1, int(knobs.get("octaves", 1)))
        gate = float(knobs.get("gate", 0.7))
        base_vel = int(knobs.get("base_vel", 95))
        octave_shift = int(knobs.get("octave", 0))

        quality = str(knobs.get("quality", "minor"))
        intervals = intervals_for(quality)

        spacing, positions = subdivision_grid(subdivision, ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(spacing * gate))

        register_octave = 4 + octave_shift
        root_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones

        ladder: list[int] = []
        for octave in range(octaves):
            for interval in intervals:
                ladder.append(root_midi + octave * 12 + interval)

        if not ladder:
            return []

        sequence = _build_sequence(mode, ladder, positions, pitch_rng)

        events: list[AbstractEvent] = []
        for arp_idx in range(positions):
            pitch = max(0, min(127, sequence[arp_idx]))
            tick = arp_idx * spacing
            jitter = jitter_rng.randint(-3, 3)
            vel = max(1, min(127, base_vel + jitter))
            events.append(
                Note(pitch=pitch, velocity=vel, duration_ticks=duration, tick=tick)
            )

        return events


def _build_sequence(mode: str, ladder: list[int], positions: int, rng: object) -> list[int]:
    """Return one pitch per arp position, cycling the ladder in *mode*."""
    import random as _random

    rng_random = rng if isinstance(rng, _random.Random) else _random.Random()

    if mode == "up":
        return [ladder[i % len(ladder)] for i in range(positions)]
    if mode == "down":
        return [ladder[(-i - 1) % len(ladder)] for i in range(positions)]
    if mode == "up_down":
        cycle = ladder + ladder[-2:0:-1]  # up, then down without re-doubling top/bottom
        if not cycle:
            cycle = ladder
        return [cycle[i % len(cycle)] for i in range(positions)]
    if mode == "random":
        return [ladder[rng_random.randrange(len(ladder))] for _ in range(positions)]
    if mode == "walk":
        out: list[int] = []
        idx = 0
        for _ in range(positions):
            out.append(ladder[idx])
            delta = rng_random.choice([-1, 1])
            idx = max(0, min(len(ladder) - 1, idx + delta))
        return out
    raise ValueError(f"arp: unknown mode {mode!r} (expected up | down | up_down | random | walk)")
