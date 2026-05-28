"""Tests for melodic_line + arp algorithms.

Schema v3: both emit abstract :class:`Note` events (pitch + duration_ticks).
The voicing stage adds the MIDI channel at SongPlayer level.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import Arp, MelodicLine
from jtx.algorithms._theory import scale_intervals
from jtx.engine.context import BarContext
from jtx.model.events import Note
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


def _notes(events) -> list[Note]:
    return [e for e in events if isinstance(e, Note)]


# ----------------------------------------------------------------- scales


def test_scale_intervals_known() -> None:
    assert scale_intervals("minor") == (0, 2, 3, 5, 7, 8, 10)
    assert scale_intervals("major") == (0, 2, 4, 5, 7, 9, 11)
    assert scale_intervals("dorian") == (0, 2, 3, 5, 7, 9, 10)


def test_scale_intervals_unknown_falls_back_to_minor() -> None:
    assert scale_intervals("bogus") == scale_intervals("minor")


# ----------------------------------------------------------- melodic_line


def test_melodic_line_pitches_within_scale() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0}))
    expected = {69, 72, 76, 77, 81}
    assert all(n.pitch in expected for n in _notes(events))


def test_melodic_line_drop_prob_one_emits_nothing() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0}))
    assert _notes(events) == []


def test_melodic_line_drop_prob_zero_fills_all_positions_default_grid() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0}))
    assert len(_notes(events)) == 16


def test_melodic_line_subdivision_8_fills_eight_positions() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "subdivision": "8"}))
    assert len(_notes(events)) == 8


def test_melodic_line_subdivision_16t_uses_triplet_grid() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "subdivision": "16t"}))
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert len(notes) == 24
    assert [n.tick for n in notes[:3]] == [0, 80, 160]


def test_melodic_line_triplet_prob_inserts_triplet_runs() -> None:
    line = MelodicLine()
    events = line.generate_bar(
        _ctx(
            pattern_knobs={
                "drop_prob": 0.0,
                "triplet_prob": 1.0,
                "triplet_subdiv": "16t",
            }
        )
    )
    assert len(_notes(events)) == 12


def test_melodic_line_triplet_prob_zero_leaves_base_grid_intact() -> None:
    line = MelodicLine()
    events = line.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "triplet_prob": 0.0}),
    )
    assert len(_notes(events)) == 16


def test_melodic_line_palette_constrains_pitches() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "palette": "triad"}))
    assert all(n.pitch in {69, 72, 76} for n in _notes(events))


def test_melodic_line_low_palette_reaches_below_root() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "palette": "low"}))
    assert any(n.pitch < 69 for n in _notes(events))


def test_melodic_line_chord_root_semitones_transposes() -> None:
    line = MelodicLine()
    ctx = _ctx(pattern_knobs={"drop_prob": 0.0, "palette": "triad"})
    ctx.chord_root_semitones = 5
    events = line.generate_bar(ctx)
    assert all(n.pitch in {74, 77, 81} for n in _notes(events))


def test_melodic_line_passing_tone_inserts_chromatic_neighbour() -> None:
    line = MelodicLine()
    events = line.generate_bar(
        _ctx(
            pattern_knobs={
                "drop_prob": 0.0,
                "palette": "tones_only",
                "passing_prob": 1.0,
            }
        )
    )
    pitches_seen = {n.pitch for n in _notes(events)}
    palette_pitches = {69, 72, 76, 77, 81}
    assert pitches_seen - palette_pitches  # at least one chromatic neighbour


def test_melodic_line_gate_controls_duration() -> None:
    line = MelodicLine()
    events = line.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "gate": 0.25}))
    notes = _notes(events)
    # Each base-grid note: duration = int(120 * 0.25) = 30.
    assert any(n.duration_ticks == 30 for n in notes)


def test_melodic_line_uses_key_scale() -> None:
    line = MelodicLine()
    events = line.generate_bar(
        _ctx(scale="major", pattern_knobs={"drop_prob": 0.0, "palette": "triad"})
    )
    assert all(n.pitch in {69, 73, 76} for n in _notes(events))


# ---------------------------------------------------- cycle knobs


def _pitch_seq(line: MelodicLine, *, bar: int, knobs: dict[str, object]) -> tuple[int, ...]:
    events = line.generate_bar(_ctx(bar_index=bar, seed=bar, pattern_knobs=knobs))
    return tuple(n.pitch for n in _notes(events))


def test_melodic_line_pitch_cycle_4_repeats_every_4_bars() -> None:
    line = MelodicLine()
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "4"}
    seqs = {b: _pitch_seq(line, bar=b, knobs=knobs) for b in range(8)}
    assert seqs[0] == seqs[4]
    assert seqs[1] == seqs[5]
    assert seqs[2] == seqs[6]
    assert seqs[3] == seqs[7]
    assert seqs[0] != seqs[1]


def test_melodic_line_pitch_cycle_1_makes_every_bar_identical() -> None:
    line = MelodicLine()
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "1"}
    seqs = {_pitch_seq(line, bar=b, knobs=knobs) for b in range(8)}
    assert len(seqs) == 1


def test_melodic_line_pitch_cycle_off_varies_every_bar() -> None:
    line = MelodicLine()
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "off"}
    seqs = {_pitch_seq(line, bar=b, knobs=knobs) for b in range(8)}
    assert len(seqs) > 1


def test_melodic_line_combined_cycle_locks_full_bar() -> None:
    line = MelodicLine()
    knobs = {
        "drop_prob": 0.5,
        "pitch_cycle_bars": "4",
        "rhythm_cycle_bars": "4",
        "intensity": 0.0,
    }
    e0 = sorted(
        line.generate_bar(_ctx(bar_index=0, seed=0, pattern_knobs=knobs)),
        key=lambda e: e.tick,
    )
    e4 = sorted(
        line.generate_bar(_ctx(bar_index=4, seed=4, pattern_knobs=knobs)),
        key=lambda e: e.tick,
    )
    pitches_0 = [(n.tick, n.pitch) for n in _notes(e0)]
    pitches_4 = [(n.tick, n.pitch) for n in _notes(e4)]
    assert pitches_0 == pitches_4


def test_melodic_line_pitch_cycle_part_locks_across_part() -> None:
    line = MelodicLine()
    knobs = {"drop_prob": 0.0, "pitch_cycle_bars": "part"}
    seqs = {_pitch_seq(line, bar=b, knobs=knobs) for b in [0, 3, 7, 17, 65]}
    assert len(seqs) == 1


# ---------------------------------------------------------------- arp


def test_arp_up_climbs_chord_tones() -> None:
    arp = Arp()
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "up", "quality": "minor", "subdivision": "4"})
    )
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert [n.pitch for n in notes] == [69, 72, 76, 69]


def test_arp_down_descends() -> None:
    arp = Arp()
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "down", "quality": "minor", "subdivision": "4"})
    )
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert [n.pitch for n in notes] == [76, 72, 69, 76]


def test_arp_octaves_extends_range() -> None:
    arp = Arp()
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
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert [n.pitch for n in notes] == [69, 81]


def test_arp_random_stays_within_ladder() -> None:
    arp = Arp()
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "random", "quality": "minor", "subdivision": "16"})
    )
    ladder = {69, 72, 76}
    assert all(n.pitch in ladder for n in _notes(events))


def test_arp_walk_takes_steps_of_one() -> None:
    arp = Arp()
    events = arp.generate_bar(
        _ctx(pattern_knobs={"mode": "walk", "quality": "minor", "subdivision": "8"})
    )
    ladder = [69, 72, 76]
    notes = sorted(_notes(events), key=lambda n: n.tick)
    indices = [ladder.index(n.pitch) for n in notes]
    for prev, curr in zip(indices, indices[1:], strict=False):
        assert abs(prev - curr) <= 1


def test_arp_subdivision_4_produces_4_arp_notes_per_bar() -> None:
    arp = Arp()
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "4"}))
    assert len(_notes(events)) == 4


def test_arp_subdivision_16_produces_16_arp_notes() -> None:
    arp = Arp()
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "16"}))
    assert len(_notes(events)) == 16


def test_arp_subdivision_8t_produces_triplet_grid() -> None:
    arp = Arp()
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "8t"}))
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert len(notes) == 12
    assert [n.tick for n in notes[:4]] == [0, 160, 320, 480]


def test_arp_subdivision_16t_produces_24_notes() -> None:
    arp = Arp()
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "16t"}))
    assert len(_notes(events)) == 24


def test_arp_gate_controls_duration() -> None:
    arp = Arp()
    events = arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "4", "gate": 0.25}))
    notes = sorted(_notes(events), key=lambda n: n.tick)
    for n in notes:
        assert n.duration_ticks == 120


def test_arp_unknown_mode_raises() -> None:
    arp = Arp()
    with pytest.raises(ValueError, match="unknown mode"):
        arp.generate_bar(_ctx(pattern_knobs={"mode": "bogus", "subdivision": "4"}))


def test_arp_unknown_subdivision_raises() -> None:
    arp = Arp()
    with pytest.raises(ValueError, match="unknown subdivision"):
        arp.generate_bar(_ctx(pattern_knobs={"mode": "up", "subdivision": "bogus"}))


def test_arp_chord_root_semitones_transposes() -> None:
    arp = Arp()
    ctx = _ctx(pattern_knobs={"mode": "up", "quality": "unison", "subdivision": "4"})
    ctx.chord_root_semitones = 5
    events = arp.generate_bar(ctx)
    assert all(n.pitch == 69 + 5 for n in _notes(events))
