"""Tests for the step_cc modulator algorithm."""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import StepCC
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange
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


def test_step_cc_emits_one_value_per_step_at_default_subdivision() -> None:
    mod = StepCC(midi_channel=1)
    events = mod.generate_bar(_ctx(pattern_knobs={"value_curve": "ramp_up"}))
    ccs = [e for e in events if isinstance(e, ControlChange)]
    # Default subdivision "16" → 16 steps per bar.
    assert len(ccs) == 16


def test_step_cc_triplet_subdivision() -> None:
    mod = StepCC(midi_channel=1)
    events = mod.generate_bar(_ctx(pattern_knobs={"subdivision": "16t", "value_curve": "ramp_up"}))
    ccs = [e for e in events if isinstance(e, ControlChange)]
    # 16t = 24 per bar.
    assert len(ccs) == 24


def test_step_cc_ramp_up_ascends() -> None:
    mod = StepCC(midi_channel=1)
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
    ccs = sorted((e for e in events if isinstance(e, ControlChange)), key=lambda c: c.tick)
    assert ccs[0].value < ccs[-1].value


def test_step_cc_flat_curve_at_centre() -> None:
    mod = StepCC(midi_channel=1)
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
    ccs = [e for e in events if isinstance(e, ControlChange)]
    # Flat curve = centre of [30, 110] = 70.
    assert all(c.value == 70 for c in ccs)


def test_step_cc_depth_zero_collapses_to_centre() -> None:
    mod = StepCC(midi_channel=1)
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
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert all(c.value == 70 for c in ccs)


def test_step_cc_uses_configured_cc_number() -> None:
    mod = StepCC(midi_channel=1)
    events = mod.generate_bar(_ctx(pattern_knobs={"cc": 71}))
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert all(c.cc == 71 for c in ccs)


def test_step_cc_samples_per_step_smooths() -> None:
    mod = StepCC(midi_channel=1)
    events = mod.generate_bar(
        _ctx(
            pattern_knobs={
                "subdivision": "16",
                "value_curve": "ramp_up",
                "samples_per_step": 4,
            }
        )
    )
    ccs = [e for e in events if isinstance(e, ControlChange)]
    # 16 steps × 4 samples = 64 emissions.
    assert len(ccs) == 64


def test_step_cc_unknown_curve_raises() -> None:
    mod = StepCC(midi_channel=1)
    with pytest.raises(ValueError, match="unknown value_curve"):
        mod.generate_bar(_ctx(pattern_knobs={"value_curve": "bogus"}))


def test_step_cc_pulse_curve_emphasises_downbeats() -> None:
    mod = StepCC(midi_channel=1)
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
    ccs = sorted((e for e in events if isinstance(e, ControlChange)), key=lambda c: c.tick)
    # Steps 0, 4, 8, 12 should be high; others low.
    high_steps = {0, 4, 8, 12}
    for i, c in enumerate(ccs):
        if i in high_steps:
            assert c.value >= 100
        else:
            assert c.value <= 20
