"""``drum_pattern`` — unified euclidean / four-on-floor / breakbeat drum.

One voice = one drum piece (kick / snare / hat / clap / …). The
algorithm emits hits for that single piece at the channel + note bound
at construction time. A song with kick + snare + hat is three drum
voices all running ``drum_pattern`` with their own piece-name +
``style`` knob.

Knobs (all overridable per part):

* ``style`` — ``"four_floor"`` (default), ``"euclid"``, or ``"break"``.
* ``pulses`` / ``offset`` — euclid parameters; default by piece.
* ``velocity`` — base note-on velocity; default by piece.
* ``ghost`` — 0..1 probability of a ghost hit on each off-step.
* ``ghost_velocity_ratio`` — multiplier on ``velocity`` for ghost hits.
* ``polyrhythm`` — secondary euclid layer with N pulses across the bar
  at softer velocity (0 = off).
* ``duration_ticks`` — note-off offset from note-on; default ``step // 2``.
* ``vel_curve`` — algorithmic per-step velocity shape. One of
  ``flat`` (default) / ``ramp_up`` / ``ramp_down`` / ``arc`` /
  ``valley`` / ``pulse`` / ``drift`` (bar-seeded random walk) /
  ``surprise`` (bigger bar-seeded jumps). Knob-style — pick a curve,
  sweep the depth, listen. ``drift`` + ``surprise`` use the bar RNG
  so the same seed always lands the same accidents.
* ``vel_curve_depth`` (0.15) — how strongly the curve modulates base
  velocity. ``0`` flattens any curve choice; ``1`` is the wildest.

Feel knobs (swing, humanize, vel_jitter, …) are applied later by the
scheduler-level post-emit pass — algorithms emit "ideal" hits.
"""

from __future__ import annotations

import random
from typing import ClassVar

from jtx.algorithms._euclid import euclid as euclid_pattern
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn
from jtx.model.song import KnobDict

# Per-piece (pulses, offset, velocity) defaults at 16 steps/bar.
# Beats are at 0/4/8/12; offset=4 ⇒ first hit on beat 2 (backbeat snare).
_PIECE_DEFAULTS: dict[str, dict[str, int]] = {
    "kick": {"pulses": 4, "offset": 0, "velocity": 110},
    "bd": {"pulses": 4, "offset": 0, "velocity": 110},
    "snare": {"pulses": 2, "offset": 4, "velocity": 100},
    "sd": {"pulses": 2, "offset": 4, "velocity": 100},
    "clap": {"pulses": 2, "offset": 4, "velocity": 100},
    "hat": {"pulses": 8, "offset": 0, "velocity": 78},
    "hh": {"pulses": 8, "offset": 0, "velocity": 78},
    "hats": {"pulses": 8, "offset": 0, "velocity": 78},
    "ohat": {"pulses": 1, "offset": 14, "velocity": 88},
    "rim": {"pulses": 5, "offset": 3, "velocity": 95},
    "tom": {"pulses": 3, "offset": 8, "velocity": 95},
}

# Per-piece breakbeat patterns on a 16-step bar.
_BREAK_PATTERNS: dict[str, list[int]] = {
    # Amen-flavoured: kick on 0, 7, 10; snare on 4, 12, 14;
    # hats sixteenths; clap doubles snare.
    "kick": [0, 7, 10],
    "bd": [0, 7, 10],
    "snare": [4, 12, 14],
    "sd": [4, 12, 14],
    "clap": [4, 12, 14],
    "hat": list(range(0, 16, 1)),
    "hh": list(range(0, 16, 1)),
    "hats": list(range(0, 16, 1)),
}

_BEAT_STRIDE = 4  # at 16 steps/bar, beats are on every 4th step


class DrumPattern(Algorithm):
    """Single-piece drum generator (euclid / four_floor / break)."""

    name: ClassVar[str] = "drum_pattern"

    def __init__(self, *, piece: str, midi_channel: int, midi_note: int) -> None:
        self.piece = piece.lower()
        self.midi_channel = midi_channel
        self.midi_note = midi_note

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        defaults = _PIECE_DEFAULTS.get(self.piece, {})

        style = str(knobs.get("style", "four_floor"))
        velocity = int(knobs.get("velocity", defaults.get("velocity", 100)))
        ghost_prob = float(knobs.get("ghost", 0.0))
        ghost_ratio = float(knobs.get("ghost_velocity_ratio", 0.35))
        polyrhythm = int(knobs.get("polyrhythm", 0))

        # Algorithmic per-step velocity shaping (no per-step lists). The
        # curve modulates the base velocity by ``vel_curve_depth`` across
        # the bar; ``vel_curve_depth=0`` (or ``vel_curve="flat"``) is a
        # no-op. Curves available below.
        vel_curve = str(knobs.get("vel_curve", "flat"))
        vel_curve_depth = float(knobs.get("vel_curve_depth", 0.15))

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = int(knobs.get("duration_ticks", max(1, s // 2)))

        pattern = self._make_pattern(style, knobs, defaults, total_steps)
        events: list[Event] = []

        for step, hit in enumerate(pattern):
            if not hit:
                continue
            tick = step * s
            curve_mult = _vel_curve_multiplier(
                vel_curve, step, total_steps, vel_curve_depth, ctx.rng
            )
            step_vel = int(round(velocity * curve_mult))
            events.extend(self._note(tick, step_vel, duration))

        if ghost_prob > 0.0 and ghost_ratio > 0.0:
            ghost_vel = max(1, int(velocity * ghost_ratio))
            for step in range(total_steps):
                if pattern[step]:
                    continue
                # Ghost-hit candidates: syncopated off-steps. At 16
                # steps/bar that's the odd-numbered slots.
                if step % 2 == 0:
                    continue
                if ctx.rng.random() < ghost_prob:
                    events.extend(self._note(step * s, ghost_vel, duration))

        if polyrhythm > 0:
            poly_vel = max(1, int(velocity * 0.65))
            poly_pattern = euclid_pattern(polyrhythm, total_steps, 0)
            for step, hit in enumerate(poly_pattern):
                if hit and not pattern[step]:
                    events.extend(self._note(step * s, poly_vel, duration))

        return events

    def _make_pattern(
        self,
        style: str,
        knobs: KnobDict,
        defaults: dict[str, int],
        total_steps: int,
    ) -> list[bool]:
        if style == "four_floor":
            return [step % _BEAT_STRIDE == 0 for step in range(total_steps)]
        if style == "euclid":
            pulses = int(knobs.get("pulses", defaults.get("pulses", 4)))
            offset = int(knobs.get("offset", defaults.get("offset", 0)))
            return euclid_pattern(pulses, total_steps, offset)
        if style == "break":
            steps = _BREAK_PATTERNS.get(self.piece)
            if steps is None:
                # Fall back to euclid for unknown pieces.
                pulses = int(knobs.get("pulses", defaults.get("pulses", 4)))
                offset = int(knobs.get("offset", defaults.get("offset", 0)))
                return euclid_pattern(pulses, total_steps, offset)
            pattern = [False] * total_steps
            for st in steps:
                if 0 <= st < total_steps:
                    pattern[st] = True
            return pattern
        raise ValueError(
            f"drum_pattern: unknown style {style!r} (expected 'four_floor' | 'euclid' | 'break')"
        )

    def _note(self, tick: int, velocity: int, duration: int) -> list[Event]:
        v = max(1, min(127, velocity))
        return [
            NoteOn(tick=tick, channel=self.midi_channel, note=self.midi_note, velocity=v),
            NoteOff(tick=tick + duration, channel=self.midi_channel, note=self.midi_note),
        ]


def _vel_curve_multiplier(
    curve: str,
    step: int,
    total_steps: int,
    depth: float,
    rng: random.Random,
) -> float:
    """Algorithmic velocity-shape multiplier for a single step.

    The result is ``1.0`` on the flat curve or when depth is zero;
    otherwise the curve modulates around ``1.0`` with magnitude
    bounded by *depth*. Designed for the knobs-not-lists posture:
    pick a named curve, sweep the depth knob, listen.

    Probabilistic curves consume :class:`random.Random` so the output
    is bar-seed deterministic (same bar seed → same per-step
    multipliers across runs).
    """
    if depth <= 0 or curve == "flat":
        return 1.0
    progress = step / max(1, total_steps - 1)  # 0..1 across the bar
    if curve == "ramp_up":
        # Linear from 1 - depth/2 at step 0 to 1 + depth/2 at the end.
        return 1.0 + depth * (progress - 0.5)
    if curve == "ramp_down":
        return 1.0 + depth * (0.5 - progress)
    if curve == "arc":
        # Hump centred on the middle: 1 - depth/2 at edges, 1 + depth/2 at centre.
        return 1.0 - depth / 2 + depth * (4 * progress * (1 - progress))
    if curve == "valley":
        # Inverted arc: dip in the middle.
        return 1.0 + depth / 2 - depth * (4 * progress * (1 - progress))
    if curve == "pulse":
        # Every 4-step downbeat gets +depth, others stay flat.
        return 1.0 + depth if step % 4 == 0 else 1.0
    if curve == "drift":
        # Bar-seeded random walk — each step a small step ±depth/2
        # around 1.0. Same bar seed → same drift; turn the depth knob
        # and the walk gets wilder. Use ctx.rng so the walk is local
        # to this bar (and reproducible).
        # We seed-advance the rng per step so the walk is bar-stable.
        return 1.0 + depth * (rng.random() - 0.5)
    if curve == "surprise":
        # Bigger per-step shock: uniformly +/-depth (so a hit can be
        # very quiet or very loud, with no smooth curve constraint).
        # Combined with the bar-seeded rng this gives reproducible
        # "happy-accident" variations as the user explores.
        return 1.0 + depth * (rng.random() * 2 - 1) * 1.5
    raise ValueError(
        f"drum_pattern: unknown vel_curve {curve!r} "
        "(expected flat | ramp_up | ramp_down | arc | valley | pulse | drift | surprise)"
    )
