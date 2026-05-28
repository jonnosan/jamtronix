"""``step_cc`` — step-sequenced CC modulator (rhythmic, not periodic).

``cc_lfo`` is shape-based: sine/tri/saw/random over a fixed period.
``step_cc`` is grid-based: one CC value per *step* of a configurable
subdivision, chosen by a named curve. Use when the filter (or any CC)
should follow a rhythmic pattern instead of a smooth wave.

Knobs-not-lists posture: pick a ``value_curve`` (same menu as
``drum_pattern.vel_curve``) and sweep ``depth``; the value at each
step is determined algorithmically from curve + bar-seeded RNG.

Knobs:

* ``cc`` (74) — controller number.
* ``subdivision`` (``"16"``) — step grid; ``"16t"`` / ``"8t"`` etc.
  give triplet-feel rhythmic CC sweeps.
* ``value_curve`` (``"ramp_up"``) — shape across the bar: ``flat`` /
  ``ramp_up`` / ``ramp_down`` / ``arc`` / ``valley`` / ``pulse`` /
  ``drift`` (bar-seeded random walk) / ``surprise``.
* ``cc_min`` (40), ``cc_max`` (110) — CC value range.
* ``depth`` (1.0) — how strongly the curve modulates around the
  centre (``(cc_min+cc_max)/2``). ``0`` = flat at centre regardless
  of curve; ``1`` = full swing to ``[cc_min, cc_max]``.
* ``samples_per_step`` (1) — emit N CCs per step for smoothing (1 =
  raw step values, 2+ = linearly interpolated between consecutive
  step values).
"""

from __future__ import annotations

import random
from typing import ClassVar

from jtx.algorithms._subdivision import subdivision_grid
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Param

_VALUE_CURVES = (
    "flat",
    "ramp_up",
    "ramp_down",
    "arc",
    "valley",
    "pulse",
    "drift",
    "surprise",
)


class StepCC(Algorithm):
    """Step-sequenced CC modulator with curve-driven values.

    MIDI-naive: emits ``Param(name="cc<N>", value=v/127)`` events.
    """

    name: ClassVar[str] = "step_cc"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        cc = int(knobs.get("cc", 74))
        subdivision = str(knobs.get("subdivision", "16"))
        value_curve = str(knobs.get("value_curve", "ramp_up"))
        cc_min = max(0, min(127, int(knobs.get("cc_min", 40))))
        cc_max = max(0, min(127, int(knobs.get("cc_max", 110))))
        depth = max(0.0, min(1.0, float(knobs.get("depth", 1.0))))
        samples_per_step = max(1, int(knobs.get("samples_per_step", 1)))

        if value_curve not in _VALUE_CURVES:
            raise ValueError(
                f"step_cc: unknown value_curve {value_curve!r} (expected one of {_VALUE_CURVES})"
            )

        spacing, positions = subdivision_grid(subdivision, ctx.ticks_per_bar, ctx.ppq)

        centre = (cc_min + cc_max) / 2.0
        half_range = (cc_max - cc_min) / 2.0

        # Compute the per-step normalized values (-1..1 around centre).
        normalized = [_curve_value(value_curve, step, positions, rng) for step in range(positions)]

        events: list[AbstractEvent] = []
        function_name = f"cc{cc}"
        for i in range(positions):
            tick = i * spacing
            v_next = normalized[(i + 1) % positions]
            v_curr = normalized[i]
            for s in range(samples_per_step):
                sub_tick = tick + (s * spacing) // samples_per_step
                if samples_per_step > 1:
                    frac = s / samples_per_step
                    v = v_curr * (1 - frac) + v_next * frac
                else:
                    v = v_curr
                cc_value = centre + half_range * depth * v
                cc_int = max(0, min(127, int(round(cc_value))))
                events.append(Param(name=function_name, value=cc_int / 127.0, tick=sub_tick))
        return events


def _curve_value(curve: str, step: int, total_steps: int, rng: random.Random) -> float:
    """Return the curve value at ``step`` in [-1, 1]."""
    if total_steps <= 0:
        return 0.0
    progress = step / max(1, total_steps - 1)  # 0..1 across the bar
    if curve == "flat":
        return 0.0
    if curve == "ramp_up":
        # -1 at start, +1 at end.
        return progress * 2 - 1
    if curve == "ramp_down":
        return 1 - progress * 2
    if curve == "arc":
        # -1 at edges, +1 in middle.
        return 4 * progress * (1 - progress) * 2 - 1
    if curve == "valley":
        return 1 - 4 * progress * (1 - progress) * 2
    if curve == "pulse":
        # Every 4 steps a downbeat pulse: +1 on beat, -1 elsewhere.
        return 1.0 if step % 4 == 0 else -1.0
    if curve == "drift":
        # Bar-seeded random walk in [-1, 1].
        return rng.uniform(-1.0, 1.0)
    if curve == "surprise":
        # Bigger jumps. Same distribution but bumped magnitude clipped.
        return max(-1.0, min(1.0, rng.uniform(-1.5, 1.5)))
    raise ValueError(f"step_cc: unknown curve {curve!r}")
