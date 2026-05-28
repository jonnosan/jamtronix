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
* ``polyrhythm_subdiv`` — subdivision grid for the polyrhythm layer
  (``"16"`` default, or ``"8t"`` / ``"16t"`` for triplet hat/perc
  layers — signature deep-techno move). The N pulses are euclid-
  distributed across the chosen grid.
* ``roll_pos`` — when to fire a triplet roll fill: ``"none"`` (default)
  / ``"last_beat"`` (every bar's beat 4) / ``"last_bar_of_4"``
  (bar % 4 == 3) / ``"last_bar_of_8"`` (bar % 8 == 7) /
  ``"random_sparse"`` (1-in-8 chance per bar).
* ``roll_subdiv`` (``"16t"``) — subdivision grid for the roll fill.
* ``roll_depth`` (0.6) — fraction of roll-grid positions that actually
  fire. ``1.0`` = continuous fill; ``0.3`` = sparse stutter.
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
from jtx.algorithms._subdivision import subdivision_grid
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Hit
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
    # Percussion expansion: clave / conga / cowbell / shaker / tamb.
    # Defaults tuned for deep-techno + acid + psy percussion grooves.
    "clave": {"pulses": 5, "offset": 0, "velocity": 92},
    "conga_hi": {"pulses": 4, "offset": 2, "velocity": 90},
    "conga": {"pulses": 4, "offset": 2, "velocity": 90},
    "conga_lo": {"pulses": 3, "offset": 7, "velocity": 96},
    "cowbell": {"pulses": 4, "offset": 1, "velocity": 88},
    "cb": {"pulses": 4, "offset": 1, "velocity": 88},
    "shaker": {"pulses": 16, "offset": 0, "velocity": 70},
    "shk": {"pulses": 16, "offset": 0, "velocity": 70},
    "tamb": {"pulses": 2, "offset": 4, "velocity": 80},
    "wood": {"pulses": 4, "offset": 2, "velocity": 88},
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
    # 3-2 son clave: 0, 3, 6, 10, 12 (the "bossa" / Latin foundation
    # underneath a lot of deep-techno percussion grooves).
    "clave": [0, 3, 6, 10, 12],
    # Cascara on cowbell — standard 3-2 cowbell pattern under clave.
    "cowbell": [0, 2, 4, 6, 7, 10, 12, 14],
    "cb": [0, 2, 4, 6, 7, 10, 12, 14],
    # Conga tumbao — low conga on the and-of-2 and 4, high open on 2 and 4.
    "conga_lo": [3, 11],
    "conga_hi": [4, 6, 12, 14],
    "conga": [4, 6, 12, 14],
    # Tambourine on the and-of-each-beat.
    "tamb": [2, 6, 10, 14],
    # Wood block / claves — bossa rim.
    "wood": [0, 4, 6, 10, 12],
    # Shaker continuous 16ths.
    "shaker": list(range(0, 16, 1)),
    "shk": list(range(0, 16, 1)),
}

_BEAT_STRIDE = 4  # at 16 steps/bar, beats are on every 4th step

_ROLL_POSITIONS = ("none", "last_beat", "last_bar_of_4", "last_bar_of_8", "random_sparse")


def _roll_active(roll_pos: str, bar_index: int, rng: random.Random) -> bool:
    """True if the chosen roll-pos selector fires on *bar_index*."""
    if roll_pos == "none":
        return False
    if roll_pos == "last_beat":
        return True  # every bar fires on its own last beat
    if roll_pos == "last_bar_of_4":
        return bar_index % 4 == 3
    if roll_pos == "last_bar_of_8":
        return bar_index % 8 == 7
    if roll_pos == "random_sparse":
        return rng.random() < 0.125  # ~1 in 8 bars
    raise ValueError(
        f"drum_pattern: unknown roll_pos {roll_pos!r} (expected one of {_ROLL_POSITIONS})"
    )


# Drum NoteOffs are fired a fixed short offset after the NoteOn, just
# for MIDI-protocol correctness. Drum samples ignore note-off; any
# release-time character lives in the sample's internal envelope.
_NOTE_OFF_OFFSET_TICKS = 30


class DrumPattern(Algorithm):
    """Single-piece drum generator (euclid / four_floor / break).

    MIDI-naive: emits :class:`Hit` events tagged with the voice's
    instrument name. The voicing stage resolves the instrument to
    ``(slot.midi_channel, slot.note)``.
    """

    name: ClassVar[str] = "drum_pattern"

    def __init__(self, *, piece: str, instrument_name: str | None = None) -> None:
        self.piece = piece.lower()
        # Hit.instrument is None on a single-piece drum slot (voicing
        # uses slot.note + slot.midi_channel). We accept an explicit
        # name for tests / future drum_kit-style reuse.
        self._instrument_name = instrument_name

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
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
        # Fixed-length NoteOffs for MIDI-protocol housekeeping only —
        # drum samples ignore note-off and play their internal envelope.
        duration = _NOTE_OFF_OFFSET_TICKS

        pattern = self._make_pattern(style, knobs, defaults, total_steps)
        events: list[AbstractEvent] = []

        for step, hit in enumerate(pattern):
            if not hit:
                continue
            tick = step * s
            curve_mult = _vel_curve_multiplier(
                vel_curve, step, total_steps, vel_curve_depth, ctx.rng
            )
            step_vel = int(round(velocity * curve_mult))
            events.append(self._hit(tick, step_vel, duration))

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
                    events.append(self._hit(step * s, ghost_vel, duration))

        if polyrhythm > 0:
            poly_vel = max(1, int(velocity * 0.65))
            poly_subdiv = str(knobs.get("polyrhythm_subdiv", "16"))
            poly_spacing, poly_positions = subdivision_grid(poly_subdiv, ctx.ticks_per_bar, ctx.ppq)
            poly_pulses = min(polyrhythm, poly_positions)
            poly_pattern = euclid_pattern(poly_pulses, poly_positions, 0)
            base_hit_ticks = {step * s for step, hit in enumerate(pattern) if hit}
            for poly_idx, hit in enumerate(poly_pattern):
                if not hit:
                    continue
                tick = poly_idx * poly_spacing
                if tick in base_hit_ticks:
                    continue  # don't double-hit the main pattern
                events.append(self._hit(tick, poly_vel, duration))

        roll_pos = str(knobs.get("roll_pos", "none"))
        if roll_pos != "none":
            events.extend(self._make_roll(roll_pos, knobs, ctx, velocity, duration))

        return events

    def _make_roll(
        self,
        roll_pos: str,
        knobs: KnobDict,
        ctx: BarContext,
        velocity: int,
        duration: int,
    ) -> list[AbstractEvent]:
        if not _roll_active(roll_pos, ctx.bar_index, ctx.rng):
            return []
        roll_subdiv = str(knobs.get("roll_subdiv", "16t"))
        roll_depth = float(knobs.get("roll_depth", 0.6))
        spacing, positions = subdivision_grid(roll_subdiv, ctx.ticks_per_bar, ctx.ppq)
        beats_per_bar = ctx.ticks_per_bar // ctx.ppq
        roll_start = (beats_per_bar - 1) * ctx.ppq
        roll_end = ctx.ticks_per_bar
        events: list[AbstractEvent] = []
        for i in range(positions):
            tick = i * spacing
            if tick < roll_start or tick >= roll_end:
                continue
            if ctx.rng.random() >= roll_depth:
                continue
            window_progress = (tick - roll_start) / max(1, roll_end - roll_start)
            vel_mult = 0.7 + 0.4 * window_progress
            roll_vel = max(1, min(127, int(velocity * vel_mult)))
            events.append(self._hit(tick, roll_vel, duration))
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

    def _hit(self, tick: int, velocity: int, duration: int) -> Hit:
        return Hit(
            instrument=self._instrument_name,
            velocity=max(1, min(127, velocity)),
            duration_ticks=duration,
            tick=tick,
        )


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
