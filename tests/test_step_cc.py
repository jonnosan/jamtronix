"""Tests for the step_cc modulator algorithm.

Schema v3: MIDI-naive. Emits ``Param(name="cc<N>")`` events with
normalised [0,1] values.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import StepCC
from jtx.engine.context import BarContext
from jtx.model.events import Param
from jtx.model.song import Key


def _ctx(*, pattern_knobs: dict[str, object] | None = None, seed: int = 0) -> BarContext:
    return BarContext(
        bar_index=0,
        tick_offset=0,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(seed),
    )


def _params(events) -> list[Param]:
    return [e for e in events if isinstance(e, Param)]


def test_step_cc_emits_one_value_per_step_at_default_subdivision() -> None:
    mod = StepCC()
    events = mod.generate_bar(_ctx(pattern_knobs={"value_curve": "ramp_up"}))
    assert len(_params(events)) == 16


def test_step_cc_triplet_subdivision() -> None:
    mod = StepCC()
    events = mod.generate_bar(_ctx(pattern_knobs={"subdivision": "16t", "value_curve": "ramp_up"}))
    assert len(_params(events)) == 24


def test_step_cc_ramp_up_ascends() -> None:
    mod = StepCC()
    events = mod.generate_bar(
        _ctx(
            pattern_knobs={
                "subdivision": "16",
                "value_curve": "ramp_up",
                "cc_min": 0,
                "cc_max": 120,
                "depth": 1.0,
            }
        )
    )
    params = sorted(_params(events), key=lambda p: p.tick)
    assert params[0].value < params[-1].value


def test_step_cc_flat_curve_at_centre() -> None:
    mod = StepCC()
    events = mod.generate_bar(
        _ctx(
            pattern_knobs={
                "value_curve": "flat",
                "cc_min": 30,
                "cc_max": 110,
                "depth": 1.0,
            }
        )
    )
    # Centre of [30,110] = 70 → normalised 70/127.
    assert all(p.value == pytest.approx(70 / 127.0) for p in _params(events))


def test_step_cc_depth_zero_collapses_to_centre() -> None:
    mod = StepCC()
    events = mod.generate_bar(
        _ctx(
            pattern_knobs={
                "value_curve": "ramp_up",
                "cc_min": 30,
                "cc_max": 110,
                "depth": 0.0,
            }
        )
    )
    assert all(p.value == pytest.approx(70 / 127.0) for p in _params(events))


def test_step_cc_uses_configured_cc_number_as_function_name() -> None:
    mod = StepCC()
    events = mod.generate_bar(_ctx(pattern_knobs={"cc": 71}))
    assert all(p.name == "cc71" for p in _params(events))


def test_step_cc_samples_per_step_smooths() -> None:
    mod = StepCC()
    events = mod.generate_bar(
        _ctx(
            pattern_knobs={
                "subdivision": "16",
                "value_curve": "ramp_up",
                "samples_per_step": 4,
            }
        )
    )
    assert len(_params(events)) == 64


def test_step_cc_unknown_curve_raises() -> None:
    mod = StepCC()
    with pytest.raises(ValueError, match="unknown value_curve"):
        mod.generate_bar(_ctx(pattern_knobs={"value_curve": "bogus"}))


def test_step_cc_pulse_curve_emphasises_downbeats() -> None:
    mod = StepCC()
    events = mod.generate_bar(
        _ctx(
            pattern_knobs={
                "subdivision": "16",
                "value_curve": "pulse",
                "cc_min": 0,
                "cc_max": 120,
                "depth": 1.0,
            }
        )
    )
    params = sorted(_params(events), key=lambda p: p.tick)
    high_steps = {0, 4, 8, 12}
    for i, p in enumerate(params):
        if i in high_steps:
            assert p.value >= 100 / 127.0
        else:
            assert p.value <= 20 / 127.0
