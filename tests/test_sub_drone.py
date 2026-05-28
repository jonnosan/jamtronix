"""Tests for the sub_drone algorithm.

Schema v3: emits :class:`Note` for the held bass tone and
:class:`Param` events (function ``cutoff``, value in [0, 1]) for the
kick-env CC74 envelope.
"""

from __future__ import annotations

import random

from jtx.algorithms import SubDrone
from jtx.engine.context import BarContext
from jtx.model.events import Note, Param
from jtx.model.song import Key


def _ctx(*, pattern_knobs: dict[str, object] | None = None, bar_index: int = 0) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(0),
    )


def _notes(events) -> list[Note]:
    return [e for e in events if isinstance(e, Note)]


def _cutoff(events) -> list[Param]:
    return [e for e in events if isinstance(e, Param) and e.name == "cutoff"]


def test_sub_drone_emits_one_note_per_bar() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx())
    assert len(_notes(events)) == 1


def test_sub_drone_emits_at_register_1_by_default() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx())
    assert _notes(events)[0].pitch == 33  # A1


def test_sub_drone_octave_knob_shifts_register() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx(pattern_knobs={"octave": 1}))
    assert _notes(events)[0].pitch == 45  # A2


def test_sub_drone_cell_pattern_root_first() -> None:
    drone = SubDrone()
    pitches = [
        _notes(drone.generate_bar(_ctx(pattern_knobs={"fifth_prob": 0.0}, bar_index=b)))[0].pitch
        for b in range(4)
    ]
    assert pitches == [33, 33, 40, 40]


def test_sub_drone_bars_per_chord_one_alternates_every_bar() -> None:
    drone = SubDrone()
    pitches = [
        _notes(
            drone.generate_bar(
                _ctx(pattern_knobs={"fifth_prob": 0.0, "bars_per_chord": 1}, bar_index=b)
            )
        )[0].pitch
        for b in range(4)
    ]
    assert pitches == [33, 40, 33, 40]


def test_sub_drone_fifth_prob_one_always_emits_fifth() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx(pattern_knobs={"fifth_prob": 1.0}, bar_index=0))
    assert _notes(events)[0].pitch == 40


def test_sub_drone_chord_root_semitones_transposes() -> None:
    drone = SubDrone()
    ctx = _ctx(pattern_knobs={"fifth_prob": 0.0}, bar_index=0)
    ctx.chord_root_semitones = 5  # IV in A minor → D1 = 38.
    events = drone.generate_bar(ctx)
    assert _notes(events)[0].pitch == 38


def test_sub_drone_gate_controls_duration() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx(pattern_knobs={"gate": 0.5}))
    note = _notes(events)[0]
    assert note.duration_ticks == 1920 // 2


def test_sub_drone_kick_env_zero_emits_no_cutoff_param() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx(pattern_knobs={"kick_env": 0.0}))
    assert _cutoff(events) == []


def test_sub_drone_kick_env_emits_per_beat_cutoff_envelope() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx(pattern_knobs={"kick_env": 1.0}))
    cutoffs = _cutoff(events)
    # 4 beats × 4 samples = 16.
    assert len(cutoffs) == 16
    # All values are normalised [0, 1].
    assert all(0.0 <= p.value <= 1.0 for p in cutoffs)


def test_sub_drone_kick_env_starts_low_ramps_high_each_beat() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx(pattern_knobs={"kick_env": 1.0}))
    cutoffs = sorted(_cutoff(events), key=lambda p: p.tick)
    beats_per_bar = 4
    samples_per_beat = 4
    for beat in range(beats_per_bar):
        first = cutoffs[beat * samples_per_beat]
        last = cutoffs[beat * samples_per_beat + samples_per_beat - 1]
        # Floor = 20/127, ceiling = 120/127.
        assert first.value == pytest_approx(20 / 127.0)
        assert last.value == pytest_approx(120 / 127.0)


def test_sub_drone_velocity_around_base_vel() -> None:
    drone = SubDrone()
    events = drone.generate_bar(_ctx(pattern_knobs={"base_vel": 80}))
    note = _notes(events)[0]
    assert 77 <= note.velocity <= 83


def pytest_approx(value: float, tol: float = 1e-6) -> object:
    """Tiny inline approx — used inline to keep this test file free of fixtures."""
    import pytest as _pytest

    return _pytest.approx(value, abs=tol)
