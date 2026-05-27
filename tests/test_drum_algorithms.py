"""Tests for drum_pattern + drum_one_shot.

Algorithms are tested in isolation: construct a BarContext by hand,
call ``generate_bar``, assert the events. No scheduler involved.
"""

from __future__ import annotations

import random

from jtx.algorithms import DrumOneShot, DrumPattern
from jtx.algorithms._euclid import euclid
from jtx.engine.context import BarContext
from jtx.engine.events import NoteOff, NoteOn
from jtx.model.song import Key


def _ctx(pattern_knobs: dict[str, object]) -> BarContext:
    return BarContext(
        bar_index=0,
        tick_offset=0,
        ticks_per_bar=1920,  # 4/4 at PPQ 480
        tempo_bpm=120.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs,
        rng=random.Random(0),
    )


# ----------------------------------------------------------------- euclid


def test_euclid_zero_pulses() -> None:
    assert euclid(0, 16) == [False] * 16


def test_euclid_full_pulses() -> None:
    assert euclid(16, 16) == [True] * 16


def test_euclid_4_in_16_is_four_on_floor() -> None:
    # 4 pulses evenly over 16 steps = beats 0, 4, 8, 12.
    p = euclid(4, 16)
    assert [i for i, b in enumerate(p) if b] == [0, 4, 8, 12]


def test_euclid_8_in_16_is_eighth_notes() -> None:
    p = euclid(8, 16)
    assert [i for i, b in enumerate(p) if b] == list(range(0, 16, 2))


def test_euclid_offset_rotates_pattern() -> None:
    # 2-pulse pattern is asymmetric under a 4-step rotation, so the
    # shift is observable. (4-pulse is rotationally symmetric on a
    # 16-step grid — rotating by 4 just relabels indices.)
    base = euclid(2, 16, offset=0)
    rotated = euclid(2, 16, offset=4)
    assert [i for i, b in enumerate(base) if b] == [0, 8]
    assert [i for i, b in enumerate(rotated) if b] == [4, 12]
    assert sum(base) == sum(rotated) == 2


def test_euclid_overflow_pulses_clamps_to_all_true() -> None:
    assert euclid(20, 16) == [True] * 16


# ---------------------------------------------------------- drum_pattern


def test_drum_pattern_four_floor_kick() -> None:
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    events = kick.generate_bar(_ctx({"style": "four_floor", "velocity": 110}))

    note_ons = [e for e in events if isinstance(e, NoteOn)]
    note_offs = [e for e in events if isinstance(e, NoteOff)]
    assert len(note_ons) == 4
    assert len(note_offs) == 4

    step_ticks = 480 // 4  # 120
    assert [e.tick for e in note_ons] == [0, 4 * step_ticks, 8 * step_ticks, 12 * step_ticks]
    assert all(e.note == 36 and e.channel == 10 and e.velocity == 110 for e in note_ons)


def test_drum_pattern_euclid_uses_piece_defaults() -> None:
    snare = DrumPattern(piece="snare", midi_channel=10, midi_note=38)
    events = snare.generate_bar(_ctx({"style": "euclid"}))

    # Snare default: pulses=2, offset=4 → hits at step 4 and step 12.
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    step_ticks = 120
    assert [e.tick for e in note_ons] == [4 * step_ticks, 12 * step_ticks]


def test_drum_pattern_break_kick() -> None:
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    events = kick.generate_bar(_ctx({"style": "break"}))

    note_ons = [e for e in events if isinstance(e, NoteOn)]
    step_ticks = 120
    # Amen-flavoured kick: steps 0, 7, 10.
    assert [e.tick for e in note_ons] == [0, 7 * step_ticks, 10 * step_ticks]


def test_drum_pattern_break_unknown_piece_falls_back_to_euclid() -> None:
    bell = DrumPattern(piece="cowbell", midi_channel=10, midi_note=56)
    events = bell.generate_bar(_ctx({"style": "break", "pulses": 4}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # cowbell has no break entry → euclid(4, 16) → [0, 4, 8, 12]
    assert [e.tick for e in note_ons] == [0, 4 * 120, 8 * 120, 12 * 120]


def test_drum_pattern_ghost_layer_adds_off_step_hits() -> None:
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    events = kick.generate_bar(
        _ctx({"style": "four_floor", "ghost": 1.0, "ghost_velocity_ratio": 0.5})
    )

    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # 4 main hits + 8 ghost hits (every odd step among 0..15) = 12.
    assert len(note_ons) == 4 + 8
    ghosts = [e for e in note_ons if e.velocity < 110]
    assert len(ghosts) == 8
    # Ghosts land on odd-numbered steps only.
    assert all((e.tick // 120) % 2 == 1 for e in ghosts)


def test_drum_pattern_polyrhythm_overlay() -> None:
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    events = kick.generate_bar(_ctx({"style": "four_floor", "polyrhythm": 3}))

    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # 4 main + 3 poly = 7 hits (poly steps that overlap main are skipped).
    # euclid(3, 16) = [0, 5, 10]; step 0 overlaps main (4-on-floor).
    # So we get 4 + 2 = 6.
    assert len(note_ons) == 6


def test_drum_pattern_velocity_clamped() -> None:
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    events = kick.generate_bar(_ctx({"style": "four_floor", "velocity": 200}))
    assert all(isinstance(e, NoteOn) and e.velocity == 127 for e in events if isinstance(e, NoteOn))


def test_drum_pattern_rejects_unknown_style() -> None:
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    import pytest

    with pytest.raises(ValueError, match="unknown style"):
        kick.generate_bar(_ctx({"style": "bogus"}))


def test_drum_pattern_emits_short_fixed_note_off() -> None:
    """Drum samples ignore note-off, so we just emit a short housekeeping off."""
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    events = kick.generate_bar(_ctx({"style": "four_floor"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    note_offs = [e for e in events if isinstance(e, NoteOff)]
    for on, off in zip(note_ons, note_offs, strict=True):
        # 30 ticks ≈ 32nd note — fixed by the algorithm, not user-tunable.
        assert off.tick - on.tick == 30


def test_drum_pattern_emits_in_step_order() -> None:
    kick = DrumPattern(piece="kick", midi_channel=10, midi_note=36)
    events = kick.generate_bar(_ctx({"style": "four_floor"}))
    note_ons = [e.tick for e in events if isinstance(e, NoteOn)]
    assert note_ons == sorted(note_ons)


# --------------------------------------------------------- drum_one_shot


def test_drum_one_shot_emits_on_euclid_distribution() -> None:
    clap = DrumOneShot(midi_channel=10, midi_note=39)
    events = clap.generate_bar(_ctx({"pulses": 2, "offset": 4, "velocity": 100}))

    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # euclid(2, 16, offset=4) lands hits on 4 and 12.
    assert [e.tick for e in note_ons] == [4 * 120, 12 * 120]
    assert all(e.note == 39 and e.channel == 10 for e in note_ons)


def test_drum_one_shot_zero_pulses_emits_nothing() -> None:
    crash = DrumOneShot(midi_channel=10, midi_note=49)
    assert crash.generate_bar(_ctx({"pulses": 0})) == []
