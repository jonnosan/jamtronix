"""``cc_envelope`` — triggered envelope modulator.

Linear A-D-S-R shape retriggered on an even distribution of
``pulses`` + ``offset`` across the 16-step bar. The envelope ramps
from rest up to a peak (``peak_value``) over ``attack_ticks``, decays
to ``sustain_value`` over ``decay_ticks``, holds, then releases to
``rest_value`` over ``release_ticks``.

Schema v3: MIDI-naive. Emits :class:`Param` events tagged with a
semantic ``function`` name (``"cutoff"`` by default). The voice
slot's ``parameter_map`` (or the algorithm's ``DEFAULT_PARAM_MAP``
fallback) decides whether that becomes a CC / OSC / MPE message.

Knobs:

* ``function`` (``"cutoff"``) — semantic parameter name; the
  parameter_router resolves this via slot.parameter_map. Set to
  ``"resonance"``, ``"glide"``, etc. to drive a different parameter.
* ``pulses`` (4) + ``offset`` (0) — euclid trigger distribution.
* ``attack_ticks`` (40), ``decay_ticks`` (120), ``release_ticks`` (240).
* ``peak_value`` (120), ``sustain_value`` (90), ``rest_value`` (40).
* ``samples`` (8) — number of intermediate CC events per envelope
  segment (smoother sweep ↔ more MIDI traffic).
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Param
from jtx.model.parameter_target import CCTarget, ParameterTarget


class CCEnvelope(Algorithm):
    """Triggered envelope on a function-named parameter."""

    name: ClassVar[str] = "cc_envelope"
    DEFAULT_PARAM_MAP: ClassVar[dict[str, ParameterTarget]] = {
        "cutoff": CCTarget(74),
        "resonance": CCTarget(71),
    }

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        from jtx.algorithms._euclid import euclid

        knobs = ctx.pattern_knobs

        function = str(knobs.get("function", "cutoff"))
        pulses = int(knobs.get("pulses", 4))
        offset = int(knobs.get("offset", 0))

        attack = max(1, int(knobs.get("attack_ticks", 40)))
        decay = max(1, int(knobs.get("decay_ticks", 120)))
        release = max(1, int(knobs.get("release_ticks", 240)))
        peak = max(0, min(127, int(knobs.get("peak_value", 120))))
        sustain = max(0, min(127, int(knobs.get("sustain_value", 90))))
        rest = max(0, min(127, int(knobs.get("rest_value", 40))))
        samples = max(2, int(knobs.get("samples", 8)))

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        events: list[AbstractEvent] = []

        pattern = euclid(pulses, total_steps, offset)
        for step_idx, fires in enumerate(pattern):
            if not fires:
                continue
            start = step_idx * s
            events.extend(_ramp(function, start, attack, rest, peak, samples))
            events.extend(_ramp(function, start + attack, decay, peak, sustain, samples))
            release_start = start + attack + decay
            events.extend(_ramp(function, release_start, release, sustain, rest, samples))

        return events


def _ramp(
    function: str,
    start: int,
    duration: int,
    from_val: int,
    to_val: int,
    samples: int,
) -> list[AbstractEvent]:
    events: list[AbstractEvent] = []
    for i in range(samples):
        frac = i / max(1, samples - 1)
        value = int(round(from_val + (to_val - from_val) * frac))
        value = max(0, min(127, value))
        tick = start + int(round(duration * frac))
        events.append(Param(name=function, value=value / 127.0, tick=tick))
    return events
