"""``tonic_pulse`` + ``chord_pulse`` — reference clicks for tonal context.

These two small algorithms are intended as **monitoring voices** during
a jam — you route them to a dedicated synth channel to hear the song
tonic / current chord root as a click track alongside the music.

* :class:`TonicPulse` emits the song tonic (``ctx.key.tonic``) at
  configured 16th-step positions. **Ignores ``chord_root_semitones``**
  so the tonic stays constant even when the chord progression moves
  underneath.
* :class:`ChordPulse` emits the current chord root (tonic +
  ``chord_root_semitones``) once per bar as a held note. This is the
  pitch you'd hum to *follow* the progression.

Both are deterministic (no RNG use) and stateless across bars.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._steps import step_ticks, steps_per_bar
from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn

_DEFAULT_TONIC_STEPS: tuple[int, ...] = (0, 4, 8, 12)  # quarter notes in 4/4


class TonicPulse(Algorithm):
    """Song-tonic reference click at configured 16th-step positions.

    Knobs:

    * ``steps`` — list of 16th-step indices to fire on. Default
      ``[0, 4, 8, 12]`` (quarter notes in 4/4).
    * ``velocity`` (90).
    * ``octave`` (0) — register shift; default 0 = octave 4 (A4 ≈ 440 Hz
      for an A-key song).
    * ``gate`` (0.5) — fraction of step the note holds.
    """

    name: ClassVar[str] = "tonic_pulse"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        raw_steps = knobs.get("steps", list(_DEFAULT_TONIC_STEPS))
        if not isinstance(raw_steps, list):
            raise TypeError(f"tonic_pulse: 'steps' must be a list, got {type(raw_steps).__name__}")

        velocity = max(1, min(127, int(knobs.get("velocity", 90))))
        octave_shift = int(knobs.get("octave", 0))
        gate = float(knobs.get("gate", 0.5))

        register_octave = 4 + octave_shift
        pitch = max(0, min(127, note_to_midi(ctx.key.tonic, register_octave)))

        s = step_ticks(ctx.ppq)
        total_steps = steps_per_bar(ctx.ticks_per_bar, ctx.ppq)
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


class ChordPulse(Algorithm):
    """Current chord-root reference, one whole note per bar.

    Pitch = ``note_to_midi(ctx.key.tonic, register) + ctx.chord_root_semitones``.
    Honours ``ctx.chord_root_semitones`` so the held note follows the
    progression's chord changes (unlike :class:`TonicPulse`).

    Knobs:

    * ``velocity`` (90).
    * ``octave`` (0) — register shift; default 0 = octave 4.
    * ``gate`` (0.95) — fraction of bar the note holds. Slightly under
      1 so consecutive bars have a clean retrigger boundary.
    """

    name: ClassVar[str] = "chord_pulse"

    def __init__(self, *, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        velocity = max(1, min(127, int(knobs.get("velocity", 90))))
        octave_shift = int(knobs.get("octave", 0))
        gate = float(knobs.get("gate", 0.95))

        register_octave = 4 + octave_shift
        pitch = max(
            0,
            min(127, note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones),
        )
        duration = max(1, int(ctx.ticks_per_bar * gate))
        return [
            NoteOn(tick=0, channel=self.midi_channel, note=pitch, velocity=velocity),
            NoteOff(tick=duration, channel=self.midi_channel, note=pitch),
        ]
