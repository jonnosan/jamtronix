"""Tests for drum_pattern + drum_one_shot.

Schema v3: both algorithms are MIDI-naive — they emit ``Hit`` events
(``instrument`` may be ``None`` on a single-piece drum slot; voicing
resolves the slot's note + channel). No MIDI channel / note arguments.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import DrumOneShot, DrumPattern
from jtx.algorithms._euclid import euclid
from jtx.engine.context import BarContext
from jtx.model.events import Hit
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


def _ticks(events: list) -> list[int]:
    return [e.tick for e in events if isinstance(e, Hit)]


def _vels(events: list) -> list[int]:
    return [e.velocity for e in events if isinstance(e, Hit)]


# ----------------------------------------------------------------- euclid


def test_euclid_zero_pulses() -> None:
    assert euclid(0, 16) == [False] * 16


def test_euclid_full_pulses() -> None:
    assert euclid(16, 16) == [True] * 16


def test_euclid_4_in_16_is_four_on_floor() -> None:
    p = euclid(4, 16)
    assert [i for i, b in enumerate(p) if b] == [0, 4, 8, 12]


def test_euclid_8_in_16_is_eighth_notes() -> None:
    p = euclid(8, 16)
    assert [i for i, b in enumerate(p) if b] == list(range(0, 16, 2))


def test_euclid_offset_rotates_pattern() -> None:
    base = euclid(2, 16, offset=0)
    rotated = euclid(2, 16, offset=4)
    assert [i for i, b in enumerate(base) if b] == [0, 8]
    assert [i for i, b in enumerate(rotated) if b] == [4, 12]
    assert sum(base) == sum(rotated) == 2


def test_euclid_overflow_pulses_clamps_to_all_true() -> None:
    assert euclid(20, 16) == [True] * 16


# ---------------------------------------------------------- drum_pattern


def test_drum_pattern_four_floor_kick() -> None:
    kick = DrumPattern(piece="kick")
    events = kick.generate_bar(_ctx({"style": "four_floor", "velocity": 110}))

    hits = [e for e in events if isinstance(e, Hit)]
    assert len(hits) == 4
    step = 120  # 16th at PPQ 480
    assert [h.tick for h in hits] == [0, 4 * step, 8 * step, 12 * step]
    assert all(h.velocity == 110 for h in hits)
    assert all(h.instrument is None for h in hits)
    assert all(h.duration_ticks == 30 for h in hits)


def test_drum_pattern_euclid_uses_piece_defaults() -> None:
    snare = DrumPattern(piece="snare")
    events = snare.generate_bar(_ctx({"style": "euclid"}))

    # Snare default: pulses=2, offset=4 → hits at step 4 and step 12.
    assert _ticks(events) == [4 * 120, 12 * 120]


def test_drum_pattern_break_kick() -> None:
    kick = DrumPattern(piece="kick")
    events = kick.generate_bar(_ctx({"style": "break"}))
    # Amen-flavoured kick: steps 0, 7, 10.
    assert _ticks(events) == [0, 7 * 120, 10 * 120]


def test_drum_pattern_break_unknown_piece_falls_back_to_euclid() -> None:
    triangle = DrumPattern(piece="triangle")
    events = triangle.generate_bar(_ctx({"style": "break", "pulses": 4}))
    assert _ticks(events) == [0, 4 * 120, 8 * 120, 12 * 120]


def test_drum_pattern_ghost_layer_adds_off_step_hits() -> None:
    kick = DrumPattern(piece="kick")
    events = kick.generate_bar(
        _ctx({"style": "four_floor", "ghost": 1.0, "ghost_velocity_ratio": 0.5})
    )

    hits = [e for e in events if isinstance(e, Hit)]
    # 4 main hits + 8 ghost hits (every odd step among 0..15) = 12.
    assert len(hits) == 4 + 8
    ghosts = [h for h in hits if h.velocity < 110]
    assert len(ghosts) == 8
    assert all((h.tick // 120) % 2 == 1 for h in ghosts)


def test_drum_pattern_polyrhythm_overlay() -> None:
    kick = DrumPattern(piece="kick")
    events = kick.generate_bar(_ctx({"style": "four_floor", "polyrhythm": 3}))
    hits = [e for e in events if isinstance(e, Hit)]
    # 4 main + euclid(3,16) minus the overlap at step 0 = 6.
    assert len(hits) == 6


def test_drum_pattern_velocity_clamped() -> None:
    kick = DrumPattern(piece="kick")
    events = kick.generate_bar(_ctx({"style": "four_floor", "velocity": 200}))
    assert all(h.velocity == 127 for h in events if isinstance(h, Hit))


def test_drum_pattern_rejects_unknown_style() -> None:
    kick = DrumPattern(piece="kick")
    with pytest.raises(ValueError, match="unknown style"):
        kick.generate_bar(_ctx({"style": "bogus"}))


def test_drum_pattern_emits_short_fixed_duration() -> None:
    """Drum samples ignore note-off — duration is housekeeping only."""
    kick = DrumPattern(piece="kick")
    events = kick.generate_bar(_ctx({"style": "four_floor"}))
    for h in events:
        if isinstance(h, Hit):
            assert h.duration_ticks == 30


def test_drum_pattern_emits_in_step_order() -> None:
    kick = DrumPattern(piece="kick")
    events = kick.generate_bar(_ctx({"style": "four_floor"}))
    ticks = _ticks(events)
    assert ticks == sorted(ticks)


def test_drum_pattern_instrument_name_threaded_through() -> None:
    """When the instantiator supplies an instrument_name, every Hit carries it."""
    kick = DrumPattern(piece="kick", instrument_name="bd")
    events = kick.generate_bar(_ctx({"style": "four_floor"}))
    assert all(h.instrument == "bd" for h in events if isinstance(h, Hit))


# --------------------------------------------------------- drum_one_shot


def test_drum_one_shot_emits_on_euclid_distribution() -> None:
    clap = DrumOneShot()
    events = clap.generate_bar(_ctx({"pulses": 2, "offset": 4, "velocity": 100}))
    # euclid(2, 16, offset=4) lands hits on 4 and 12.
    assert _ticks(events) == [4 * 120, 12 * 120]
    assert all(h.instrument is None for h in events if isinstance(h, Hit))


def test_drum_one_shot_zero_pulses_emits_nothing() -> None:
    crash = DrumOneShot()
    assert crash.generate_bar(_ctx({"pulses": 0})) == []


# ----------------------------------------------- triplet rolls + polyrhythm


def test_drum_pattern_roll_last_beat_fires_every_bar() -> None:
    hat = DrumPattern(piece="hat")
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
    ticks = sorted(_ticks(events))
    expected_roll_ticks = [1440 + i * 80 for i in range(6)]
    assert ticks == expected_roll_ticks


def test_drum_pattern_roll_last_bar_of_4_only_on_bar3() -> None:
    hat = DrumPattern(piece="hat")
    knobs = {
        "style": "euclid",
        "pulses": 0,
        "roll_pos": "last_bar_of_4",
        "roll_subdiv": "16t",
        "roll_depth": 1.0,
    }
    bar0 = hat.generate_bar(_ctx(knobs, bar_index=0))
    bar3 = hat.generate_bar(_ctx(knobs, bar_index=3))
    assert [e for e in bar0 if isinstance(e, Hit)] == []
    assert len([e for e in bar3 if isinstance(e, Hit)]) == 6


def test_drum_pattern_polyrhythm_triplet_grid() -> None:
    hat = DrumPattern(piece="hat")
    events = hat.generate_bar(
        _ctx(
            {
                "style": "four_floor",
                "pulses": 0,
                "polyrhythm": 12,
                "polyrhythm_subdiv": "8t",
            }
        )
    )
    hits = sorted((e for e in events if isinstance(e, Hit)), key=lambda e: e.tick)
    # Main hits at 0/480/960/1440. 12 8t positions, 4 overlap with main → 4 + 8 = 12.
    assert len(hits) == 4 + 8


def test_drum_one_shot_roll_last_bar_of_8_only_fires_on_bar7() -> None:
    tom = DrumOneShot()
    knobs = {
        "pulses": 0,
        "roll_pos": "last_bar_of_8",
        "roll_subdiv": "16t",
        "roll_depth": 1.0,
    }
    bar0 = tom.generate_bar(_ctx(knobs, bar_index=0))
    bar7 = tom.generate_bar(_ctx(knobs, bar_index=7))
    assert [e for e in bar0 if isinstance(e, Hit)] == []
    hits7 = [e for e in bar7 if isinstance(e, Hit)]
    assert len(hits7) == 6
    velocities = [h.velocity for h in hits7]
    assert velocities[0] < velocities[-1]


def test_drum_pattern_clave_break_pattern_is_3_2_son() -> None:
    clave = DrumPattern(piece="clave")
    events = clave.generate_bar(_ctx({"style": "break"}))
    ticks = sorted(_ticks(events))
    assert [t // 120 for t in ticks] == [0, 3, 6, 10, 12]


def test_drum_pattern_cowbell_default_euclid() -> None:
    cb = DrumPattern(piece="cowbell")
    events = cb.generate_bar(_ctx({"style": "euclid"}))
    assert len([e for e in events if isinstance(e, Hit)]) == 4


def test_drum_pattern_shaker_continuous_sixteenths() -> None:
    shk = DrumPattern(piece="shaker")
    events = shk.generate_bar(_ctx({"style": "break"}))
    assert len([e for e in events if isinstance(e, Hit)]) == 16


def test_drum_one_shot_roll_none_is_no_op() -> None:
    tom = DrumOneShot()
    events = tom.generate_bar(_ctx({"pulses": 2, "offset": 4, "roll_pos": "none"}))
    assert _ticks(events) == [480, 1440]
