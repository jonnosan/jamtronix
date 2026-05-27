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
    part_voice_seed: int = 99,
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
        part_voice_seed=part_voice_seed,
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


def test_melodic_line_drop_prob_zero_fills_all_positions_default_grid() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # Default subdivision = "16" → 16 positions per bar.
    assert len(note_ons) == 16


def test_melodic_line_subdivision_8_fills_eight_positions() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "subdivision": "8"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 8


def test_melodic_line_subdivision_16t_uses_triplet_grid() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "subdivision": "16t"}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # 16t = 3 per 8th × 8 8ths per bar = 24 positions per bar.
    assert len(note_ons) == 24
    # Triplet spacing at PPQ=480 is 80 ticks; first three positions
    # cluster at 0, 80, 160 (the 2/3-of-quarter triplet grid).
    assert [e.tick for e in note_ons[:3]] == [0, 80, 160]


def test_melodic_line_triplet_prob_inserts_triplet_runs() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(
        _ctx(
            pattern_knobs={
                "drop_prob": 0.0,
                "triplet_prob": 1.0,
                "triplet_subdiv": "16t",
            }
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # Every beat won the roll; each beat gets 3 triplet positions
    # instead of 4 16ths. 4 beats × 3 = 12 notes total.
    assert len(note_ons) == 12


def test_melodic_line_triplet_prob_zero_leaves_base_grid_intact() -> None:
    line = MelodicLine(midi_channel=3)
    events = line.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "triplet_prob": 0.0}),
    )
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


# ---------------------------------------------------- cycle knobs


def _pitch_seq(line: MelodicLine, *, bar: int, knobs: dict[str, object]) -> tuple[int, ...]:
    # Pass a bar-specific seed so ctx.rng (used when cycles are "off") varies
    # across bars — that's the per-bar-fresh property the cycle knobs override.
    events = line.generate_bar(_ctx(bar_index=bar, seed=bar, pattern_knobs=knobs))
    return tuple(e.note for e in events if isinstance(e, NoteOn))


def test_melodic_line_pitch_cycle_4_repeats_every_4_bars() -> None:
    line = MelodicLine(midi_channel=3)
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "4"}
    seqs = {b: _pitch_seq(line, bar=b, knobs=knobs) for b in range(8)}
    assert seqs[0] == seqs[4]
    assert seqs[1] == seqs[5]
    assert seqs[2] == seqs[6]
    assert seqs[3] == seqs[7]
    assert seqs[0] != seqs[1]


def test_melodic_line_pitch_cycle_1_makes_every_bar_identical() -> None:
    line = MelodicLine(midi_channel=3)
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "1"}
    seqs = {_pitch_seq(line, bar=b, knobs=knobs) for b in range(8)}
    assert len(seqs) == 1


def test_melodic_line_pitch_cycle_off_varies_every_bar() -> None:
    line = MelodicLine(midi_channel=3)
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "off"}
    # With part_voice_seed pinned, bar-seeded ctx.rng differs per bar;
    # generated pitch sequences should not be uniform.
    seqs = {_pitch_seq(line, bar=b, knobs=knobs) for b in range(8)}
    assert len(seqs) > 1


def test_melodic_line_combined_cycle_locks_full_bar() -> None:
    line = MelodicLine(midi_channel=3)
    # Both cycles at 4 → bar 0 and bar 4 should have identical pitches AND
    # identical drop patterns (only velocity jitter still varies).
    knobs = {
        "drop_prob": 0.5,
        "pitch_cycle_bars": "4",
        "rhythm_cycle_bars": "4",
        "intensity": 0.0,  # zeroes velocity contribution; jitter still ±5 ticks
    }
    # Compare pitches at the same tick positions across bar 0 vs bar 4.
    e0 = sorted(
        line.generate_bar(_ctx(bar_index=0, seed=0, pattern_knobs=knobs)),
        key=lambda e: (e.tick, isinstance(e, NoteOff)),
    )
    e4 = sorted(
        line.generate_bar(_ctx(bar_index=4, seed=4, pattern_knobs=knobs)),
        key=lambda e: (e.tick, isinstance(e, NoteOff)),
    )
    pitches_0 = [(e.tick, e.note) for e in e0 if isinstance(e, NoteOn)]
    pitches_4 = [(e.tick, e.note) for e in e4 if isinstance(e, NoteOn)]
    assert pitches_0 == pitches_4


def test_melodic_line_pitch_cycle_part_locks_across_part() -> None:
    line = MelodicLine(midi_channel=3)
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "part"}
    seqs = {_pitch_seq(line, bar=b, knobs=knobs) for b in [0, 3, 7, 17, 65]}
    assert len(seqs) == 1


# ---------------------------------------------------------------- arp


def test_arp_up_climbs_chord_tones() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "up", "quality": "minor", "subdivision": "4"})
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # subdivision="4" → 4 arp notes per bar; 1 octave × 3 intervals.
    assert [e.note for e in note_ons] == [69, 72, 76, 69]


def test_arp_down_descends() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "down", "quality": "minor", "subdivision": "4"})
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
                "subdivision": "2",
            }
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # subdivision="2" → 2 notes per bar; 3-rung unison-octave ladder.
    assert [e.note for e in note_ons] == [69, 81]


def test_arp_random_stays_within_ladder() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "random", "quality": "minor", "subdivision": "16"})
    )
    ladder = {69, 72, 76}
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert all(e.note in ladder for e in note_ons)


def test_arp_walk_takes_steps_of_one() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "walk", "quality": "minor", "subdivision": "8"})
    )
    ladder = [69, 72, 76]
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # Each consecutive walk note should be one ladder index away
    # (or clamped at the boundary).
    indices = [ladder.index(e.note) for e in note_ons]
    for prev, curr in zip(indices, indices[1:], strict=False):
        assert abs(prev - curr) <= 1


def test_arp_subdivision_4_produces_4_arp_notes_per_bar() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "4"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 4


def test_arp_subdivision_16_produces_16_arp_notes() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "16"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 16


def test_arp_subdivision_8t_produces_triplet_grid() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "8t"}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # 8t at PPQ=480 → spacing 160 ticks → 12 positions per 1920-tick bar.
    assert len(note_ons) == 12
    assert [e.tick for e in note_ons[:4]] == [0, 160, 320, 480]


def test_arp_subdivision_16t_produces_24_notes() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "16t"}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # 16t spacing 80 ticks → 24 positions per bar.
    assert len(note_ons) == 24


def test_arp_gate_controls_duration() -> None:
    arp = Arp(midi_channel=4)
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "4", "gate": 0.25}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    note_offs = sorted((e for e in events if isinstance(e, NoteOff)), key=lambda e: e.tick)
    # quarter-note subdivision = 480 ticks; gate 0.25 → duration = 120.
    for on, off in zip(note_ons, note_offs, strict=True):
        assert off.tick - on.tick == 120


def test_arp_unknown_mode_raises() -> None:
    arp = Arp(midi_channel=4)
    with pytest.raises(ValueError, match="unknown mode"):
        arp.generate_bar(_ctx(pattern_knobs={"mode": "bogus", "subdivision": "4"}))


def test_arp_unknown_subdivision_raises() -> None:
    arp = Arp(midi_channel=4)
    with pytest.raises(ValueError, match="unknown subdivision"):
        arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "bogus"}))


def test_arp_chord_root_semitones_transposes() -> None:
    arp = Arp(midi_channel=4)
    ctx = _ctx(pattern_knobs={"mode": "up", "quality": "unison", "subdivision": "4"})
    ctx.chord_root_semitones = 5
    events = arp.generate_bar(ctx)
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert all(e.note == 69 + 5 for e in note_ons)
