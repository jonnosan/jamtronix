"""Tests for the mix pass — fade-in/out + sidechain ducking.

Schema v3: ``sidechain_from`` lists **instrument names**, not voice
names. A drum_kit voice resolves the name via ``slot.kit_map``; a
single-piece voice (drum/mono/poly) uses its own ``slot.name`` as its
implicit instrument name.
"""

from __future__ import annotations

from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn
from jtx.engine.mix import apply_mix_pass
from jtx.model.setup import KitPiece, VoiceSlot


def _notes(*specs: tuple[int, int, int, int, int]) -> list[Event]:
    out: list[Event] = []
    for tick, ch, note, vel, dur in specs:
        out.append(NoteOn(tick=tick, channel=ch, note=note, velocity=vel))
        out.append(NoteOff(tick=tick + dur, channel=ch, note=note))
    return out


def _vels(events: list[Event]) -> list[int]:
    return [e.velocity for e in events if isinstance(e, NoteOn)]


def _drum_slot(name: str, channel: int, note: int = 36) -> VoiceSlot:
    return VoiceSlot(
        name=name,
        type="drum",
        default_role="drum",
        midi_channel=channel,
        note=note,
    )


def _mono_slot(name: str, channel: int = 1) -> VoiceSlot:
    return VoiceSlot(name=name, type="mono", default_role="bass", midi_channel=channel)


def _kit_slot(name: str = "kit") -> VoiceSlot:
    return VoiceSlot(
        name=name,
        type="drum_kit",
        default_role="drum_kit",
        midi_channel=10,
        kit_map={
            "kick": KitPiece(note=36, channel=10),
            "snare": KitPiece(note=38, channel=10),
            "chh": KitPiece(note=42, channel=11),
        },
    )


def _mix(
    *,
    voice_events: dict[str, list[Event]],
    voice_slots: dict[str, VoiceSlot],
    mix_knobs: dict[str, dict[str, object]] | None = None,
    prev: dict[str, list[Event]] | None = None,
    bar_index: int = 0,
) -> dict[str, list[Event]]:
    return apply_mix_pass(
        voice_events=voice_events,
        prev_voice_events=prev or {},
        mix_knobs_by_voice=mix_knobs or {},
        voice_slots=voice_slots,
        bar_index=bar_index,
        ticks_per_bar=1920,
        ppq=480,
    )


# ---------------------------------------------------------- no-op


def test_mix_pass_empty_knobs_is_identity() -> None:
    events = _notes((0, 1, 60, 100, 120))
    slots = {"v": _mono_slot("v", channel=1)}
    out = _mix(voice_events={"v": events}, voice_slots=slots)
    assert out["v"] == events


# ---------------------------------------------------------- sidechain by instrument name


def test_sidechain_trigger_in_same_bar_ducks() -> None:
    """Note at tick T+release/2 ducks to ~halfway between base and floor."""
    out = _mix(
        voice_events={
            "kick": _notes((0, 10, 36, 110, 60)),
            "hat": _notes((120, 1, 42, 110, 60)),  # 120 ticks after kick
        },
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "hat": _mono_slot("hat", channel=1),
        },
        mix_knobs={
            "hat": {
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,  # 240 ticks
            }
        },
    )
    # distance = 120, release = 240, duck = 1 - 0.5 = 0.5.
    # vel = 110*(1-0.5) + 60*0.5 = 55 + 30 = 85.
    assert _vels(out["hat"]) == [85]


def test_sidechain_from_drum_kit_piece_matches_channel_and_note() -> None:
    """A Pump-style sidechain_from=["kick"] against a drum_kit voice
    looks up the kit_map entry's (channel, note) and matches only those
    NoteOns. Other kit pieces (e.g. snare) do NOT trigger."""
    kit_events = (
        # snare hit at tick 60 — should NOT trigger
        [NoteOn(tick=60, channel=10, note=38, velocity=100), NoteOff(tick=120, channel=10, note=38)]
        # kick hit at tick 0 — triggers
        + _notes((0, 10, 36, 110, 60))
    )
    out = _mix(
        voice_events={
            "kit": kit_events,
            "bass": _notes((120, 2, 40, 110, 60)),
        },
        voice_slots={
            "kit": _kit_slot(),
            "bass": _mono_slot("bass", channel=2),
        },
        mix_knobs={
            "bass": {
                "sidechain_from": ["kick"],
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # distance = 120 ticks from the kick at 0 → duck 0.5 → vel 85.
    # snare at 60 is closer (distance 60, duck 0.75 → vel ≈ 72) but it
    # should NOT be a trigger since we asked only for "kick".
    assert _vels(out["bass"]) == [85]


def test_sidechain_from_drum_kit_snare_matches_only_snare_hits() -> None:
    """sidechain_from=["snare"] picks up snare hits, not kicks."""
    kit_events = _notes(
        (0, 10, 36, 110, 60),  # kick — should NOT trigger
        (120, 10, 38, 100, 60),  # snare — triggers
    )
    out = _mix(
        voice_events={
            "kit": kit_events,
            "bass": _notes((180, 2, 40, 110, 60)),
        },
        voice_slots={
            "kit": _kit_slot(),
            "bass": _mono_slot("bass", channel=2),
        },
        mix_knobs={
            "bass": {
                "sidechain_from": ["snare"],
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # snare at 120, bass at 180. Distance 60, release 240. Duck 0.75.
    # vel = 110*0.25 + 60*0.75 = 27.5 + 45 = 72.5 → 72 (banker's rounding).
    assert _vels(out["bass"]) == [72]


def test_sidechain_unknown_instrument_is_no_op() -> None:
    """sidechain_from naming an instrument no voice owns is a no-op."""
    out = _mix(
        voice_events={
            "kick": _notes((0, 10, 36, 110, 60)),
            "hat": _notes((100, 1, 42, 110, 60)),
        },
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "hat": _mono_slot("hat", channel=1),
        },
        mix_knobs={
            "hat": {"sidechain_from": ["nonexistent"], "sidechain_floor": 60}
        },
    )
    assert _vels(out["hat"]) == [110]  # untouched


def test_sidechain_trigger_at_zero_distance_full_duck() -> None:
    out = _mix(
        voice_events={
            "kick": _notes((0, 10, 36, 110, 60)),
            "hat": _notes((0, 1, 42, 110, 60)),  # simultaneous
        },
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "hat": _mono_slot("hat", channel=1),
        },
        mix_knobs={"hat": {"sidechain_from": "kick", "sidechain_floor": 60}},
    )
    assert _vels(out["hat"]) == [60]


def test_sidechain_past_release_window_no_duck() -> None:
    out = _mix(
        voice_events={
            "kick": _notes((0, 10, 36, 110, 60)),
            "hat": _notes((480, 1, 42, 110, 60)),  # 1 beat later
        },
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "hat": _mono_slot("hat", channel=1),
        },
        mix_knobs={
            "hat": {
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,  # 240 ticks; hat is 480 away
            }
        },
    )
    assert _vels(out["hat"]) == [110]  # untouched


def test_sidechain_multiple_sources_strongest_wins() -> None:
    out = _mix(
        voice_events={
            "kick": _notes((0, 10, 36, 110, 60)),
            "snare": _notes((100, 10, 38, 100, 60)),
            "hat": _notes((110, 1, 42, 110, 60)),
        },
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "snare": _drum_slot("snare", 10, 38),
            "hat": _mono_slot("hat", channel=1),
        },
        mix_knobs={
            "hat": {
                "sidechain_from": ["kick", "snare"],
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # snare at 100 is closer (dist 10) than kick at 0 (dist 110); snare wins.
    # duck = 1 - 10/240 ≈ 0.958; vel ≈ 110*0.042 + 60*0.958 ≈ 4.6 + 57.5 = 62.1.
    assert _vels(out["hat"])[0] <= 65


def test_sidechain_from_previous_bar_carries_over() -> None:
    """A kick on the last tick of bar N-1 still ducks the first ticks of bar N."""
    prev_kick = _notes((1800, 10, 36, 110, 60))  # tick 1800 of prev bar
    curr_hat = _notes((0, 1, 42, 110, 60))  # tick 0 of current bar
    out = _mix(
        voice_events={"kick": [], "hat": curr_hat},
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "hat": _mono_slot("hat", channel=1),
        },
        prev={"kick": prev_kick},
        mix_knobs={
            "hat": {
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,  # 240 ticks
            }
        },
    )
    # Effective trigger tick = 1800 - 1920 = -120. Hat at 0. Distance 120.
    # duck = 0.5; vel = 85.
    assert _vels(out["hat"]) == [85]


def test_sidechain_no_source_is_passthrough() -> None:
    out = _mix(
        voice_events={"hat": _notes((100, 1, 42, 100, 60))},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={"hat": {"sidechain_floor": 60}},  # no source
    )
    assert _vels(out["hat"]) == [100]


def test_sidechain_does_not_affect_non_noteon_events() -> None:
    events: list[Event] = [
        NoteOn(tick=0, channel=10, note=36, velocity=110),  # kick
        NoteOff(tick=60, channel=10, note=36),
    ]
    cc_voice: list[Event] = [
        ControlChange(tick=120, channel=1, cc=74, value=80),
    ]
    out = _mix(
        voice_events={"kick": events, "filt": cc_voice},
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "filt": _mono_slot("filt", channel=1),
        },
        mix_knobs={"filt": {"sidechain_from": "kick", "sidechain_floor": 0}},
    )
    # CCs pass through unchanged.
    assert out["filt"] == cc_voice


# ---------------------------------------------------------- fade-in


def test_fade_in_pre_start_silences_all_notes() -> None:
    """Notes scheduled before fade_in_at_bar are dropped (vel * 0)."""
    out = _mix(
        voice_events={"hat": _notes((0, 1, 42, 110, 60))},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={"hat": {"fade_in_at_bar": 4, "fade_in_beats": 8}},
        bar_index=0,
    )
    # bar 0 << bar 4 → scale = 0 → vel * 0 = 0 → below min_velocity → dropped.
    assert _vels(out["hat"]) == []
    # Matching NoteOff also dropped.
    assert out["hat"] == []


def test_fade_in_at_start_is_silent_during_ramp() -> None:
    """At the exact start of fade_in, velocity is 0 (silence)."""
    out = _mix(
        voice_events={"hat": _notes((0, 1, 42, 110, 60))},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 4}},
        bar_index=0,
    )
    # beat_position = 0, fade_in_start = 0, progress = 0 → scale 0 → dropped.
    assert out["hat"] == []


def test_fade_in_mid_ramp_scales_velocity() -> None:
    """At 50% through the fade-in, velocity = base * 0.5."""
    # bar 1 of a 2-bar fade-in (8 beats total). beat_position at tick 0 = 4.
    # progress = 4/8 = 0.5 → vel 100 * 0.5 = 50.
    out = _mix(
        voice_events={"hat": _notes((0, 1, 42, 100, 60))},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 8}},
        bar_index=1,
    )
    assert _vels(out["hat"]) == [50]


def test_fade_in_after_ramp_returns_to_sustain() -> None:
    out = _mix(
        voice_events={"hat": _notes((0, 1, 42, 100, 60))},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 4}},
        bar_index=4,  # well after fade_in completes (1 bar = 4 beats)
    )
    assert _vels(out["hat"]) == [100]


def test_fade_sustain_level_below_one_attenuates_full_volume() -> None:
    out = _mix(
        voice_events={"hat": _notes((0, 1, 42, 100, 60))},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={
            "hat": {
                "fade_in_at_bar": 0,
                "fade_in_beats": 4,
                "fade_sustain_level": 0.5,
            }
        },
        bar_index=4,
    )
    assert _vels(out["hat"]) == [50]


def test_fade_shape_exp_is_slower_at_start() -> None:
    slots = {"hat": _mono_slot("hat", channel=1)}
    linear = _mix(
        voice_events={"hat": _notes((0, 1, 42, 100, 60))},
        voice_slots=slots,
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 8, "fade_shape": "linear"}},
        bar_index=1,  # 50% through
    )
    exp = _mix(
        voice_events={"hat": _notes((0, 1, 42, 100, 60))},
        voice_slots=slots,
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 8, "fade_shape": "exp"}},
        bar_index=1,
    )
    # At 50% progress: linear = 0.5, exp = 0.25 (quadratic ease-in).
    assert _vels(linear["hat"]) == [50]
    assert _vels(exp["hat"]) == [25]


def test_fade_out_ramps_down() -> None:
    out = _mix(
        voice_events={"hat": _notes((0, 1, 42, 100, 60))},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={"hat": {"fade_out_at_bar": 4, "fade_out_beats": 8}},
        bar_index=5,  # 50% through fade-out
    )
    # bar 5 tick 0 = beat 20. fade_out_start = 16. progress = 4/8 = 0.5.
    # scale = 1 * (1 - 0.5) = 0.5. vel = 50.
    assert _vels(out["hat"]) == [50]


def test_fade_in_dropped_notes_remove_matching_offs() -> None:
    """Below fade_min_velocity → NoteOn AND its NoteOff are removed."""
    events = _notes((0, 1, 42, 100, 60))
    out = _mix(
        voice_events={"hat": events},
        voice_slots={"hat": _mono_slot("hat", channel=1)},
        mix_knobs={"hat": {"fade_in_at_bar": 4, "fade_in_beats": 8, "fade_min_velocity": 5}},
        bar_index=0,
    )
    assert out["hat"] == []  # no orphan NoteOff


def test_fade_in_and_sidechain_compose() -> None:
    """Pipeline order: sidechain ducks first, then fade scales the result.

    With simultaneous kick + hat at 50% through a fade-in:
      step 1 — sidechain: 100 → 60 (full duck, floor 60)
      step 2 — fade:      60 * 0.5 → 30
    """
    out = _mix(
        voice_events={
            "kick": _notes((0, 10, 36, 110, 60)),
            "hat": _notes((0, 1, 42, 100, 60)),
        },
        voice_slots={
            "kick": _drum_slot("kick", 10, 36),
            "hat": _mono_slot("hat", channel=1),
        },
        mix_knobs={
            "hat": {
                "fade_in_at_bar": 0,
                "fade_in_beats": 8,  # 2 bars
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
        bar_index=1,  # 50% through the fade-in ramp
    )
    assert _vels(out["hat"]) == [30]
