"""Tests for the reese_bass algorithm."""

from __future__ import annotations

import random

from jtx.algorithms import ReeseBass
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, NoteOff, NoteOn
from jtx.model.song import Key


def _ctx(
    *,
    pattern_knobs: dict[str, object] | None = None,
    bar_index: int = 0,
    seed: int = 0,
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


def test_reese_bass_emits_one_note_per_bar() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(_ctx())
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    note_offs = [e for e in events if isinstance(e, NoteOff)]
    assert len(note_ons) == 1
    assert len(note_offs) == 1


def test_reese_bass_root_default_octave_register_1() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(_ctx(pattern_knobs={"wobble_depth": 0.0, "detune_depth": 0.0}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # A at octave 1 = MIDI 33.
    assert note_ons[0].note == 33


def test_reese_bass_alternates_root_and_fifth_per_cell() -> None:
    reese = ReeseBass(midi_channel=8)
    knobs = {"wobble_depth": 0.0, "detune_depth": 0.0, "bars_per_chord": 2}
    pitches = []
    for b in range(4):
        evs = reese.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b))
        pitches.append(next(e for e in evs if isinstance(e, NoteOn)).note)
    # bars 0-1 root, bars 2-3 fifth.
    assert pitches[0] == pitches[1]
    assert pitches[2] == pitches[3]
    assert pitches[2] - pitches[0] == 7  # perfect fifth


def test_reese_bass_wobble_emits_cc74_on_subdivision() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(
        _ctx(pattern_knobs={"wobble_subdiv": "8", "wobble_depth": 1.0, "detune_depth": 0.0})
    )
    cc74 = [e for e in events if isinstance(e, ControlChange) and e.cc == 74]
    # 8th-note subdivision → 8 samples per bar.
    assert len(cc74) == 8


def test_reese_bass_wobble_triplet_subdivision() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(
        _ctx(pattern_knobs={"wobble_subdiv": "8t", "wobble_depth": 0.8, "detune_depth": 0.0})
    )
    cc74 = [e for e in events if isinstance(e, ControlChange) and e.cc == 74]
    # 8t = 12 positions per 4/4 bar.
    assert len(cc74) == 12


def test_reese_bass_wobble_zero_emits_no_cc74() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(_ctx(pattern_knobs={"wobble_depth": 0.0, "detune_depth": 0.0}))
    assert not any(isinstance(e, ControlChange) and e.cc == 74 for e in events)


def test_reese_bass_detune_emits_cc1() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(_ctx(pattern_knobs={"wobble_depth": 0.0, "detune_depth": 0.5}))
    cc1 = [e for e in events if isinstance(e, ControlChange) and e.cc == 1]
    assert cc1


def test_reese_bass_gate_controls_note_duration() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(_ctx(pattern_knobs={"gate": 0.5, "wobble_depth": 0.0}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    note_offs = [e for e in events if isinstance(e, NoteOff)]
    assert note_offs[0].tick - note_ons[0].tick == int(1920 * 0.5)


def test_reese_bass_octave_shift_changes_register() -> None:
    reese = ReeseBass(midi_channel=8)
    events = reese.generate_bar(
        _ctx(pattern_knobs={"octave": 1, "wobble_depth": 0.0, "detune_depth": 0.0})
    )
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # A at octave 2 = MIDI 45.
    assert note_ons[0].note == 45
