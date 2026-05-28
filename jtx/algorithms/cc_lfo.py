"""``cc_lfo`` + ``cc_envelope`` — modulator-voice algorithms.

These algorithms emit ControlChange events only — no notes. They live on
``modulator`` voices in the setup, where the channel is the *target*
channel (the same one the synth-voice algorithm is firing notes on).

``cc_lfo`` is the convenient case for a free-running CC LFO. The general
case — modulating a *knob*, a feel parameter, or anything else — lives
in the song-level LFO system (issue #14). For raw CCs on a fixed channel,
this algorithm is simpler than wiring a song-level LFO.

``cc_envelope`` is a triggered envelope: linear attack-decay-sustain
shape, retriggered on a euclid distribution of ``pulses`` + ``offset``
across the 16-step bar. Used for kick-synced filter sweeps.
"""

from __future__ import annotations

import math
from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Param


class CCLFO(Algorithm):
    """Free-running CC LFO on one CC number.

    Schema v3: MIDI-naive. Emits ``Param(name="cc<N>", value=v/127)``
    events. The voicing stage uses the embedded CC number to emit a
    :class:`ControlChange` on the slot's channel.

    Knobs:
    * ``cc`` (74) — controller number.
    * ``shape`` — ``sine`` (default) / ``tri`` / ``saw`` / ``square``
      / ``random``.
    * ``period_bars`` (4.0) — full cycle length in bars.
    * ``phase`` (0.0) — starting phase in ``[0, 1)``.
    * ``depth`` (1.0) — 0..1, output amplitude scale.
    * ``offset`` (0.5) — DC offset of the centre point (0..1).
    * ``samples_per_bar`` (16) — how many Param events per bar.
    """

    name: ClassVar[str] = "cc_lfo"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        cc = int(knobs.get("cc", 74))
        shape = str(knobs.get("shape", "sine"))
        period_bars = float(knobs.get("period_bars", 4.0))
        phase = float(knobs.get("phase", 0.0))
        depth = float(knobs.get("depth", 1.0))
        offset = float(knobs.get("offset", 0.5))
        samples = max(1, int(knobs.get("samples_per_bar", 16)))

        if period_bars <= 0:
            raise ValueError("cc_lfo: period_bars must be > 0")

        sample_ticks = max(1, ctx.ticks_per_bar // samples)
        events: list[AbstractEvent] = []
        function_name = f"cc{cc}"

        for i in range(samples):
            tick = i * sample_ticks
            within_bar = tick / ctx.ticks_per_bar
            absolute_phase = (ctx.bar_index + within_bar) / period_bars + phase
            absolute_phase -= math.floor(absolute_phase)
            raw = _wave_sample(shape, absolute_phase, rng)
            value_unit = max(0.0, min(1.0, offset + (raw - 0.5) * depth))
            events.append(Param(name=function_name, value=value_unit, tick=tick))
        return events


def _wave_sample(shape: str, phase: float, rng: object) -> float:
    """Return the wave's value in [0, 1] at *phase* in [0, 1)."""
    import random as _random

    if shape == "sine":
        return (math.sin(2 * math.pi * phase) + 1.0) / 2.0
    if shape == "tri":
        return 1.0 - 2.0 * abs(phase - 0.5)
    if shape == "saw":
        return phase
    if shape == "square":
        return 1.0 if phase < 0.5 else 0.0
    if shape == "random":
        rng_random = rng if isinstance(rng, _random.Random) else _random.Random()
        return rng_random.random()
    raise ValueError(
        f"cc_lfo: unknown shape {shape!r} (expected sine | tri | saw | square | random)"
    )


class CCEnvelope(Algorithm):
    """Triggered envelope on a CC. MIDI-naive — emits Param("cc<N>")."""

    name: ClassVar[str] = "cc_envelope"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        from jtx.algorithms._euclid import euclid

        knobs = ctx.pattern_knobs

        cc = int(knobs.get("cc", 74))
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
        function_name = f"cc{cc}"

        pattern = euclid(pulses, total_steps, offset)
        for step_idx, fires in enumerate(pattern):
            if not fires:
                continue
            start = step_idx * s
            events.extend(_ramp(function_name, start, attack, rest, peak, samples))
            events.extend(_ramp(function_name, start + attack, decay, peak, sustain, samples))
            release_start = start + attack + decay
            events.extend(_ramp(function_name, release_start, release, sustain, rest, samples))

        return events


def _ramp(
    function_name: str,
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
        events.append(Param(name=function_name, value=value / 127.0, tick=tick))
    return events
