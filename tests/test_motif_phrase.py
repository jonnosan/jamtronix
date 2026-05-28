"""Tests for the ``motif_phrase`` algorithm.

Covers the load-bearing properties: phrase-stable motif content across A
bars (held via ``ctx.rng_hold``), distinct B content, slot transforms
varying per bar inside the phrase, ``random_walk`` escape hatch, and
progression-mode shifting between slots.
"""

from __future__ import annotations

import random

from jtx.algorithms import MotifPhrase
from jtx.engine.context import BarContext
from jtx.model.events import Note
from jtx.model.song import Key
from jtx.seed import derive_part_voice_seed, seed_from_title


def _ctx(
    *,
    bar_index: int = 0,
    pattern_knobs: dict[str, object] | None = None,
    part_voice_seed: int | None = None,
) -> BarContext:
    pv = (
        part_voice_seed
        if part_voice_seed is not None
        else derive_part_voice_seed(seed_from_title("Phuture"), "drop", "lead")
    )
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,
        tempo_bpm=128.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(bar_index),  # bar-fresh per real playback
        part_voice_seed=pv,
    )


def _pitches(events: list) -> tuple[int, ...]:
    return tuple(e.pitch for e in events if isinstance(e, Note))


def _ticks(events: list) -> tuple[int, ...]:
    return tuple(e.tick for e in events if isinstance(e, Note))


# -- determinism ------------------------------------------------------------


def test_motif_phrase_deterministic() -> None:
    line = MotifPhrase()
    knobs = {"phrase_shape": "A_A_A_B", "phrase_length_bars": 4}
    a = line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs))
    b = line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs))
    assert _pitches(a) == _pitches(b)
    assert _ticks(a) == _ticks(b)


# -- A-bar phrase coherence -------------------------------------------------


def test_a_bars_share_motif_pitch_sequence() -> None:
    # phrase_shape=A_A_A_B with phrase_length_bars=4:
    # bars 0/1/2 are A → should share underlying motif content (pre-transform).
    # We use A_A_A_A to remove the B slot and density to keep the test stable.
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_A_A_A",
        "phrase_length_bars": 4,
        "rhythm_template": "eighth_eighth",
        "contour": "up",
        "density": 1.0,
        "variation_depth": 0.0,
    }
    seqs = [_pitches(line.generate_bar(_ctx(bar_index=b, pattern_knobs=knobs))) for b in range(4)]
    # All A bars should produce the same pitch sequence with variation_depth=0.
    assert seqs[0] == seqs[1] == seqs[2] == seqs[3]


def test_a_a_a_b_b_bar_differs_from_a_bars() -> None:
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_A_A_B",
        "phrase_length_bars": 4,
        "rhythm_template": "eighth_eighth",
        "contour": "up",
        "density": 1.0,
        "variation_depth": 0.0,
        "b_section_difference": 1.0,  # full re-roll
    }
    pa = _pitches(line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs)))
    pb = _pitches(line.generate_bar(_ctx(bar_index=3, pattern_knobs=knobs)))
    # B should be a different motif under "fresh" strategy.
    assert pa != pb


def test_a_b_a_b_pattern_alternates() -> None:
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_B_A_B",
        "phrase_length_bars": 4,
        "rhythm_template": "eighth_eighth",
        "contour": "up",
        "density": 1.0,
        "variation_depth": 0.0,
        "b_section_difference": 1.0,
    }
    p0 = _pitches(line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs)))
    p1 = _pitches(line.generate_bar(_ctx(bar_index=1, pattern_knobs=knobs)))
    p2 = _pitches(line.generate_bar(_ctx(bar_index=2, pattern_knobs=knobs)))
    p3 = _pitches(line.generate_bar(_ctx(bar_index=3, pattern_knobs=knobs)))
    # A_B_A_B: bars 0+2 are A (same), bars 1+3 are B (same), A != B.
    assert p0 == p2
    assert p1 == p3
    assert p0 != p1


# -- variation_depth on A' / A'' -------------------------------------------


def test_aprime_can_differ_from_a_with_variation_depth() -> None:
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_A'_A_A''",
        "phrase_length_bars": 4,
        "rhythm_template": "eighth_eighth",
        "contour": "up",
        "density": 1.0,
        "variation_depth": 1.0,  # max transform intensity
    }
    a = _pitches(line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs)))
    aprime = _pitches(line.generate_bar(_ctx(bar_index=1, pattern_knobs=knobs)))
    # At max variation_depth, A' will compose multiple transforms; pitches
    # should land somewhere different than A. (We don't assert *how* — the
    # exact transforms are bar-rng-driven; we just want the two bars to
    # not be byte-identical.)
    assert a != aprime


def test_zero_variation_depth_keeps_aprime_equal_to_a() -> None:
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_A'_A_A''",
        "phrase_length_bars": 4,
        "rhythm_template": "eighth_eighth",
        "contour": "up",
        "density": 1.0,
        "variation_depth": 0.0,
    }
    a = _pitches(line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs)))
    aprime = _pitches(line.generate_bar(_ctx(bar_index=1, pattern_knobs=knobs)))
    assert a == aprime


# -- random_walk fallback ---------------------------------------------------


def test_random_walk_uses_bar_fresh_rng() -> None:
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "random_walk",
        "rhythm_template": "eighth_eighth",
        "contour": "up",
        "density": 1.0,
    }
    # bar 0 vs bar 1: different bar-seeded ctx.rng → different motifs.
    p0 = _pitches(line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs)))
    p1 = _pitches(line.generate_bar(_ctx(bar_index=1, pattern_knobs=knobs)))
    assert p0 != p1


# -- progression -----------------------------------------------------------


def test_progression_fifths_transposes_second_half_of_phrase() -> None:
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_A_A_A",
        "phrase_length_bars": 4,
        "rhythm_template": "quarter",
        "contour": "pulse",
        "density": 1.0,
        "variation_depth": 0.0,
        "progression_mode": "fifths",
        "progression_range": 4,
    }
    p0 = _pitches(line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs)))
    p2 = _pitches(line.generate_bar(_ctx(bar_index=2, pattern_knobs=knobs)))
    # bar 2 is in the second half (slot 2 of 4) → transposed up a fifth
    # (4 scale steps). p0 and p2 should differ; specifically p2 > p0.
    assert p0 != p2
    assert min(p2) > min(p0)


# -- output shape ----------------------------------------------------------


def test_motif_phrase_emits_note_on_off_pairs() -> None:
    line = MotifPhrase()
    events = line.generate_bar(_ctx(pattern_knobs={"density": 1.0}))
    notes = [e for e in events if isinstance(e, Note)]
    assert len(notes) > 0
    assert all(0 <= e.tick < 1920 for e in notes)


def test_motif_phrase_pitches_in_midi_range() -> None:
    line = MotifPhrase()
    # Extreme knobs that could push pitches out of range; algorithm clamps.
    events = line.generate_bar(
        _ctx(
            pattern_knobs={
                "density": 1.0,
                "octave": 3,
                "progression_mode": "climb_up",
                "progression_range": 7,
                "phrase_length_bars": 2,
            },
            bar_index=1,
        )
    )
    note_ons = [e for e in events if isinstance(e, Note)]
    assert all(0 <= e.pitch <= 127 for e in note_ons)


def test_a_b_a_b_within_phrase_shares_motif_per_slot() -> None:
    # A_B_A_B pattern (length 2) cycles twice within phrase_length_bars=4,
    # so bars 0/2 are both A in the same phrase → identical motif.
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_B_A_B",
        "phrase_length_bars": 4,
        "rhythm_template": "quarter",
        "contour": "pulse",
        "density": 1.0,
        "variation_depth": 0.0,
        "b_section_difference": 1.0,
    }
    p0 = _pitches(line.generate_bar(_ctx(bar_index=0, pattern_knobs=knobs)))
    p1 = _pitches(line.generate_bar(_ctx(bar_index=1, pattern_knobs=knobs)))
    p2 = _pitches(line.generate_bar(_ctx(bar_index=2, pattern_knobs=knobs)))
    p3 = _pitches(line.generate_bar(_ctx(bar_index=3, pattern_knobs=knobs)))
    assert p0 == p2  # both A within same phrase
    assert p1 == p3  # both B within same phrase
    assert p0 != p1  # A vs B differ


def test_motif_evolves_across_phrases() -> None:
    # phrase_length_bars=2 with A_A pattern: bars 0-1 are phrase 0, bars
    # 2-3 are phrase 1 — content RNG epoch advances → motifs differ.
    # Use 'auto' rhythm template so the template itself can vary per phrase
    # (single-template + same-start-degree can collide).
    line = MotifPhrase()
    knobs = {
        "phrase_shape": "A_A_A_A",
        "phrase_length_bars": 2,
        "rhythm_template": "auto",
        "contour": "auto",
        "density": 1.0,
        "variation_depth": 0.0,
    }
    # Sample several phrase pairs — at least one phrase pair must differ
    # (the deterministic per-phrase RNG should rarely happen to coincide).
    seqs = {
        _pitches(line.generate_bar(_ctx(bar_index=b, pattern_knobs=knobs))) for b in [0, 2, 4, 6, 8]
    }
    assert len(seqs) > 1
