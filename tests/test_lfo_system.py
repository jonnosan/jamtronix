"""Tests for the engine-side LFO sampler + target parser + applier."""

from __future__ import annotations

import random

import pytest

from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange
from jtx.engine.lfo import (
    apply_lfos_to_bar,
    parse_target,
    sample_lfo,
)
from jtx.model.lfo import LFO, LFOApplication
from jtx.model.song import Key


def _bar_ctx() -> BarContext:
    return BarContext(
        bar_index=0,
        tick_offset=0,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs={},
        mix_knobs={},
        song_feel={},
        rng=random.Random(0),
    )


# ---------------------------------------------------------- parser


def test_parse_target_pattern() -> None:
    p = parse_target("pattern:acid:slide_prob")
    assert p.kind == "pattern" and p.voice == "acid" and p.knob == "slide_prob"


def test_parse_target_mix() -> None:
    p = parse_target("mix:kick:sidechain_floor")
    assert p.kind == "mix" and p.voice == "kick" and p.knob == "sidechain_floor"


def test_parse_target_global_feel() -> None:
    p = parse_target("global_feel:pump")
    assert p.kind == "global_feel" and p.voice is None and p.knob == "pump"


def test_parse_target_legacy_feel_rejected() -> None:
    """``feel:`` targets are gone in schema v3."""
    with pytest.raises(ValueError, match="global_feel"):
        parse_target("feel:kick:swing")


def test_parse_target_midi() -> None:
    p = parse_target("midi:ch2:cc74")
    assert p.kind == "midi" and p.midi_channel == 2 and p.midi_cc == 74


def test_parse_target_root() -> None:
    p = parse_target("root:acid")
    assert p.kind == "root" and p.voice == "acid"


def test_parse_target_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="expected"):
        parse_target("bogus:thing")
    with pytest.raises(ValueError, match="midi:"):
        parse_target("midi:notavalidform")


# ---------------------------------------------------------- sampler


def test_sample_lfo_sine_centred_around_half() -> None:
    lfo = LFO(name="x", shape="sine", period_bars=4.0, depth=1.0)
    # At phase 0 sine = 0.5, at phase 0.25 sine peaks at 1.0.
    assert abs(sample_lfo(lfo, 0, 0, 1920) - 0.5) < 1e-6
    assert abs(sample_lfo(lfo, 1, 0, 1920) - 1.0) < 1e-6


def test_sample_lfo_depth_scales_swing() -> None:
    lfo = LFO(name="x", shape="sine", period_bars=4.0, depth=0.5)
    # depth=0.5 → swing in [0.25, 0.75] around centre 0.5.
    samples = [sample_lfo(lfo, b, 0, 1920) for b in range(8)]
    assert min(samples) >= 0.25 - 1e-6
    assert max(samples) <= 0.75 + 1e-6


def test_sample_lfo_saw_ramps_across_period() -> None:
    lfo = LFO(name="x", shape="saw", period_bars=4.0, depth=1.0)
    # Bars 0..3 should produce monotonically increasing values.
    vals = [sample_lfo(lfo, b, 0, 1920) for b in range(4)]
    assert vals == sorted(vals)


def test_sample_lfo_square_alternates() -> None:
    lfo = LFO(name="x", shape="square", period_bars=2.0, depth=1.0)
    assert sample_lfo(lfo, 0, 0, 1920) == 1.0  # first half = high
    assert sample_lfo(lfo, 1, 0, 1920) == 0.0  # second half = low


def test_sample_lfo_random_uses_rng() -> None:
    lfo = LFO(name="x", shape="random", period_bars=1.0, depth=1.0)
    rng1 = random.Random(0)
    rng2 = random.Random(0)
    assert sample_lfo(lfo, 0, 0, 1920, rng1) == sample_lfo(lfo, 0, 0, 1920, rng2)


def test_sample_lfo_unknown_shape_raises() -> None:
    lfo = LFO(name="x", shape="bogus", period_bars=4.0, depth=1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="LFO shape"):
        sample_lfo(lfo, 0, 0, 1920)


# ---------------------------------------------------------- apply


def test_apply_lfos_pattern_target_writes_knob() -> None:
    lfos = [
        LFO(
            name="sweep",
            shape="sine",
            period_bars=4.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="pattern:acid:slide_prob")],
        )
    ]
    ctx = _bar_ctx()
    voice_contexts = {"acid": ctx}
    events = apply_lfos_to_bar(lfos, "drop", voice_contexts, 1, 1920, random.Random(0))
    assert events == []
    # At bar 1 with period_bars=4, phase=0.25, sine peak → 1.0.
    assert ctx.pattern_knobs.get("slide_prob") == pytest.approx(1.0, abs=1e-6)


def test_apply_lfos_mix_target_writes_mix_knob() -> None:
    lfos = [
        LFO(
            name="x",
            shape="square",
            period_bars=1.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="mix:kick:sidechain_floor")],
        )
    ]
    ctx = _bar_ctx()
    voice_contexts = {"kick": ctx}
    apply_lfos_to_bar(lfos, "drop", voice_contexts, 0, 1920, random.Random(0))
    assert ctx.mix_knobs.get("sidechain_floor") == 1.0


def test_apply_lfos_global_feel_target_writes_song_feel() -> None:
    """``global_feel:`` LFO target broadcasts to every voice's song_feel."""
    lfos = [
        LFO(
            name="x",
            shape="square",
            period_bars=1.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="global_feel:pump")],
        )
    ]
    # Two voices share the same song_feel dict (as SongPlayer arranges).
    shared = {"pump": 0.0}
    ctx_a = _bar_ctx()
    ctx_a.song_feel = shared
    ctx_b = _bar_ctx()
    ctx_b.song_feel = shared
    apply_lfos_to_bar(
        lfos, "drop", {"a": ctx_a, "b": ctx_b}, 0, 1920, random.Random(0)
    )
    assert ctx_a.song_feel["pump"] == 1.0
    assert ctx_b.song_feel["pump"] == 1.0  # broadcast through shared dict


def test_apply_lfos_midi_target_emits_control_change() -> None:
    lfos = [
        LFO(
            name="x",
            shape="sine",
            period_bars=4.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="midi:ch2:cc74")],
        )
    ]
    events = apply_lfos_to_bar(lfos, "drop", {}, 1, 1920, random.Random(0))
    assert len(events) == 1
    cc = events[0]
    assert isinstance(cc, ControlChange)
    assert cc.channel == 2 and cc.cc == 74
    # Sine peak at bar 1 (phase 0.25) → 1.0 → 127.
    assert cc.value == 127


def test_apply_lfos_root_target_writes_chord_root_semitones() -> None:
    lfos = [
        LFO(
            name="x",
            shape="sine",
            period_bars=4.0,
            depth=2.0,  # depth=2 → ±2 semitone swing
            applications=[LFOApplication(part="drop", target="root:acid")],
        )
    ]
    ctx = _bar_ctx()
    voice_contexts = {"acid": ctx}
    apply_lfos_to_bar(lfos, "drop", voice_contexts, 1, 1920, random.Random(0))
    # Bar 1 → sine peak → 1.0 (raw, after depth=2 mapping clamps to 1.0).
    # apply_lfos passes the clamped value into (value-0.5)*2*depth = 0.5*2*2 = 2.
    assert ctx.chord_root_semitones == 2


def test_apply_lfos_ignores_applications_in_other_parts() -> None:
    lfos = [
        LFO(
            name="x",
            shape="sine",
            period_bars=4.0,
            depth=1.0,
            applications=[LFOApplication(part="build", target="pattern:acid:slide_prob")],
        )
    ]
    ctx = _bar_ctx()
    voice_contexts = {"acid": ctx}
    events = apply_lfos_to_bar(lfos, "drop", voice_contexts, 1, 1920, random.Random(0))
    assert events == []
    assert "slide_prob" not in ctx.pattern_knobs


def test_apply_lfos_skips_unknown_voice() -> None:
    lfos = [
        LFO(
            name="x",
            shape="sine",
            period_bars=4.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="pattern:ghost:slide_prob")],
        )
    ]
    # No "ghost" voice in contexts → graceful skip.
    apply_lfos_to_bar(lfos, "drop", {}, 0, 1920, random.Random(0))


def test_apply_lfos_multiple_lfos_same_part() -> None:
    """Two LFOs on different targets in the same part both fire."""
    lfos = [
        LFO(
            name="a",
            shape="square",
            period_bars=1.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="pattern:acid:slide_prob")],
        ),
        LFO(
            name="b",
            shape="square",
            period_bars=1.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="midi:ch2:cc74")],
        ),
    ]
    ctx = _bar_ctx()
    events = apply_lfos_to_bar(lfos, "drop", {"acid": ctx}, 0, 1920, random.Random(0))
    assert ctx.pattern_knobs.get("slide_prob") == 1.0
    assert len(events) == 1
    assert isinstance(events[0], ControlChange)
