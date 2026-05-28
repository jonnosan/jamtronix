"""Tests for the noise_riser algorithm.

Schema v3: MIDI-naive. Emits :class:`Note` for the held tone and
:class:`Param` for the cutoff ramp and (when configured) the bend rise.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import NoiseRiser
from jtx.engine.context import BarContext
from jtx.model.events import Note, Param
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


def _notes(events) -> list[Note]:
    return [e for e in events if isinstance(e, Note)]


def _params(events, name: str) -> list[Param]:
    return [e for e in events if isinstance(e, Param) and e.name == name]


def test_noise_riser_once_inside_window_emits_note_and_cutoff() -> None:
    riser = NoiseRiser()
    events = riser.generate_bar(
        _ctx(pattern_knobs={"trigger": "once", "duration_bars": 4}, bar_index=0)
    )
    assert _notes(events)
    assert _params(events, "cutoff")


def test_noise_riser_once_outside_window_silent() -> None:
    riser = NoiseRiser()
    events = riser.generate_bar(
        _ctx(pattern_knobs={"trigger": "once", "duration_bars": 4}, bar_index=4)
    )
    assert events == []


def test_noise_riser_every_fires_last_n_bars_of_cycle() -> None:
    riser = NoiseRiser()
    knobs = {"trigger": "every", "duration_bars": 4, "cycle_bars": 16}
    for b in [0, 3, 11]:
        assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b)) == []
    for b in [12, 13, 14, 15]:
        assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b))


def test_noise_riser_last_bar_of_8_only_on_bar7() -> None:
    riser = NoiseRiser()
    knobs = {"trigger": "last_bar_of_8"}
    assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=0)) == []
    assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=6)) == []
    assert riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=7))


def test_noise_riser_velocity_ramps_up_across_window() -> None:
    riser = NoiseRiser()
    knobs = {
        "trigger": "once",
        "duration_bars": 4,
        "vel_start": 40,
        "vel_end": 120,
        "curve": "linear",
    }
    vels = [
        _notes(riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b)))[0].velocity
        for b in range(4)
    ]
    for prev, curr in zip(vels, vels[1:], strict=False):
        assert curr >= prev


def test_noise_riser_cutoff_ramps_up() -> None:
    riser = NoiseRiser()
    knobs = {
        "trigger": "once",
        "duration_bars": 1,
        "cutoff_start": 20,
        "cutoff_end": 110,
        "curve": "linear",
        "samples_per_bar": 8,
    }
    events = riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=0))
    cutoffs = sorted(_params(events, "cutoff"), key=lambda p: p.tick)
    assert cutoffs[0].value <= 40 / 127.0
    assert cutoffs[-1].value >= 90 / 127.0


def test_noise_riser_bend_when_pitch_rise_nonzero() -> None:
    riser = NoiseRiser()
    knobs = {
        "trigger": "once",
        "duration_bars": 1,
        "pitch_rise_cents": 200,
        "curve": "linear",
    }
    events = riser.generate_bar(_ctx(pattern_knobs=knobs, bar_index=0))
    bends = sorted(_params(events, "bend"), key=lambda p: p.tick)
    assert bends
    assert bends[0].value < bends[-1].value


def test_noise_riser_unknown_curve_raises() -> None:
    riser = NoiseRiser()
    with pytest.raises(ValueError, match="unknown curve"):
        riser.generate_bar(
            _ctx(pattern_knobs={"trigger": "once", "duration_bars": 4, "curve": "bogus"})
        )


def test_noise_riser_unknown_trigger_raises() -> None:
    riser = NoiseRiser()
    with pytest.raises(ValueError, match="unknown trigger"):
        riser.generate_bar(_ctx(pattern_knobs={"trigger": "bogus"}))


def test_noise_riser_base_note_parsing() -> None:
    riser = NoiseRiser()
    events = riser.generate_bar(
        _ctx(pattern_knobs={"trigger": "once", "duration_bars": 1, "base_note": "C3"})
    )
    assert _notes(events)[0].pitch == 48
