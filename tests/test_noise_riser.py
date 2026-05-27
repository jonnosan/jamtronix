"""Tests for the noise_riser algorithm."""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import NoiseRiser
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, NoteOff, NoteOn, PitchBend
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


def test_noise_riser_once_inside_window_emits_note_and_cc() -> None:
    riser = NoiseRiser(midi_channel=7)
    events = riser.generate_bar(
        _ctx(pattern_knobs={"trigger": "once", "duration_bars": 4}, bar_index=0)
    )
    assert any(isinstance(e, NoteOn) for e in events)
    assert any(isinstance(e, NoteOff) for e in events)
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert ccs, "noise_riser should emit CC74 ramp samples"
    assert all(c.cc == 74 for c in ccs)


def test_noise_riser_once_outside_window_silent() -> None:
    riser = NoiseRiser(midi_channel=7)
    # duration_bars=4 → bars 0-3 fire, bar 4 silent.
    events = riser.generate_bar(
        _ctx(pattern_knobs={"trigger": "once", "duration_bars": 4}, bar_index=4)
    )
    assert events == []


def test_noise_riser_every_fires_last_n_bars_of_cycle() -> None:
    riser = NoiseRiser(midi_channel=7)
    knobs = {"trigger": "every", "duration_bars": 4, "cycle_bars": 16}
    silent_bars = [0, 3, 11]
    riser_bars = [12, 13, 14, 15]
    for b in silent_bars:
        assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b)) == []
    for b in riser_bars:
        assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b)), (
            f"expected riser to fire at bar {b}"
        )


def test_noise_riser_last_bar_of_8_only_on_bar7() -> None:
    riser = NoiseRiser(midi_channel=7)
    knobs = {"trigger": "last_bar_of_8"}
    assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=0)) == []
    assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=6)) == []
    assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=7))


def test_noise_riser_velocity_ramps_up_across_window() -> None:
    riser = NoiseRiser(midi_channel=7)
    knobs = {
        "trigger": "once",
        "duration_bars": 4,
        "vel_start": 40,
        "vel_end": 120,
        "curve": "linear",
    }
    note_ons_by_bar = []
    for b in range(4):
        evs = riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b))
        note_ons = [e for e in evs if isinstance(e, NoteOn)]
        assert len(note_ons) == 1
        note_ons_by_bar.append(note_ons[0].velocity)
    # Velocity increases across the riser window.
    for prev, curr in zip(note_ons_by_bar, note_ons_by_bar[1:], strict=False):
        assert curr >= prev


def test_noise_riser_cutoff_ramps_up() -> None:
    riser = NoiseRiser(midi_channel=7)
    knobs = {
        "trigger": "once",
        "duration_bars": 1,  # whole rise within one bar
        "cutoff_start": 20,
        "cutoff_end": 110,
        "curve": "linear",
        "samples_per_bar": 8,
    }
    events = riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=0))
    ccs = sorted((e for e in events if isinstance(e, ControlChange)), key=lambda c: c.tick)
    # First CC should be near cutoff_start; last near cutoff_end.
    assert ccs[0].value <= 40
    assert ccs[-1].value >= 90


def test_noise_riser_pitch_bend_when_pitch_rise_nonzero() -> None:
    riser = NoiseRiser(midi_channel=7)
    knobs = {
        "trigger": "once",
        "duration_bars": 1,
        "pitch_rise_cents": 200,
        "curve": "linear",
    }
    events = riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=0))
    pbs = [e for e in events if isinstance(e, PitchBend)]
    assert pbs, "expected pitch-bend events when pitch_rise_cents > 0"
    # Bend should ramp from 0 toward ±8191.
    sorted_pbs = sorted(pbs, key=lambda p: p.tick)
    assert sorted_pbs[0].value < sorted_pbs[-1].value


def test_noise_riser_unknown_curve_raises() -> None:
    riser = NoiseRiser(midi_channel=7)
    with pytest.raises(ValueError, match="unknown curve"):
        riser.generate_bar(
            _ctx(pattern_knobs={"trigger": "once", "duration_bars": 4, "curve": "bogus"})
        )


def test_noise_riser_unknown_trigger_raises() -> None:
    riser = NoiseRiser(midi_channel=7)
    with pytest.raises(ValueError, match="unknown trigger"):
        riser.generate_bar(_ctx(pattern_knobs={"trigger": "bogus"}))


def test_noise_riser_base_note_parsing() -> None:
    riser = NoiseRiser(midi_channel=7)
    events = riser.generate_bar(
        _ctx(pattern_knobs={"trigger": "once", "duration_bars": 1, "base_note": "C3"})
    )
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # C3 = MIDI 48.
    assert note_ons[0].note == 48
