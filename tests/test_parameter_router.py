"""Tests for the sink-side :class:`ParameterRouter`."""

from __future__ import annotations

from jtx.engine.events import (
    ChannelPressure,
    ControlChange,
    Event,
    NoteOff,
    NoteOn,
    PitchBend,
)
from jtx.engine.parameter_router import ParameterRouter
from jtx.model.parameter_target import (
    CCTarget,
    MPEPitchBendTarget,
    MPEPressureTarget,
    MPETimbreTarget,
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


def _mpe_voice(
    *,
    channel: int = 2,
    count: int = 8,
    parameter_map: dict[str, ParameterTarget] | None = None,
) -> VoiceSlot:
    return VoiceSlot(
        name="lead",
        type="mono",
        default_role="lead",
        midi_channel=channel,
        mpe_mode=True,
        mpe_channel_count=count,
        parameter_map=parameter_map or {},
    )


# -------------------------------------------------- non-MPE behaviours


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


# -------------------------------------------------------- MPE allocation


def test_router_allocates_mpe_channels_round_robin() -> None:
    """4 simultaneous NoteOns claim channels 2, 3, 4, 5 in order."""
    slot = _mpe_voice(channel=2, count=8)
    router = ParameterRouter(slot)
    events: list[Event] = [
        NoteOn(tick=0, channel=2, note=60, velocity=100),
        NoteOn(tick=10, channel=2, note=64, velocity=100),
        NoteOn(tick=20, channel=2, note=67, velocity=100),
        NoteOn(tick=30, channel=2, note=72, velocity=100),
    ]
    out = router.route(events)
    on_channels = [e.channel for e in out if isinstance(e, NoteOn)]
    assert on_channels == [2, 3, 4, 5]


def test_router_reuses_freed_channels_after_note_off() -> None:
    """Sequential notes (each released before the next) reuse channels."""
    slot = _mpe_voice(channel=2, count=8)
    router = ParameterRouter(slot)
    out_bar1 = router.route(
        [
            NoteOn(tick=0, channel=2, note=60, velocity=100),
            NoteOff(tick=100, channel=2, note=60),
        ]
    )
    assert any(isinstance(e, NoteOn) and e.channel == 2 for e in out_bar1)
    # New bar — first note should claim the next channel in round-robin
    # order (channel 3), demonstrating allocation state persists across
    # bars rather than always restarting at the block's first channel.
    out_bar2 = router.route(
        [
            NoteOn(tick=0, channel=2, note=64, velocity=100),
            NoteOff(tick=100, channel=2, note=64),
        ]
    )
    second_on = next(e for e in out_bar2 if isinstance(e, NoteOn))
    assert second_on.channel == 3


def test_router_steal_oldest_at_block_full() -> None:
    """9th simultaneous note steals the oldest channel + emits NoteOff."""
    slot = _mpe_voice(channel=2, count=8)
    router = ParameterRouter(slot)
    events: list[Event] = [
        NoteOn(tick=i * 10, channel=2, note=60 + i, velocity=100) for i in range(8)
    ]
    events.append(NoteOn(tick=100, channel=2, note=80, velocity=100))
    out = router.route(events)
    note_ons = [e for e in out if isinstance(e, NoteOn)]
    note_offs = [e for e in out if isinstance(e, NoteOff)]
    # Synthetic NoteOff for the displaced (oldest = pitch 60) note.
    assert any(off.note == 60 and off.channel == 2 for off in note_offs)
    # The 9th NoteOn re-uses channel 2.
    assert note_ons[-1].channel == 2
    assert note_ons[-1].note == 80


# ----------------------------------------------- leading + trailing bend


def test_router_pairs_leading_and_trailing_bend_with_note() -> None:
    """acid_bass-style wrap: leading + trailing bend ride the NoteOn channel."""
    slot = _mpe_voice(channel=2, count=8)
    router = ParameterRouter(slot)
    events: list[Event] = [
        PitchBend(tick=119, channel=2, value=50, function="bend"),
        NoteOn(tick=120, channel=2, note=60, velocity=100),
        NoteOff(tick=240, channel=2, note=60),
        PitchBend(tick=240, channel=2, value=0, function="bend"),
    ]
    out = router.route(events)
    pb_channels = [e.channel for e in out if isinstance(e, PitchBend)]
    # NoteOn allocates channel 2 (first round-robin step from idx -1).
    note_on = next(e for e in out if isinstance(e, NoteOn))
    assert note_on.channel == 2
    # Both bends ride the same channel as the NoteOn.
    assert pb_channels == [2, 2]


def test_router_trailing_bend_does_not_leak_onto_next_note() -> None:
    """Trailing zero-bend at NoteOff.tick rides the *just-ended* note, not the next one."""
    slot = _mpe_voice(channel=2, count=8)
    router = ParameterRouter(slot)
    # Two acid-bass-shaped notes back-to-back. Second NoteOn lands at
    # the same tick as the first NoteOff + trailing bend, with its own
    # leading bend at tick - 1.
    events: list[Event] = [
        # Note 1: pre-bend, on, off + trailing zero-bend.
        PitchBend(tick=-1, channel=2, value=70, function="bend"),
        NoteOn(tick=0, channel=2, note=60, velocity=100),
        NoteOff(tick=120, channel=2, note=60),
        PitchBend(tick=120, channel=2, value=0, function="bend"),
        # Note 2: leading bend at tick=119 (before second NoteOn), on at 120.
        PitchBend(tick=119, channel=2, value=40, function="bend"),
        NoteOn(tick=120, channel=2, note=64, velocity=100),
        NoteOff(tick=240, channel=2, note=64),
        PitchBend(tick=240, channel=2, value=0, function="bend"),
    ]
    # ``apply_feel``'s tick clamping would push the -1 to 0, but the
    # router's defensive sort doesn't clamp — feed as-is.
    out = router.route(events)
    note_ons = [e for e in out if isinstance(e, NoteOn)]
    assert note_ons[0].channel == 2  # first note channel
    assert note_ons[1].channel == 3  # second note channel (next round-robin slot)

    # Find each PB by value to identify them.
    bends = [e for e in out if isinstance(e, PitchBend)]
    bend_by_value: dict[int, PitchBend] = {pb.value: pb for pb in bends}
    # Note 1's bends (values 70 and 0 just from note 1) ride channel 2.
    # Note 2's leading bend (value 40) rides channel 3.
    assert bend_by_value[70].channel == 2
    assert bend_by_value[40].channel == 3
    # The trailing zero-bend at tick=120 paired with Note 1's NoteOff
    # at tick=120 rides channel 2 — and the trailing zero-bend at
    # tick=240 paired with Note 2's NoteOff rides channel 3. We have
    # two zero-bends; check both channels are present.
    zero_channels = sorted(pb.channel for pb in bends if pb.value == 0)
    assert zero_channels == [2, 3]


# ------------------------------------------------------- MPE targets


def test_router_mpe_pitch_bend_target_rewrites_channel() -> None:
    """An MPEPitchBendTarget routes the tagged PitchBend to the per-note channel."""
    slot = _mpe_voice(
        channel=2,
        count=8,
        parameter_map={"bend": MPEPitchBendTarget()},
    )
    router = ParameterRouter(slot)
    out = router.route(
        [
            NoteOn(tick=0, channel=2, note=60, velocity=100),
            PitchBend(tick=10, channel=2, value=1000, function="bend"),
            NoteOff(tick=100, channel=2, note=60),
        ]
    )
    pb = next(e for e in out if isinstance(e, PitchBend))
    assert pb.channel == 2
    assert pb.value == 1000


def test_router_mpe_pressure_target_emits_channel_pressure() -> None:
    """A CC tagged with a function mapped to MPEPressureTarget → ChannelPressure."""
    slot = _mpe_voice(
        channel=2,
        count=8,
        parameter_map={"cutoff": MPEPressureTarget()},
    )
    router = ParameterRouter(slot)
    out = router.route(
        [
            NoteOn(tick=0, channel=2, note=60, velocity=100),
            ControlChange(tick=10, channel=2, cc=74, value=90, function="cutoff"),
            NoteOff(tick=100, channel=2, note=60),
        ]
    )
    pressures = [e for e in out if isinstance(e, ChannelPressure)]
    assert len(pressures) == 1
    assert pressures[0].channel == 2
    assert pressures[0].value == 90


def test_router_mpe_timbre_target_emits_cc74_on_mpe_channel() -> None:
    """An MPETimbreTarget rewrites the CC number to 74 on the per-note channel."""
    slot = _mpe_voice(
        channel=2,
        count=8,
        parameter_map={"cutoff": MPETimbreTarget()},
    )
    router = ParameterRouter(slot)
    out = router.route(
        [
            NoteOn(tick=0, channel=2, note=60, velocity=100),
            ControlChange(tick=10, channel=2, cc=11, value=55, function="cutoff"),
            NoteOff(tick=100, channel=2, note=60),
        ]
    )
    timbres = [e for e in out if isinstance(e, ControlChange) and e.cc == 74]
    assert len(timbres) == 1
    assert timbres[0].channel == 2
    assert timbres[0].value == 55


def test_router_non_mpe_voice_keeps_main_channel_for_mpe_target() -> None:
    """Without mpe_mode, MPE targets still rewrite type but use the main channel."""
    slot = VoiceSlot(
        name="lead",
        type="mono",
        default_role="lead",
        midi_channel=3,
        parameter_map={"bend": MPEPitchBendTarget()},
    )
    router = ParameterRouter(slot)
    out = router.route(
        [
            PitchBend(tick=0, channel=3, value=500, function="bend"),
        ]
    )
    assert isinstance(out[0], PitchBend)
    assert out[0].channel == 3
    assert out[0].value == 500
