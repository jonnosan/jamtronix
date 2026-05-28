"""Tests for sustained_chord + chord_stab.

Both emit abstract :class:`Note` events in schema v3.
"""

from __future__ import annotations

import random

from jtx.algorithms import ChordStab, SustainedChord
from jtx.engine.context import BarContext
from jtx.model.events import Note
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


def _notes(events) -> list[Note]:
    return [e for e in events if isinstance(e, Note)]


# ----------------------------------------------------- sustained_chord


def test_sustained_chord_default_minor_triad() -> None:
    voice = SustainedChord()
    events = voice.generate_bar(_ctx())
    assert sorted(n.pitch for n in _notes(events)) == [69, 72, 76]


def test_sustained_chord_intervals_override() -> None:
    voice = SustainedChord()
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "maj7"}))
    assert sorted(n.pitch for n in _notes(events)) == [69, 73, 76, 80]


def test_sustained_chord_gate_controls_duration() -> None:
    voice = SustainedChord()
    events = voice.generate_bar(_ctx(pattern_knobs={"gate": 0.5}))
    # Bar = 1920 ticks; gate 0.5 → duration = 960.
    assert all(n.duration_ticks == 960 for n in _notes(events))


def test_sustained_chord_octave_shift() -> None:
    voice = SustainedChord()
    events = voice.generate_bar(_ctx(pattern_knobs={"octave": -1}))
    assert min(n.pitch for n in _notes(events)) == 57


def test_sustained_chord_drift_drops_one_voice_octave() -> None:
    voice = SustainedChord()
    events = voice.generate_bar(_ctx(pattern_knobs={"drift_prob": 1.0}))
    notes = sorted(_notes(events), key=lambda n: n.pitch)
    assert notes[0].pitch in {57, 60, 64}


def test_sustained_chord_chord_root_semitones_transposes() -> None:
    voice = SustainedChord()
    ctx = _ctx(pattern_knobs={"quality": "unison"})
    ctx.chord_root_semitones = 5
    events = voice.generate_bar(ctx)
    notes = _notes(events)
    assert notes[0].pitch == 74


# --------------------------------------------------------- chord_stab


def test_chord_stab_default_steps_are_off_beat_16ths() -> None:
    voice = ChordStab()
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison"}))
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert [n.tick for n in notes] == [240, 720, 1200, 1680]


def test_chord_stab_pulses_knob_overrides() -> None:
    voice = ChordStab()
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison", "pulses": 2, "offset": 0}))
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert [n.tick for n in notes] == [0, 960]


def test_chord_stab_emits_full_chord_at_each_step() -> None:
    voice = ChordStab()
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "minor", "pulses": 1, "offset": 4}))
    notes = sorted(_notes(events), key=lambda n: n.pitch)
    assert [n.pitch for n in notes] == [69, 72, 76]
    assert all(n.tick == 480 for n in notes)


def test_chord_stab_gate_controls_duration() -> None:
    voice = ChordStab()
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison", "gate": 0.25}))
    # step_ticks=120, gate=0.25 → duration_ticks = 30.
    assert all(n.duration_ticks == 30 for n in _notes(events))


def test_chord_stab_drop_prob_one_emits_nothing() -> None:
    voice = ChordStab()
    events = voice.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0}))
    assert _notes(events) == []


def test_chord_stab_zero_pulses_emits_nothing() -> None:
    voice = ChordStab()
    events = voice.generate_bar(_ctx(pattern_knobs={"quality": "unison", "pulses": 0}))
    assert _notes(events) == []
