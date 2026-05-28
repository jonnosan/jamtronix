"""Tests for the mix pass — fade-in/out + sidechain ducking.

Schema v3: mix runs on abstract events. Sidechain matches by
``Hit.instrument``; fade + evolution scale ``.velocity`` on Hit + Note.
"""

from __future__ import annotations

from jtx.engine.mix import apply_mix_pass
from jtx.model.events import AbstractEvent, Hit, Note, Param


def _hits(*specs: tuple[str, int, int, int]) -> list[AbstractEvent]:
    """Build Hit events from (instrument, tick, velocity, duration)."""
    return [
        Hit(instrument=instrument, tick=tick, velocity=vel, duration_ticks=dur)
        for instrument, tick, vel, dur in specs
    ]


def _notes(*specs: tuple[int, int, int, int]) -> list[AbstractEvent]:
    """Build Note events from (pitch, tick, velocity, duration)."""
    return [
        Note(pitch=pitch, tick=tick, velocity=vel, duration_ticks=dur)
        for pitch, tick, vel, dur in specs
    ]


def _hit_vels(events: list[AbstractEvent]) -> list[int]:
    return [e.velocity for e in events if isinstance(e, Hit)]


def _note_vels(events: list[AbstractEvent]) -> list[int]:
    return [e.velocity for e in events if isinstance(e, Note)]


def _mix(
    *,
    voice_events: dict[str, list[AbstractEvent]],
    mix_knobs: dict[str, dict[str, object]] | None = None,
    prev: dict[str, list[AbstractEvent]] | None = None,
    bar_index: int = 0,
    part_bars: int = 1,
) -> dict[str, list[AbstractEvent]]:
    return apply_mix_pass(
        voice_events=voice_events,
        prev_voice_events=prev or {},
        mix_knobs_by_voice=mix_knobs or {},
        bar_index=bar_index,
        ticks_per_bar=1920,
        ppq=480,
        part_bars=part_bars,
    )


# ---------------------------------------------------------- no-op


def test_mix_pass_empty_knobs_is_identity() -> None:
    events = _notes((60, 0, 100, 120))
    out = _mix(voice_events={"v": events})
    assert out["v"] == events


# ---------------------------------------------------------- sidechain by instrument name


def test_sidechain_trigger_in_same_bar_ducks() -> None:
    """Hit at tick T+release/2 ducks a target Note to ~halfway."""
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "hat": _notes((42, 120, 110, 60)),
        },
        mix_knobs={
            "hat": {
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # distance 120 / release 240 = 0.5 duck → vel 110*0.5 + 60*0.5 = 85.
    assert _note_vels(out["hat"]) == [85]


def test_sidechain_kick_inside_drum_kit_triggers_via_instrument_name() -> None:
    """A drum_kit voice emits Hit(instrument="kick") + Hit(instrument="snare").
    sidechain_from=["kick"] picks up only the kick Hits."""
    kit_events = _hits(("snare", 60, 100, 60), ("kick", 0, 110, 60))
    out = _mix(
        voice_events={
            "kit": kit_events,
            "bass": _notes((40, 120, 110, 60)),
        },
        mix_knobs={
            "bass": {
                "sidechain_from": ["kick"],
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # kick at 0, bass at 120 → duck 0.5 → vel 85.
    # snare at 60 (matches name "snare", not "kick") is not a trigger.
    assert _note_vels(out["bass"]) == [85]


def test_sidechain_snare_picks_up_only_snare_hits() -> None:
    out = _mix(
        voice_events={
            "kit": _hits(("kick", 0, 110, 60), ("snare", 120, 100, 60)),
            "bass": _notes((40, 180, 110, 60)),
        },
        mix_knobs={
            "bass": {
                "sidechain_from": ["snare"],
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # snare at 120, bass at 180. Distance 60, release 240 → duck 0.75.
    # vel = 110*0.25 + 60*0.75 = 72.5 → 72 (banker's rounding).
    assert _note_vels(out["bass"]) == [72]


def test_sidechain_unknown_instrument_is_no_op() -> None:
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "hat": _notes((42, 100, 110, 60)),
        },
        mix_knobs={
            "hat": {"sidechain_from": ["nonexistent"], "sidechain_floor": 60}
        },
    )
    assert _note_vels(out["hat"]) == [110]  # untouched


def test_sidechain_trigger_at_zero_distance_full_duck() -> None:
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "hat": _notes((42, 0, 110, 60)),
        },
        mix_knobs={"hat": {"sidechain_from": "kick", "sidechain_floor": 60}},
    )
    assert _note_vels(out["hat"]) == [60]


def test_sidechain_past_release_window_no_duck() -> None:
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "hat": _notes((42, 480, 110, 60)),
        },
        mix_knobs={
            "hat": {
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    assert _note_vels(out["hat"]) == [110]  # untouched


def test_sidechain_multiple_sources_strongest_wins() -> None:
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "snare": _hits(("snare", 100, 100, 60)),
            "hat": _notes((42, 110, 110, 60)),
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
    assert _note_vels(out["hat"])[0] <= 65


def test_sidechain_from_previous_bar_carries_over() -> None:
    prev_kick = _hits(("kick", 1800, 110, 60))
    curr_hat = _notes((42, 0, 110, 60))
    out = _mix(
        voice_events={"kick": [], "hat": curr_hat},
        prev={"kick": prev_kick},
        mix_knobs={
            "hat": {
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # Effective trigger tick = 1800 - 1920 = -120. Hat at 0 → duck 0.5 → vel 85.
    assert _note_vels(out["hat"]) == [85]


def test_sidechain_no_source_is_passthrough() -> None:
    out = _mix(
        voice_events={"hat": _notes((42, 100, 100, 60))},
        mix_knobs={"hat": {"sidechain_floor": 60}},  # no source
    )
    assert _note_vels(out["hat"]) == [100]


def test_sidechain_does_not_affect_param_events() -> None:
    """Param events (CC streams) pass through unchanged — sidechain only
    touches velocity, which Param doesn't have."""
    events: list[AbstractEvent] = [
        Param(name="cutoff", value=0.6, tick=120),
    ]
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "filt": events,
        },
        mix_knobs={"filt": {"sidechain_from": "kick", "sidechain_floor": 0}},
    )
    assert out["filt"] == events


# ---------------------------------------------------------- fade-in


def test_fade_in_pre_start_drops_all_events() -> None:
    out = _mix(
        voice_events={"hat": _notes((42, 0, 110, 60))},
        mix_knobs={"hat": {"fade_in_at_bar": 4, "fade_in_beats": 8}},
        bar_index=0,
    )
    # Pre-fade-in window → scale 0 → below min_velocity → dropped.
    assert out["hat"] == []


def test_fade_in_at_start_is_silent_during_ramp() -> None:
    out = _mix(
        voice_events={"hat": _notes((42, 0, 110, 60))},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 4}},
        bar_index=0,
    )
    assert out["hat"] == []


def test_fade_in_mid_ramp_scales_velocity() -> None:
    out = _mix(
        voice_events={"hat": _notes((42, 0, 100, 60))},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 8}},
        bar_index=1,
    )
    # bar 1 of 2-bar fade → progress 0.5 → vel 50.
    assert _note_vels(out["hat"]) == [50]


def test_fade_in_after_ramp_returns_to_sustain() -> None:
    out = _mix(
        voice_events={"hat": _notes((42, 0, 100, 60))},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 4}},
        bar_index=4,
    )
    assert _note_vels(out["hat"]) == [100]


def test_fade_sustain_level_below_one_attenuates_full_volume() -> None:
    out = _mix(
        voice_events={"hat": _notes((42, 0, 100, 60))},
        mix_knobs={
            "hat": {
                "fade_in_at_bar": 0,
                "fade_in_beats": 4,
                "fade_sustain_level": 0.5,
            }
        },
        bar_index=4,
    )
    assert _note_vels(out["hat"]) == [50]


def test_fade_shape_exp_is_slower_at_start() -> None:
    linear = _mix(
        voice_events={"hat": _notes((42, 0, 100, 60))},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 8, "fade_shape": "linear"}},
        bar_index=1,
    )
    exp = _mix(
        voice_events={"hat": _notes((42, 0, 100, 60))},
        mix_knobs={"hat": {"fade_in_at_bar": 0, "fade_in_beats": 8, "fade_shape": "exp"}},
        bar_index=1,
    )
    assert _note_vels(linear["hat"]) == [50]
    assert _note_vels(exp["hat"]) == [25]


def test_fade_out_ramps_down() -> None:
    out = _mix(
        voice_events={"hat": _notes((42, 0, 100, 60))},
        mix_knobs={"hat": {"fade_out_at_bar": 4, "fade_out_beats": 8}},
        bar_index=5,
    )
    assert _note_vels(out["hat"]) == [50]


def test_fade_drops_event_below_min_velocity() -> None:
    """An abstract Note that ends up below fade_min_velocity is dropped
    entirely — no orphan NoteOff cleanup needed in the abstract pipeline."""
    out = _mix(
        voice_events={"hat": _notes((42, 0, 100, 60))},
        mix_knobs={"hat": {"fade_in_at_bar": 4, "fade_in_beats": 8, "fade_min_velocity": 5}},
        bar_index=0,
    )
    assert out["hat"] == []


def test_fade_in_and_sidechain_compose() -> None:
    """Sidechain ducks first, fade scales the result.

    Simultaneous kick + hat at 50% through a fade-in:
      step 1 — sidechain: 100 → 60 (full duck, floor 60)
      step 2 — fade:      60 * 0.5 → 30
    """
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "hat": _notes((42, 0, 100, 60)),
        },
        mix_knobs={
            "hat": {
                "fade_in_at_bar": 0,
                "fade_in_beats": 8,
                "sidechain_from": "kick",
                "sidechain_floor": 60,
                "sidechain_release_beats": 0.5,
            }
        },
        bar_index=1,
    )
    assert _note_vels(out["hat"]) == [30]


# ---------------------------------------------------------- sidechain ducks Hit + Note alike


def test_sidechain_ducks_hit_targets() -> None:
    """A target voice emitting Hit events gets the same ducking treatment as Notes."""
    out = _mix(
        voice_events={
            "kick": _hits(("kick", 0, 110, 60)),
            "perc": _hits(("perc", 0, 100, 60)),
        },
        mix_knobs={
            "perc": {
                "sidechain_from": ["kick"],
                "sidechain_floor": 50,
                "sidechain_release_beats": 0.5,
            }
        },
    )
    # Simultaneous trigger → full duck → vel 50.
    assert _hit_vels(out["perc"]) == [50]
