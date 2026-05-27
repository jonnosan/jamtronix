"""Tests for cc_lfo + cc_envelope (modulator-voice algorithms)."""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import CCLFO, CCEnvelope
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange
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


# ----------------------------------------------------------- cc_lfo


def test_cc_lfo_default_emits_sine_at_cc74() -> None:
    lfo = CCLFO(midi_channel=2)
    events = lfo.generate_bar(_ctx())
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert len(ccs) == 16  # default samples_per_bar
    assert all(c.cc == 74 for c in ccs)
    assert all(0 <= c.value <= 127 for c in ccs)


def test_cc_lfo_samples_per_bar_knob() -> None:
    lfo = CCLFO(midi_channel=2)
    events = lfo.generate_bar(_ctx(pattern_knobs={"samples_per_bar": 4}))
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert len(ccs) == 4


def test_cc_lfo_square_alternates_extremes() -> None:
    lfo = CCLFO(midi_channel=2)
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
    ccs = sorted((e for e in events if isinstance(e, ControlChange)), key=lambda e: e.tick)
    # First half = 127 (high), second half = 0 (low) given square wave
    # and depth/offset configured for full swing.
    assert ccs[0].value == 127
    assert ccs[-1].value == 0


def test_cc_lfo_saw_ramps_up() -> None:
    lfo = CCLFO(midi_channel=2)
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
    ccs = sorted((e for e in events if isinstance(e, ControlChange)), key=lambda e: e.tick)
    values = [c.value for c in ccs]
    # Saw ramps roughly monotonically (allowing for rounding noise).
    diffs = [b - a for a, b in zip(values, values[1:], strict=False)]
    assert sum(1 for d in diffs if d > 0) >= len(diffs) - 2


def test_cc_lfo_continuous_phase_across_bars() -> None:
    """End of bar N's LFO ≈ start of bar N+1's LFO."""
    lfo = CCLFO(midi_channel=2)
    bar0 = lfo.generate_bar(
        _ctx(pattern_knobs={"shape": "sine", "period_bars": 4.0, "samples_per_bar": 8}, bar_index=0)
    )
    bar1 = lfo.generate_bar(
        _ctx(pattern_knobs={"shape": "sine", "period_bars": 4.0, "samples_per_bar": 8}, bar_index=1)
    )
    ccs0 = sorted((e for e in bar0 if isinstance(e, ControlChange)), key=lambda e: e.tick)
    ccs1 = sorted((e for e in bar1 if isinstance(e, ControlChange)), key=lambda e: e.tick)
    # Sine over 4 bars at 8 samples/bar = 32 samples per cycle — successive
    # samples are smooth, so end of bar 0 ≈ start of bar 1.
    assert abs(ccs0[-1].value - ccs1[0].value) <= 15


def test_cc_lfo_cc_knob_changes_controller() -> None:
    lfo = CCLFO(midi_channel=2)
    events = lfo.generate_bar(_ctx(pattern_knobs={"cc": 71}))
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert all(c.cc == 71 for c in ccs)


def test_cc_lfo_period_zero_raises() -> None:
    lfo = CCLFO(midi_channel=2)
    with pytest.raises(ValueError, match="period_bars must be > 0"):
        lfo.generate_bar(_ctx(pattern_knobs={"period_bars": 0}))


def test_cc_lfo_unknown_shape_raises() -> None:
    lfo = CCLFO(midi_channel=2)
    with pytest.raises(ValueError, match="unknown shape"):
        lfo.generate_bar(_ctx(pattern_knobs={"shape": "bogus"}))


# ---------------------------------------------------- cc_envelope


def test_cc_envelope_default_emits_four_envelopes() -> None:
    env = CCEnvelope(midi_channel=2)
    events = env.generate_bar(_ctx())
    ccs = [e for e in events if isinstance(e, ControlChange)]
    # 4 triggers × 3 segments × 8 samples = 96 CC events.
    assert len(ccs) == 4 * 3 * 8


def test_cc_envelope_starts_from_rest_peaks_returns_to_rest() -> None:
    env = CCEnvelope(midi_channel=2)
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
    ccs = sorted((e for e in events if isinstance(e, ControlChange)), key=lambda e: e.tick)
    # Attack starts at rest (30), reaches peak (120). Release ends at rest (30).
    assert ccs[0].value == 30
    assert max(c.value for c in ccs) == 120
    assert ccs[-1].value == 30


def test_cc_envelope_pulses_drive_trigger_count() -> None:
    env = CCEnvelope(midi_channel=2)
    events = env.generate_bar(_ctx(pattern_knobs={"pulses": 2, "offset": 0, "samples": 4}))
    ccs = [e for e in events if isinstance(e, ControlChange)]
    # 2 triggers × 3 segments × 4 samples = 24.
    assert len(ccs) == 24


def test_cc_envelope_zero_pulses_emits_nothing() -> None:
    env = CCEnvelope(midi_channel=2)
    events = env.generate_bar(_ctx(pattern_knobs={"pulses": 0, "samples": 2}))
    assert [e for e in events if isinstance(e, ControlChange)] == []


def test_cc_envelope_cc_knob_changes_controller() -> None:
    env = CCEnvelope(midi_channel=2)
    events = env.generate_bar(_ctx(pattern_knobs={"cc": 11, "samples": 2}))
    assert all(isinstance(e, ControlChange) and e.cc == 11 for e in events)
