"""Tests for root_pulse — chord-root reference click.

Schema v3: emits :class:`Note` events; voicing stage adds the MIDI
channel from the voice slot.
"""

from __future__ import annotations

import random

from jtx.algorithms import RootPulse
from jtx.engine.context import BarContext
from jtx.model.events import Note
from jtx.model.song import Key


def _ctx(
    *,
    pattern_knobs: dict[str, object] | None = None,
    chord_root_semitones: int = 0,
    tonic: str = "A",
) -> BarContext:
    ctx = BarContext(
        bar_index=0,
        tick_offset=0,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic=tonic, scale="minor"),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(0),
    )
    ctx.chord_root_semitones = chord_root_semitones
    return ctx


def _notes(events) -> list[Note]:
    return [e for e in events if isinstance(e, Note)]


def test_root_pulse_default_emits_4_quarter_notes_at_a4() -> None:
    pulse = RootPulse()
    events = pulse.generate_bar(_ctx())
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert [n.tick for n in notes] == [0, 480, 960, 1440]
    assert all(n.pitch == 69 for n in notes)


def test_root_pulse_follows_chord_root_semitones() -> None:
    pulse = RootPulse()
    for chord_root, expected in [(0, 69), (8, 77), (3, 72), (10, 79)]:
        notes = _notes(pulse.generate_bar(_ctx(chord_root_semitones=chord_root)))
        assert all(n.pitch == expected for n in notes), (
            f"chord_root={chord_root} → expected {expected}, got {[n.pitch for n in notes]}"
        )


def test_root_pulse_follows_song_key() -> None:
    pulse = RootPulse()
    events = pulse.generate_bar(_ctx(tonic="C"))
    assert all(n.pitch == 60 for n in _notes(events))


def test_root_pulse_one_pulse_with_long_gate_holds_most_of_bar() -> None:
    pulse = RootPulse()
    events = pulse.generate_bar(_ctx(pattern_knobs={"pulses": 1, "offset": 0, "gate": 15.2}))
    notes = _notes(events)
    assert len(notes) == 1
    assert notes[0].tick == 0
    assert notes[0].duration_ticks == 1824


def test_root_pulse_octave_shift() -> None:
    pulse = RootPulse()
    events = pulse.generate_bar(_ctx(pattern_knobs={"octave": 1}))
    assert _notes(events)[0].pitch == 81  # A5


def test_root_pulse_gate_controls_step_relative_duration() -> None:
    pulse = RootPulse()
    events = pulse.generate_bar(_ctx(pattern_knobs={"gate": 0.25}))
    for n in _notes(events):
        assert n.duration_ticks == 30  # step_ticks 120 × 0.25


def test_root_pulse_zero_pulses_emits_nothing() -> None:
    pulse = RootPulse()
    events = pulse.generate_bar(_ctx(pattern_knobs={"pulses": 0}))
    assert _notes(events) == []
