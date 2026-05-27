"""``sub_drone`` — long-gated sub bass for deep techno.

Architectural note: jtx algorithms emit events for one bar at a time
(see ``docs/SPEC.md`` §Bar-by-Bar Regeneration). A "two-bar held note"
in the slackbeatz subdrone becomes two consecutive bars with identical
pitches — the synth retriggers at the bar boundary, which is musically
acceptable for sub-bass voices with a slow attack/release.

The cell length (``bars_per_chord``) selects which pitch fires on each
bar. With ``bars_per_chord=2`` (default), bars 0/1 are the root cell,
bars 2/3 the fifth cell, etc. With ``bars_per_chord=4`` you get long
4-bar holds; with 1 each bar alternates root/fifth.

Chord-following piggybacks on ``ctx.chord_root_semitones`` (set by the
not-yet-built progression resolver). With it at 0 you get root/fifth
alternation; non-zero values transpose the root.

Knobs:

* ``gate`` — fraction of the bar the note holds (default 0.95).
* ``fifth_prob`` — chance of forcing the fifth (overrides cell pattern).
* ``bars_per_chord`` — cell length in bars (default 2).
* ``kick_env`` — 0..1 CC74 envelope dipping on each quarter beat
  (default 0 = off). 1.0 = full 20→120 swing per beat.
* ``base_vel`` — default 85.
* ``octave`` — register shift; default 0 (= register 1 sub-bass A1 ≈ 55 Hz).
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn

_DEFAULT_CC: dict[str, int] = {"filter_cutoff": 74}


class SubDrone(Algorithm):
    """Long-gated root/fifth sub-bass with optional kick-locked CC74."""

    name: ClassVar[str] = "sub_drone"
    DEFAULT_CC: ClassVar[dict[str, int]] = dict(_DEFAULT_CC)

    def __init__(
        self,
        *,
        midi_channel: int,
        cc_map: dict[str, int] | None = None,
    ) -> None:
        self.midi_channel = midi_channel
        self._cc_map = dict(cc_map) if cc_map else {}

    def _cc(self, function: str) -> int:
        return int(self._cc_map.get(function, _DEFAULT_CC[function]))

    def generate_bar(self, ctx: BarContext) -> list[Event]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        gate = float(knobs.get("gate", 0.95))
        fifth_prob = float(knobs.get("fifth_prob", 0.0))
        bars_per_chord = max(1, int(knobs.get("bars_per_chord", 2)))
        kick_env = float(knobs.get("kick_env", 0.0))
        base_vel = int(knobs.get("base_vel", 85))
        octave_shift = int(knobs.get("octave", 0))

        # Register 1: A1 ≈ 55 Hz — true sub-bass for deep techno.
        register_octave = 1 + octave_shift
        root_raw = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones
        fifth_raw = root_raw + 7

        # Cell pattern: which "harmonic position" is this bar in?
        # cell_idx 0 → root, cell_idx 1 → fifth, alternating every
        # ``bars_per_chord`` bars.
        cell_position = (ctx.bar_index // bars_per_chord) % 2
        if fifth_prob > 0 and rng.random() < fifth_prob:
            pitch = fifth_raw
        else:
            pitch = fifth_raw if cell_position == 1 else root_raw

        jitter = rng.randint(-3, 3)
        vel = max(1, min(127, base_vel + jitter))
        duration = max(1, int(ctx.ticks_per_bar * gate))
        clamped_pitch = max(0, min(127, pitch))

        events: list[Event] = [
            NoteOn(tick=0, channel=self.midi_channel, note=clamped_pitch, velocity=vel),
            NoteOff(tick=duration, channel=self.midi_channel, note=clamped_pitch),
        ]

        if kick_env > 0:
            low = int(round(120 - 100 * kick_env))  # kick_env=1 → low=20
            high = 120
            events_per_beat = 4
            cc_step = ctx.ppq // events_per_beat
            beats_per_bar = ctx.ticks_per_bar // ctx.ppq
            for beat in range(beats_per_bar):
                beat_tick = beat * ctx.ppq
                for i in range(events_per_beat):
                    frac = i / max(1, events_per_beat - 1)
                    value = int(round(low + (high - low) * frac))
                    events.append(
                        ControlChange(
                            tick=beat_tick + i * cc_step,
                            channel=self.midi_channel,
                            cc=self._cc("filter_cutoff"),
                            value=max(0, min(127, value)),
                        )
                    )

        return events
