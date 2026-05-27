"""Tests for melodic_line + arp algorithms."""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import Arp, MelodicLine
from jtx.algorithms._theory import scale_intervals
from jtx.engine.context import BarContext
from jtx.engine.events import NoteOff, NoteOn
from jtx.model.song import Key


def _ctx(
    *,
    pattern_knobs: dict[str, object] | None = None,
    bar_index: int = 0,
    seed: int = 0,
    scale: str = "minor",
) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale=scale),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(seed),
    )


# ----------------------------------------------------------------- scales


def test_scale_intervals_known() -> None:
    assert scale_intervals("minor") == (0, 2, 3, 5, 7, 8, 10)
    assert scale_intervals("major") == (0, 2, 4, 5, 7, 9, 11)
    assert scale_intervals("dorian") == (0, 2, 3, 5, 7, 9, 10)


def test_scale_intervals_unknown_falls_back_to_minor() -> None:
    assert scale_intervals("bogus") == scale_intervals("minor")


# ----------------------------------------------------------- melodic_line


def test_melodic_line_pitches_within_scale() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0}))
    # A minor at octave 4: A4=69. Default palette "tones_only" =
    # (0, 2, 4, 5, 7) → +0, +3, +7, +8, +12 → 69, 72, 76, 77, 81.
    expected = {69, 72, 76, 77, 81}
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert all(e.note in expected for e in note_ons)


def test_melodic_line_drop_prob_one_emits_nothing() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0}))
    assert not any(isinstance(e, NoteOn) for e in events)


def test_melodic_line_drop_prob_zero_fills_all_steps() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 16


def test_melodic_line_palette_constrains_pitches() -> None:
    line = MelodicLine(midi_channel=3)
    # "triad" palette = (0, 2, 4) → root + 3rd + 5th = {69, 72, 76}.
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "palette": "triad"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert all(e.note in {69, 72, 76} for e in note_ons)


def test_melodic_line_low_palette_reaches_below_root() -> None:
    line = MelodicLine(midi_channel=3)
    # "low" palette = (-3, -1, 0, 2, 4) → {64, 67, 69, 72, 76}.
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "palette": "low"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert any(e.note < 69 for e in note_ons)


def test_melodic_line_chord_root_semitones_transposes() -> None:
    line = MelodicLine(midi_channel=3)
    ctx = _ctx(pattern_knobs={"drop_prob": 0.0, "palette": "triad"})
    ctx.chord_root_semitones = 5
    events = line.generate_bar(ctx)
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # triad palette shifted by +5: {74, 77, 81}.
    assert all(e.note in {74, 77, 81} for e in note_ons)


def test_melodic_line_passing_tone_inserts_chromatic_neighbour() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(
        _ctx(
            pattern_knobs={
                "drop_prob": 0.0,
                "palette": "tones_only",
                "passing_prob": 1.0,
            }
        )
    )
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    pitches_seen = {e.note for e in note_ons}
    # tones_only palette pitches in A minor: {69, 72, 76, 77, 81}.
    palette_pitches = {69, 72, 76, 77, 81}
    chromatic_neighbours = pitches_seen - palette_pitches
    assert chromatic_neighbours


def test_melodic_line_gate_controls_duration() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "gate": 0.25}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    note_offs = sorted((e for e in events if isinstance(e, NoteOff)), key=lambda e: e.tick)
    # Each non-passing-tone note: off.tick - on.tick == int(120 * 0.25) = 30.
    # passing tones produce extra short notes — count matching length 30.
    durations = [off.tick - on.tick for on, off in zip(note_ons, note_offs, strict=False)]
    assert any(d == 30 for d in durations)


def test_melodic_line_uses_key_scale() -> None:
    line = MelodicLine(midi_channel=3)
    # Major scale at A: scale intervals (0,2,4,5,7,9,11). triad palette
    # (0, 2, 4) → 69, 73, 76 (root + major 3rd + 5th).
    events = line.generate_bar(
        _ctx(scale="major", pattern_knobs={"drop_prob": 0.0, "palette": "triad"})
    )
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert all(e.note in {69, 73, 76} for e in note_ons)


# ---------------------------------------------------------------- arp


def test_arp_up_climbs_chord_tones() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "up", "quality": "minor", "rate_steps": 4})
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # rate_steps=4 → 4 arp notes per bar; 1 octave × 3 intervals.
    assert [e.note for e in note_ons] == [69, 72, 76, 69]


def test_arp_down_descends() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "down", "quality": "minor", "rate_steps": 4})
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # down starts at top of ladder (76, 72, 69) and wraps.
    assert [e.note for e in note_ons] == [76, 72, 69, 76]


def test_arp_octaves_extends_range() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(
            pattern_knobs={
                "mode": "up",
                "quality": "unison",
                "octaves": 3,
                "rate_steps": 8,
            }
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # rate_steps=8 → 2 notes per bar.
    assert [e.note for e in note_ons] == [69, 81]


def test_arp_random_stays_within_ladder() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "random", "quality": "minor", "rate_steps": 1})
    )
    ladder = {69, 72, 76}
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert all(e.note in ladder for e in note_ons)


def test_arp_walk_takes_steps_of_one() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "walk", "quality": "minor", "rate_steps": 2})
    )
    ladder = [69, 72, 76]
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # Each consecutive walk note should be one ladder index away
    # (or clamped at the boundary).
    indices = [ladder.index(e.note) for e in note_ons]
    for prev, curr in zip(indices, indices[1:], strict=False):
        assert abs(prev - curr) <= 1


def test_arp_rate_steps_4_produces_4_arp_notes_per_bar() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "rate_steps": 4}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 4


def test_arp_rate_steps_1_produces_16_arp_notes() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "rate_steps": 1}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 16


def test_arp_gate_controls_duration() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "rate_steps": 4, "gate": 0.25}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    note_offs = sorted((e for e in events if isinstance(e, NoteOff)), key=lambda e: e.tick)
    # step_ticks=120, rate_steps=4, gate=0.25 → duration = 120*4*0.25 = 120.
    for on, off in zip(note_ons, note_offs, strict=True):
        assert off.tick - on.tick == 120


def test_arp_unknown_mode_raises() -> None:
    arp = Arp(midi_channel=4)
    with pytest.raises(ValueError, match="unknown mode"):
        arp.generate_bar(_ctx(pattern_knobs={"mode": "bogus", "rate_steps": 4}))


def test_arp_chord_root_semitones_transposes() -> None:
    arp = Arp(midi_channel=4)
    ctx = _ctx(pattern_knobs={"mode": "up", "quality": "unison", "rate_steps": 4})
    ctx.chord_root_semitones = 5
    events = arp.generate_bar(ctx)
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert all(e.note == 69 + 5 for e in note_ons)
