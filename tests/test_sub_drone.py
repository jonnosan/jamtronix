"""Tests for the sub_drone algorithm."""

from __future__ import annotations

import random

from jtx.algorithms import SubDrone
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, NoteOff, NoteOn
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


def test_sub_drone_emits_one_note_per_bar() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx())
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    note_offs = [e for e in events if isinstance(e, NoteOff)]
    assert len(note_ons) == 1
    assert len(note_offs) == 1


def test_sub_drone_emits_at_register_1_by_default() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx())
    note_on = next(e for e in events if isinstance(e, NoteOn))
    # A1 = MIDI 33.
    assert note_on.note == 33


def test_sub_drone_octave_knob_shifts_register() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx(pattern_knobs={"octave": 1}))
    note_on = next(e for e in events if isinstance(e, NoteOn))
    # A2 = 45.
    assert note_on.note == 45


def test_sub_drone_cell_pattern_root_first() -> None:
    drone = SubDrone(midi_channel=1)
    # bars_per_chord=2 → bars 0,1 = root; bars 2,3 = fifth.
    bar0 = drone.generate_bar(_ctx(pattern_knobs={"fifth_prob": 0.0}, bar_index=0))
    bar1 = drone.generate_bar(_ctx(pattern_knobs={"fifth_prob": 0.0}, bar_index=1))
    bar2 = drone.generate_bar(_ctx(pattern_knobs={"fifth_prob": 0.0}, bar_index=2))
    bar3 = drone.generate_bar(_ctx(pattern_knobs={"fifth_prob": 0.0}, bar_index=3))

    n0 = next(e for e in bar0 if isinstance(e, NoteOn))
    n1 = next(e for e in bar1 if isinstance(e, NoteOn))
    n2 = next(e for e in bar2 if isinstance(e, NoteOn))
    n3 = next(e for e in bar3 if isinstance(e, NoteOn))

    # Root (A1=33) bars 0/1, fifth (E2=40) bars 2/3.
    assert n0.note == n1.note == 33
    assert n2.note == n3.note == 40


def test_sub_drone_bars_per_chord_one_alternates_every_bar() -> None:
    drone = SubDrone(midi_channel=1)
    pitches: list[int] = []
    for bar_idx in range(4):
        events = drone.generate_bar(
            _ctx(pattern_knobs={"fifth_prob": 0.0, "bars_per_chord": 1}, bar_index=bar_idx)
        )
        pitches.append(next(e.note for e in events if isinstance(e, NoteOn)))
    assert pitches == [33, 40, 33, 40]


def test_sub_drone_fifth_prob_one_always_emits_fifth() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx(pattern_knobs={"fifth_prob": 1.0}, bar_index=0))
    note_on = next(e for e in events if isinstance(e, NoteOn))
    assert note_on.note == 40  # E2 is the fifth above A1


def test_sub_drone_chord_root_semitones_transposes() -> None:
    drone = SubDrone(midi_channel=1)
    ctx = _ctx(pattern_knobs={"fifth_prob": 0.0}, bar_index=0)
    ctx.chord_root_semitones = 5  # IV in A minor → D1 = 38.
    events = drone.generate_bar(ctx)
    note_on = next(e for e in events if isinstance(e, NoteOn))
    assert note_on.note == 38


def test_sub_drone_gate_controls_note_off_offset() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx(pattern_knobs={"gate": 0.5}))
    note_off = next(e for e in events if isinstance(e, NoteOff))
    assert note_off.tick == 1920 // 2


def test_sub_drone_kick_env_zero_emits_no_cc() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx(pattern_knobs={"kick_env": 0.0}))
    assert not any(isinstance(e, ControlChange) for e in events)


def test_sub_drone_kick_env_emits_cc74_envelope_per_beat() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx(pattern_knobs={"kick_env": 1.0}))
    ccs = [e for e in events if isinstance(e, ControlChange) and e.cc == 74]
    # 4 beats per bar × 4 events per beat = 16 CC74 events.
    assert len(ccs) == 16
    # All values inside 0..127.
    assert all(0 <= c.value <= 127 for c in ccs)


def test_sub_drone_kick_env_starts_low_ramps_high_each_beat() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx(pattern_knobs={"kick_env": 1.0}))
    ccs = sorted(
        (e for e in events if isinstance(e, ControlChange) and e.cc == 74),
        key=lambda e: e.tick,
    )
    # First sample of each beat should be the "low" floor (20),
    # last sample should approach 120.
    beats_per_bar = 4
    samples_per_beat = 4
    for beat in range(beats_per_bar):
        beat_first = ccs[beat * samples_per_beat]
        beat_last = ccs[beat * samples_per_beat + samples_per_beat - 1]
        assert beat_first.value == 20
        assert beat_last.value == 120


def test_sub_drone_velocity_around_base_vel() -> None:
    drone = SubDrone(midi_channel=1)
    events = drone.generate_bar(_ctx(pattern_knobs={"base_vel": 80}))
    note_on = next(e for e in events if isinstance(e, NoteOn))
    # ±3 random jitter from the seeded RNG.
    assert 77 <= note_on.velocity <= 83
