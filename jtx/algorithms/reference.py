"""``root_pulse`` — current chord-root reference voice.

Emits the **current chord root** (``ctx.key.tonic`` shifted by
``ctx.chord_root_semitones``) at configured 16th-step positions.
Designed to drive arps and other MIDI effects in a DAW that need a
moving root-note stream:

* Default ``steps=[0, 4, 8, 12]`` → quarter-note pulse. Feed into
  Ableton's Arpeggiator / Chord / Pitch effects to lock the effect's
  output to the current chord.
* ``steps=[0]`` with high ``gate`` → one held note per bar — useful as
  a sustained chord-root reference next to the rhythmic stream.

Deterministic (no RNG), stateless across bars.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn

_DEFAULT_STEPS: tuple[int, ...] = (0, 4, 8, 12)  # quarter notes in 4/4


class RootPulse(Algorithm):
    """Current chord root at configured 16th-step positions.

    Pitch = ``note_to_midi(ctx.key.tonic, register) + ctx.chord_root_semitones``,
    so the emitted note follows the macro chord progression bar-to-bar.

    Knobs:

    * ``steps`` — list of 16th-step indices to fire on. Default
      ``[0, 4, 8, 12]`` (quarter notes in 4/4). Use ``[0]`` for one
      whole note per bar.
    * ``velocity`` (90).
    * ``octave`` (0) — register shift; default 0 = octave 4 (A4 ≈ 440 Hz
      for an A-key song).
    * ``gate`` (0.5) — fraction of *step* the note holds. With
      ``steps=[0]`` and ``gate=0.95`` you get a near-whole-note hold
      relative to the step grid; for a true full-bar hold set
      ``duration_ticks`` explicitly.
    * ``duration_ticks`` — explicit note-off offset from note-on,
      overrides ``gate`` if set.
    """

    name: ClassVar[str] = "root_pulse"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        raw_steps = knobs.get("steps", list(_DEFAULT_STEPS))
        if not isinstance(raw_steps, list):
            raise TypeError(f"root_pulse: 'steps' must be a list, got {type(raw_steps).__name__}")

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

        if "duration_ticks" in knobs:
            duration = max(1, int(knobs["duration_ticks"]))
        else:
            duration = max(1, int(s * gate))

        events: list[Event] = []
        for raw in raw_steps:
            step = int(raw)
            if not (0 <= step < total_steps):
                continue
            tick = step * s
            events.append(
                NoteOn(tick=tick, channel=self.midi_channel, note=pitch, velocity=velocity)
            )
            events.append(NoteOff(tick=tick + duration, channel=self.midi_channel, note=pitch))
        return events
