"""Tests for sustained_chord + chord_stab."""

from __future__ import annotations

import random

from jtx.algorithms import ChordStab, SustainedChord
from jtx.engine.context import BarContext
from jtx.engine.events import NoteOff, NoteOn
from jtx.model.song import Key


def _ctx(
    *, pattern_knobs: dict[str, object] | None = None, bar_index: int = 0, seed: int = 0
) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(seed),
    )


# ----------------------------------------------------- sustained_chord


def test_sustained_chord_default_minor_triad() -> None:
    voice = SustainedChord(midi_channel=5)
    events = voice.generate_bar(_ctx())
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # A minor triad at octave 4: 69, 72, 76.
    assert sorted(e.note for e in note_ons) == [69, 72, 76]


def test_sustained_chord_intervals_override() -> None:
    voice = SustainedChord(midi_channel=5)
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "maj7"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # Maj7: 69, 73, 76, 80.
    assert sorted(e.note for e in note_ons) == [69, 73, 76, 80]


def test_sustained_chord_gate_controls_duration() -> None:
    voice = SustainedChord(midi_channel=5)
    events = voice.generate_bar(_ctx(pattern_knobs={"gate": 0.5}))
    offs = [e for e in events if isinstance(e, NoteOff)]
    assert all(e.tick == 960 for e in offs)


def test_sustained_chord_octave_shift() -> None:
    voice = SustainedChord(midi_channel=5)
    events = voice.generate_bar(_ctx(pattern_knobs={"octave": -1}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # Octave -1 → root at A3 = 57.
    assert min(e.note for e in note_ons) == 57


def test_sustained_chord_drift_drops_one_voice_octave() -> None:
    voice = SustainedChord(midi_channel=5)
    events = voice.generate_bar(_ctx(pattern_knobs={"drift_prob": 1.0}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.note)
    # Without drift, lowest note would be 69 (root). With drift on every
    # bar, one voice drops 12 semitones — lowest will be 57 (root) or
    # 60 (third) or 64 (fifth).
    assert note_ons[0].note in {57, 60, 64}


def test_sustained_chord_chord_root_semitones_transposes() -> None:
    voice = SustainedChord(midi_channel=5)
    ctx = _ctx(pattern_knobs={"quality": "unison"})
    ctx.chord_root_semitones = 5
    events = voice.generate_bar(ctx)
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert note_ons[0].note == 74  # 69 + 5


# --------------------------------------------------------- chord_stab


def test_chord_stab_default_steps_are_off_beat_16ths() -> None:
    voice = ChordStab(midi_channel=6)
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison"}))  # one note for clarity
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # Default pulses=4, offset=2 → euclid steps [2, 6, 10, 14]
    # × step_ticks 120 = [240, 720, 1200, 1680].
    assert [e.tick for e in note_ons] == [240, 720, 1200, 1680]


def test_chord_stab_pulses_knob_overrides() -> None:
    voice = ChordStab(midi_channel=6)
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison", "pulses": 2, "offset": 0}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    assert [e.tick for e in note_ons] == [0, 960]


def test_chord_stab_emits_full_chord_at_each_step() -> None:
    voice = ChordStab(midi_channel=6)
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "minor", "pulses": 1, "offset": 4}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.note)
    assert [e.note for e in note_ons] == [69, 72, 76]
    assert all(e.tick == 480 for e in note_ons)


def test_chord_stab_gate_controls_duration() -> None:
    voice = ChordStab(midi_channel=6)
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison", "gate": 0.25}))
    durations = []
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    for on in note_ons:
        off = next(
            e for e in events if isinstance(e, NoteOff) and e.tick > on.tick and e.note == on.note
        )
        durations.append(off.tick - on.tick)
    # step_ticks=120, gate=0.25 → duration = 30.
    assert all(d == 30 for d in durations)


def test_chord_stab_drop_prob_one_emits_nothing() -> None:
    voice = ChordStab(midi_channel=6)
    events = voice.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0}))
    assert not any(isinstance(e, NoteOn) for e in events)


def test_chord_stab_zero_pulses_emits_nothing() -> None:
    voice = ChordStab(midi_channel=6)
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison", "pulses": 0}))
    assert not [e for e in events if isinstance(e, NoteOn)]
