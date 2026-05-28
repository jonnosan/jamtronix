"""Tests for cc_lfo + cc_envelope (modulator-voice algorithms).

Schema v3: MIDI-naive. Emit ``Param(name="cc<N>")`` events; voicing
stage parses the embedded CC# and emits a :class:`ControlChange` on
the voice slot's channel.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import CCLFO, CCEnvelope
from jtx.engine.context import BarContext
from jtx.model.events import Param
from jtx.model.song import Key


def _ctx(
    *, pattern_knobs: dict[str, object] | None = None, bar_index: int = 0, seed: int = 0
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


def _params(events) -> list[Param]:
    return [e for e in events if isinstance(e, Param)]


# ----------------------------------------------------------- cc_lfo


def test_cc_lfo_default_emits_sine_at_cc74() -> None:
    lfo = CCLFO()
    events = lfo.generate_bar(_ctx())
    params = _params(events)
    assert len(params) == 16
    assert all(p.name == "cc74" for p in params)
    assert all(0.0 <= p.value <= 1.0 for p in params)


def test_cc_lfo_samples_per_bar_knob() -> None:
    lfo = CCLFO()
    events = lfo.generate_bar(_ctx(pattern_knobs={"samples_per_bar": 4}))
    assert len(_params(events)) == 4


def test_cc_lfo_square_alternates_extremes() -> None:
    lfo = CCLFO()
    events = lfo.generate_bar(
        _ctx(
            pattern_knobs={
                "shape": "square",
                "samples_per_bar": 16,
                "period_bars": 1.0,
                "depth": 1.0,
                "offset": 0.5,
            }
        )
    )
    params = sorted(_params(events), key=lambda p: p.tick)
    assert params[0].value == pytest.approx(1.0)
    assert params[-1].value == pytest.approx(0.0)


def test_cc_lfo_saw_ramps_up() -> None:
    lfo = CCLFO()
    events = lfo.generate_bar(
        _ctx(
            pattern_knobs={
                "shape": "saw",
                "samples_per_bar": 16,
                "period_bars": 1.0,
                "depth": 1.0,
                "offset": 0.5,
            }
        )
    )
    values = [p.value for p in sorted(_params(events), key=lambda p: p.tick)]
    diffs = [b - a for a, b in zip(values, values[1:], strict=False)]
    assert sum(1 for d in diffs if d > 0) >= len(diffs) - 2


def test_cc_lfo_continuous_phase_across_bars() -> None:
    lfo = CCLFO()
    knobs = {"shape": "sine", "period_bars": 4.0, "samples_per_bar": 8}
    bar0 = sorted(_params(lfo.generate_bar(_ctx(pattern_knobs=knobs, bar_index=0))), key=lambda p: p.tick)
    bar1 = sorted(_params(lfo.generate_bar(_ctx(pattern_knobs=knobs, bar_index=1))), key=lambda p: p.tick)
    assert abs(bar0[-1].value - bar1[0].value) <= 15 / 127.0


def test_cc_lfo_cc_knob_changes_function_name() -> None:
    lfo = CCLFO()
    events = lfo.generate_bar(_ctx(pattern_knobs={"cc": 71}))
    assert all(p.name == "cc71" for p in _params(events))


def test_cc_lfo_period_zero_raises() -> None:
    lfo = CCLFO()
    with pytest.raises(ValueError, match="period_bars must be > 0"):
        lfo.generate_bar(_ctx(pattern_knobs={"period_bars": 0}))


def test_cc_lfo_unknown_shape_raises() -> None:
    lfo = CCLFO()
    with pytest.raises(ValueError, match="unknown shape"):
        lfo.generate_bar(_ctx(pattern_knobs={"shape": "bogus"}))


# ---------------------------------------------------- cc_envelope


def test_cc_envelope_default_emits_four_envelopes() -> None:
    env = CCEnvelope()
    events = env.generate_bar(_ctx())
    # 4 triggers × 3 segments × 8 samples = 96 events.
    assert len(_params(events)) == 4 * 3 * 8


def test_cc_envelope_starts_from_rest_peaks_returns_to_rest() -> None:
    env = CCEnvelope()
    events = env.generate_bar(
        _ctx(
            pattern_knobs={
                "pulses": 1,
                "offset": 0,
                "attack_ticks": 60,
                "decay_ticks": 120,
                "release_ticks": 120,
                "peak_value": 120,
                "sustain_value": 80,
                "rest_value": 30,
                "samples": 4,
            }
        )
    )
    params = sorted(_params(events), key=lambda p: p.tick)
    assert params[0].value == pytest.approx(30 / 127.0)
    assert max(p.value for p in params) == pytest.approx(120 / 127.0)
    assert params[-1].value == pytest.approx(30 / 127.0)


def test_cc_envelope_pulses_drive_trigger_count() -> None:
    env = CCEnvelope()
    events = env.generate_bar(_ctx(pattern_knobs={"pulses": 2, "offset": 0, "samples": 4}))
    # 2 triggers × 3 segments × 4 samples = 24.
    assert len(_params(events)) == 24


def test_cc_envelope_zero_pulses_emits_nothing() -> None:
    env = CCEnvelope()
    events = env.generate_bar(_ctx(pattern_knobs={"pulses": 0, "samples": 2}))
    assert _params(events) == []


def test_cc_envelope_cc_knob_changes_function_name() -> None:
    env = CCEnvelope()
    events = env.generate_bar(_ctx(pattern_knobs={"cc": 11, "samples": 2}))
    assert all(p.name == "cc11" for p in _params(events))
