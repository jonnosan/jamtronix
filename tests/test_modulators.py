"""Tests for cc_envelope — modulator-voice algorithm with envelope shape.

Schema v3: MIDI-naive. Emits ``Param`` events tagged with a semantic
``function`` name; the voicing stage + parameter_router resolve
routing via the voice slot's ``parameter_map`` (or the algorithm's
``DEFAULT_PARAM_MAP``).

``cc_lfo`` was retired in this round — smooth-shape LFO usage moved
to the song-level LFO system. See tests/test_lfo_system.py for the
sub-bar sampling + ``voice:<v>:<fn>`` target tests that replaced it.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import CCEnvelope
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


def test_cc_envelope_default_emits_four_envelopes() -> None:
    env = CCEnvelope()
    events = env.generate_bar(_ctx())
    # 4 triggers × 3 segments × 8 samples = 96 events.
    assert len(_params(events)) == 4 * 3 * 8


def test_cc_envelope_default_function_is_cutoff() -> None:
    env = CCEnvelope()
    events = env.generate_bar(_ctx(pattern_knobs={"pulses": 1, "samples": 2}))
    assert all(p.name == "cutoff" for p in _params(events))


def test_cc_envelope_function_knob_overrides_default() -> None:
    env = CCEnvelope()
    events = env.generate_bar(
        _ctx(pattern_knobs={"function": "resonance", "pulses": 1, "samples": 2})
    )
    assert all(p.name == "resonance" for p in _params(events))


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
