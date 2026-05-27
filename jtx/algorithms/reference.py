"""``root_pulse`` — current chord-root reference voice.

Emits the **current chord root** (``ctx.key.tonic`` shifted by
``ctx.chord_root_semitones``) at euclid-distributed step positions.
Designed to drive arps and other MIDI effects in a DAW that need a
moving root-note stream.

Knobs:

* ``pulses`` + ``offset`` — even distribution across the 16-step bar.
  ``pulses=4, offset=0`` = quarter-note pulse. ``pulses=1, offset=0``
  + high ``gate`` = one held note per bar (sustained chord-root).
* ``velocity`` (90), ``octave`` (0), ``gate`` (0.5).
* ``duration_ticks`` — explicit note-off offset; if set, overrides
  ``gate``.

Deterministic (no RNG), stateless across bars.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._euclid import euclid
from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn


class RootPulse(Algorithm):
    """Current chord root at euclid-distributed step positions."""

    name: ClassVar[str] = "root_pulse"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
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

        if "duration_ticks" in knobs and int(knobs["duration_ticks"]) > 0:
            duration = max(1, int(knobs["duration_ticks"]))
        else:
            duration = max(1, int(s * gate))

        pattern = euclid(pulses, total_steps, offset)
        events: list[Event] = []
        for step_idx, fires in enumerate(pattern):
            if not fires:
                continue
            tick = step_idx * s
            events.append(
                NoteOn(tick=tick, channel=self.midi_channel, note=pitch, velocity=velocity)
            )
            events.append(NoteOff(tick=tick + duration, channel=self.midi_channel, note=pitch))
        return events
