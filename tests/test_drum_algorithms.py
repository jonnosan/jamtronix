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


def _ctx(pattern_knobs: dict[str, object], *, bar_index: int = 0, seed: int = 0) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,  # 4/4 at PPQ 480
        tempo_bpm=120.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs,
        rng=random.Random(seed),
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
    triangle = DrumPattern(piece="triangle", midi_channel=10, midi_note=81)
    events = triangle.generate_bar(_ctx({"style": "break", "pulses": 4}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # triangle has no break entry → euclid(4, 16) → [0, 4, 8, 12]
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


# ----------------------------------------------- triplet rolls + polyrhythm


def test_drum_pattern_roll_last_beat_fires_every_bar() -> None:
    hat = DrumPattern(piece="hat", midi_channel=10, midi_note=42)
    events = hat.generate_bar(
        _ctx(
            {
                "style": "euclid",
                "pulses": 0,
                "roll_pos": "last_beat",
                "roll_subdiv": "16t",
                "roll_depth": 1.0,
            }
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # 0 main pulses + roll covers beat 4 = ticks 1440..1920 at 16t spacing 80.
    expected_roll_ticks = [1440 + i * 80 for i in range(6)]
    assert [e.tick for e in note_ons] == expected_roll_ticks


def test_drum_pattern_roll_last_bar_of_4_only_on_bar3() -> None:
    hat = DrumPattern(piece="hat", midi_channel=10, midi_note=42)
    # Disable polyrhythm + ghost; pulses=0 so only the roll appears.
    knobs = {
        "style": "euclid",
        "pulses": 0,
        "roll_pos": "last_bar_of_4",
        "roll_subdiv": "16t",
        "roll_depth": 1.0,
    }
    bar0 = hat.generate_bar(_ctx(knobs, bar_index=0))
    bar3 = hat.generate_bar(_ctx(knobs, bar_index=3))
    assert [e for e in bar0 if isinstance(e, NoteOn)] == []
    note_ons_3 = [e for e in bar3 if isinstance(e, NoteOn)]
    assert len(note_ons_3) == 6  # 6 16t positions in beat 4


def test_drum_pattern_polyrhythm_triplet_grid() -> None:
    hat = DrumPattern(piece="hat", midi_channel=10, midi_note=42)
    events = hat.generate_bar(
        _ctx(
            {
                "style": "four_floor",  # not used for hat — just need a base
                "pulses": 0,
                "polyrhythm": 12,
                "polyrhythm_subdiv": "8t",
            }
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # 8t polyrhythm with 12 pulses = continuous 8th-triplet hat layer.
    # Beats 1+3 (ticks 0 and 960) overlap four-on-the-floor hat skeleton if
    # any; hat piece has 4 main hits at 0/480/960/1440. The 8t grid at
    # 160-tick spacing produces 12 positions; positions at 0 and 960
    # collide with four-floor and get filtered, leaving 10 poly hits + 4 main.
    # But hat piece isn't four_floor by default — style=four_floor forces it.
    # Main hits land at 0/480/960/1440. 8t positions: 0,160,320,480,640,
    # 800,960,1120,1280,1440,1600,1760. Overlap at 0/480/960/1440 (4 collisions).
    # 12 - 4 = 8 poly hits.
    assert len(note_ons) == 4 + 8


def test_drum_one_shot_roll_last_bar_of_8_only_fires_on_bar7() -> None:
    tom = DrumOneShot(midi_channel=10, midi_note=45)
    knobs = {
        "pulses": 0,
        "roll_pos": "last_bar_of_8",
        "roll_subdiv": "16t",
        "roll_depth": 1.0,
    }
    bar0 = tom.generate_bar(_ctx(knobs, bar_index=0))
    bar7 = tom.generate_bar(_ctx(knobs, bar_index=7))
    assert [e for e in bar0 if isinstance(e, NoteOn)] == []
    note_ons_7 = [e for e in bar7 if isinstance(e, NoteOn)]
    assert len(note_ons_7) == 6
    # Velocity ramps up across the fill (crescendo).
    velocities = [e.velocity for e in note_ons_7]
    assert velocities[0] < velocities[-1]


def test_drum_pattern_clave_break_pattern_is_3_2_son() -> None:
    clave = DrumPattern(piece="clave", midi_channel=10, midi_note=75)
    events = clave.generate_bar(_ctx({"style": "break"}))
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # 3-2 son clave: 0, 3, 6, 10, 12.
    assert [e.tick // 120 for e in note_ons] == [0, 3, 6, 10, 12]


def test_drum_pattern_cowbell_default_euclid() -> None:
    cb = DrumPattern(piece="cowbell", midi_channel=10, midi_note=56)
    events = cb.generate_bar(_ctx({"style": "euclid"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # cowbell default: pulses=4, offset=1.
    assert len(note_ons) == 4


def test_drum_pattern_shaker_continuous_sixteenths() -> None:
    shk = DrumPattern(piece="shaker", midi_channel=10, midi_note=70)
    events = shk.generate_bar(_ctx({"style": "break"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 16


def test_drum_one_shot_roll_none_is_no_op() -> None:
    tom = DrumOneShot(midi_channel=10, midi_note=45)
    events = tom.generate_bar(_ctx({"pulses": 2, "offset": 4, "roll_pos": "none"}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # Just the two euclid hits, no roll.
    assert [e.tick for e in note_ons] == [480, 1440]
