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

Feel knobs (swing, humanize, vel_jitter, …) are applied later by the
scheduler-level post-emit pass — algorithms emit "ideal" hits.
"""

from __future__ import annotations

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

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = int(knobs.get("duration_ticks", max(1, s // 2)))

        pattern = self._make_pattern(style, knobs, defaults, total_steps)
        events: list[Event] = []

        for step, hit in enumerate(pattern):
            if not hit:
                continue
            tick = step * s
            events.extend(self._note(tick, velocity, duration))

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
