"""Tests for root_pulse — chord-root reference click."""

from __future__ import annotations

import random

from jtx.algorithms import RootPulse
from jtx.engine.context import BarContext
from jtx.engine.events import NoteOff, NoteOn
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


def test_root_pulse_default_emits_4_quarter_notes_at_a4() -> None:
    pulse = RootPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx())
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    assert [e.tick for e in note_ons] == [0, 480, 960, 1440]
    assert all(e.note == 69 for e in note_ons)  # A4 with chord_root=0


def test_root_pulse_follows_chord_root_semitones() -> None:
    """Defining property: pitch shifts with the chord progression."""
    pulse = RootPulse(midi_channel=16)
    # In A minor: i → A4 (69), VI → F5 (77), III → C5 (72), VII → G5 (79).
    for chord_root, expected in [(0, 69), (8, 77), (3, 72), (10, 79)]:
        ons = [
            e
            for e in pulse.generate_bar(_ctx(chord_root_semitones=chord_root))
            if isinstance(e, NoteOn)
        ]
        assert all(e.note == expected for e in ons), (
            f"chord_root={chord_root} → expected {expected}, got {[e.note for e in ons]}"
        )


def test_root_pulse_follows_song_key() -> None:
    pulse = RootPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(tonic="C"))
    assert all(e.note == 60 for e in events if isinstance(e, NoteOn))  # C4


def test_root_pulse_one_pulse_with_long_gate_holds_most_of_bar() -> None:
    """Useful as a sustained chord-root reference next to the rhythmic stream."""
    pulse = RootPulse(midi_channel=15)
    # step_ticks = 120, gate = 15.2 → duration 1824 ticks (≈ 95% of a bar).
    events = pulse.generate_bar(_ctx(pattern_knobs={"pulses": 1, "offset": 0, "gate": 15.2}))
    ons = [e for e in events if isinstance(e, NoteOn)]
    offs = [e for e in events if isinstance(e, NoteOff)]
    assert len(ons) == 1 and len(offs) == 1
    assert ons[0].tick == 0
    assert offs[0].tick == 1824


def test_root_pulse_octave_shift() -> None:
    pulse = RootPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(pattern_knobs={"octave": 1}))
    assert next(e.note for e in events if isinstance(e, NoteOn)) == 81  # A5


def test_root_pulse_gate_controls_step_relative_duration() -> None:
    pulse = RootPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(pattern_knobs={"gate": 0.25}))
    ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    offs = sorted((e for e in events if isinstance(e, NoteOff)), key=lambda e: e.tick)
    for on, off in zip(ons, offs, strict=True):
        assert off.tick - on.tick == 30  # step_ticks 120 × 0.25


def test_root_pulse_zero_pulses_emits_nothing() -> None:
    pulse = RootPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(pattern_knobs={"pulses": 0}))
    assert [e for e in events if isinstance(e, NoteOn)] == []
