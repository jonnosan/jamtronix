"""``root_pulse`` — current chord-root reference voice.

Emits the **current chord root** (``ctx.key.tonic`` shifted by
``ctx.chord_root_semitones``) at euclid-distributed step positions.
Designed to drive arps and other MIDI effects in a DAW that need a
moving root-note stream.

Knobs:

* ``pulses`` + ``offset`` — even distribution across the 16-step bar.
  ``pulses=4, offset=0`` = quarter-note pulse. ``pulses=1, offset=0``
  + a high ``gate`` = one held note that lasts most of the bar.
* ``velocity`` (90), ``octave`` (0).
* ``gate`` (0.5..32) — note length as a fraction of *one step*. A
  generous range lets a single pulse hold for many steps; ``gate=15``
  with ``pulses=1`` gives a near-whole-bar sustained root.

Deterministic (no RNG), stateless across bars. MIDI-naive — emits
:class:`Note` events for the voicing stage to route.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._euclid import euclid
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note


class RootPulse(Algorithm):
    """Current chord root at euclid-distributed step positions."""

    name: ClassVar[str] = "root_pulse"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs

        pulses = int(knobs.get("pulses", 4))
        offset = int(knobs.get("offset", 0))
        velocity = max(1, min(127, int(knobs.get("velocity", 90))))
        octave_shift = int(knobs.get("octave", 0))
        gate = float(knobs.get("gate", 0.5))

        register_octave = 4 + octave_shift
        pitch = max(
            0,
            min(127, note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones),
        )

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
        duration = max(1, int(s * gate))

        pattern = euclid(pulses, total_steps, offset)
        events: list[AbstractEvent] = []
        for step_idx, fires in enumerate(pattern):
            if not fires:
                continue
            tick = step_idx * s
            events.append(
                Note(pitch=pitch, velocity=velocity, duration_ticks=duration, tick=tick)
            )
        return events
