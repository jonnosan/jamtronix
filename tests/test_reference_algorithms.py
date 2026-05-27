"""Tests for tonic_pulse + chord_pulse reference clicks."""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import ChordPulse, TonicPulse
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


# ------------------------------------------------------ tonic_pulse


def test_tonic_pulse_default_emits_4_quarter_notes_at_a4() -> None:
    pulse = TonicPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx())
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # 4 quarter notes at step 0, 4, 8, 12 → ticks 0, 480, 960, 1440.
    assert [e.tick for e in note_ons] == [0, 480, 960, 1440]
    # A4 = MIDI 69.
    assert all(e.note == 69 for e in note_ons)


def test_tonic_pulse_ignores_chord_root_semitones() -> None:
    """Defining property: tonic stays constant while the chord moves."""
    pulse = TonicPulse(midi_channel=16)
    bar_i = pulse.generate_bar(_ctx(chord_root_semitones=0))
    bar_vi = pulse.generate_bar(_ctx(chord_root_semitones=8))  # F over A
    bar_iii = pulse.generate_bar(_ctx(chord_root_semitones=3))  # C over A
    for bar in (bar_i, bar_vi, bar_iii):
        ons = [e for e in bar if isinstance(e, NoteOn)]
        assert all(e.note == 69 for e in ons)  # always A4


def test_tonic_pulse_follows_song_key() -> None:
    pulse = TonicPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(tonic="C"))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # C4 = MIDI 60.
    assert all(e.note == 60 for e in note_ons)


def test_tonic_pulse_steps_knob_overrides_default() -> None:
    pulse = TonicPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(pattern_knobs={"steps": [0, 8]}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    assert [e.tick for e in note_ons] == [0, 960]


def test_tonic_pulse_octave_shift() -> None:
    pulse = TonicPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(pattern_knobs={"octave": 1}))
    note_on = next(e for e in events if isinstance(e, NoteOn))
    assert note_on.note == 81  # A5


def test_tonic_pulse_gate_controls_duration() -> None:
    pulse = TonicPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(pattern_knobs={"gate": 0.25}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    note_offs = [e for e in events if isinstance(e, NoteOff)]
    for on, off in zip(note_ons, note_offs, strict=True):
        # step_ticks 120 × 0.25 = 30.
        assert off.tick - on.tick == 30


def test_tonic_pulse_rejects_non_list_steps() -> None:
    pulse = TonicPulse(midi_channel=16)
    with pytest.raises(TypeError, match="must be a list"):
        pulse.generate_bar(_ctx(pattern_knobs={"steps": "0,4"}))


def test_tonic_pulse_ignores_out_of_range_steps() -> None:
    pulse = TonicPulse(midi_channel=16)
    events = pulse.generate_bar(_ctx(pattern_knobs={"steps": [-1, 0, 16, 100]}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert [e.tick for e in note_ons] == [0]


# ------------------------------------------------------ chord_pulse


def test_chord_pulse_default_emits_one_whole_note_at_a4() -> None:
    pulse = ChordPulse(midi_channel=15)
    events = pulse.generate_bar(_ctx())
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    note_offs = [e for e in events if isinstance(e, NoteOff)]
    assert len(note_ons) == 1 and len(note_offs) == 1
    on = note_ons[0]
    off = note_offs[0]
    assert on.tick == 0 and on.note == 69
    assert off.tick == int(1920 * 0.95)


def test_chord_pulse_follows_chord_root_semitones() -> None:
    pulse = ChordPulse(midi_channel=15)
    # In A minor: i=A4, VI=F4 (+8), III=C5 (+3 → A4+3=72), VII=G5 (+10 → A4+10=79).
    assert (
        next(
            e.note
            for e in pulse.generate_bar(_ctx(chord_root_semitones=0))
            if isinstance(e, NoteOn)
        )
        == 69
    )
    assert (
        next(
            e.note
            for e in pulse.generate_bar(_ctx(chord_root_semitones=8))
            if isinstance(e, NoteOn)
        )
        == 77
    )  # A4 + 8 = F5
    assert (
        next(
            e.note
            for e in pulse.generate_bar(_ctx(chord_root_semitones=3))
            if isinstance(e, NoteOn)
        )
        == 72
    )  # A4 + 3 = C5
    assert (
        next(
            e.note
            for e in pulse.generate_bar(_ctx(chord_root_semitones=10))
            if isinstance(e, NoteOn)
        )
        == 79
    )  # A4 + 10 = G5


def test_chord_pulse_octave_shift() -> None:
    pulse = ChordPulse(midi_channel=15)
    events = pulse.generate_bar(_ctx(pattern_knobs={"octave": -1}))
    assert next(e.note for e in events if isinstance(e, NoteOn)) == 57  # A3


def test_chord_pulse_gate_controls_duration() -> None:
    pulse = ChordPulse(midi_channel=15)
    events = pulse.generate_bar(_ctx(pattern_knobs={"gate": 0.5}))
    assert next(e for e in events if isinstance(e, NoteOff)).tick == 960
