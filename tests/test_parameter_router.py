"""Tests for the sink-side :class:`ParameterRouter`."""

from __future__ import annotations

import pytest

from jtx.engine.events import (
    ControlChange,
    Event,
    PitchBend,
)
from jtx.engine.osc_client import MemoryOscClient
from jtx.engine.parameter_router import ParameterRouter
from jtx.model.parameter_target import (
    CCTarget,
    OscTarget,
    ParameterTarget,
)
from jtx.model.setup import VoiceSlot


def _mono_voice(
    *,
    channel: int = 1,
    parameter_map: dict[str, ParameterTarget] | None = None,
) -> VoiceSlot:
    return VoiceSlot(
        name="acid",
        type="mono",
        default_role="bass",
        midi_channel=channel,
        parameter_map=parameter_map or {},
    )


# -------------------------------------------------- passthrough + CC routing


def test_router_passthrough_untagged_events() -> None:
    """An untagged CC (function=None) is passed through unchanged."""
    slot = _mono_voice(channel=3)
    router = ParameterRouter(slot)
    events: list[Event] = [
        ControlChange(tick=0, channel=3, cc=11, value=64),
    ]
    out = router.route(events)
    assert out == events


def test_router_rewrites_cc_number_via_cctarget() -> None:
    """A tagged CC with a CCTarget override gets its CC number rewritten."""
    slot = _mono_voice(channel=3, parameter_map={"cutoff": CCTarget(80)})
    router = ParameterRouter(slot, {"cutoff": CCTarget(74)})
    events: list[Event] = [
        ControlChange(tick=0, channel=3, cc=74, value=30, function="cutoff"),
    ]
    out = router.route(events)
    assert isinstance(out[0], ControlChange)
    assert out[0].cc == 80
    assert out[0].value == 30
    assert out[0].channel == 3


def test_router_falls_back_to_default_param_map() -> None:
    """Without a per-voice entry, the algorithm DEFAULT_PARAM_MAP is used."""
    slot = _mono_voice(channel=2)
    router = ParameterRouter(slot, {"cutoff": CCTarget(74)})
    events: list[Event] = [
        ControlChange(tick=0, channel=2, cc=74, value=50, function="cutoff"),
    ]
    out = router.route(events)
    assert isinstance(out[0], ControlChange)
    assert out[0].cc == 74


def test_router_passthrough_when_no_target_anywhere() -> None:
    """Tagged event with no map entry passes through unchanged."""
    slot = _mono_voice(channel=2)
    router = ParameterRouter(slot)  # empty defaults too
    events: list[Event] = [
        ControlChange(tick=0, channel=2, cc=11, value=10, function="custom"),
    ]
    out = router.route(events)
    assert out[0] == events[0]


def test_router_passthrough_pitchbend_unchanged() -> None:
    """A tagged PitchBend with no map entry passes through on its source channel.

    ``acid_bass`` and ``noise_riser`` emit ``"bend"`` Param events that
    the voicing stage translates to PitchBend on the slot's channel;
    the router leaves them alone so per-note bend lands as articulation.
    """
    slot = _mono_voice(channel=2)
    router = ParameterRouter(slot)
    events: list[Event] = [
        PitchBend(tick=0, channel=2, value=500, function="bend"),
    ]
    out = router.route(events)
    assert isinstance(out[0], PitchBend)
    assert out[0].channel == 2
    assert out[0].value == 500


# ---------------------------------------------------------- OSC routing


def test_router_routes_osc_target_via_client() -> None:
    """A CC tagged with a function mapped to OscTarget produces no MIDI; OSC client sees it."""
    slot = _mono_voice(
        channel=3,
        parameter_map={"cutoff": OscTarget("/jtx/lead/cutoff")},
    )
    osc = MemoryOscClient()
    router = ParameterRouter(slot, osc_client=osc)
    out = router.route(
        [
            ControlChange(tick=0, channel=3, cc=74, value=127, function="cutoff"),
        ]
    )
    # No MIDI event survives the router for an OSC-routed source.
    assert out == []
    # And the OSC client got the scaled value.
    assert osc.sent == [("/jtx/lead/cutoff", 1.0)]


def test_router_osc_scales_cc_value_to_zero_to_one() -> None:
    """A CC value of 64 maps to ~0.504 (64/127) on the OSC wire."""
    slot = _mono_voice(parameter_map={"cutoff": OscTarget("/jtx/x/cutoff")})
    osc = MemoryOscClient()
    router = ParameterRouter(slot, osc_client=osc)
    router.route([ControlChange(tick=0, channel=1, cc=74, value=64, function="cutoff")])
    address, value = osc.sent[0]
    assert address == "/jtx/x/cutoff"
    assert abs(value - 64 / 127) < 1e-6


def test_router_osc_scales_pitchbend_to_minus_one_to_one() -> None:
    """PitchBend (e.g. ``"bend"``) routed to OSC lands in [-1, 1]."""
    slot = _mono_voice(parameter_map={"bend": OscTarget("/jtx/x/bend")})
    osc = MemoryOscClient()
    router = ParameterRouter(slot, osc_client=osc)
    router.route(
        [
            PitchBend(tick=0, channel=1, value=-8192, function="bend"),
            PitchBend(tick=10, channel=1, value=0, function="bend"),
            PitchBend(tick=20, channel=1, value=8191, function="bend"),
        ]
    )
    values = [v for _addr, v in osc.sent]
    assert values[0] == pytest.approx(-1.0)
    assert values[1] == pytest.approx(0.0)
    assert values[2] == pytest.approx(8191 / 8192)


def test_router_osc_without_client_raises_with_helpful_message() -> None:
    """An OscTarget with no configured OSC client raises a clear runtime error."""
    slot = _mono_voice(parameter_map={"cutoff": OscTarget("/jtx/x/cutoff")})
    router = ParameterRouter(slot)  # no osc_client
    with pytest.raises(RuntimeError, match="OscTarget.*no OSC client"):
        router.route([ControlChange(tick=0, channel=1, cc=74, value=64, function="cutoff")])
