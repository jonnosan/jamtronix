"""Tests for the four musicality features added in this PR:

* ``evolution_start`` / ``evolution_end`` velocity ramp (mix pass)
* ``flam_ticks`` on ``drum_one_shot`` (algorithmic flam hits)
* ``vel_curve`` + ``vel_curve_depth`` on ``drum_pattern`` (knob-driven
  per-step velocity shaping)
* ``follow_progression`` voice pattern knob (SongPlayer-level opt-out
  from the chord progression)
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import DrumOneShot, DrumPattern
from jtx.engine.context import BarContext
from jtx.engine.events import NoteOn  # only used by SongPlayer integration tests below
from jtx.engine.mix import apply_mix_pass
from jtx.model.events import AbstractEvent, Hit, Note
from jtx.model.setup import Setup, VoiceSlot
from jtx.model.song import ChordProgression, Key, Part, Song, VoiceConfig
from jtx.player import SongPlayer

# ----------------------------------------------------- mix evolution


def _notes(*specs: tuple[int, int, int, int]) -> list[AbstractEvent]:
    """Build Note events from (tick, pitch, vel, duration) specs."""
    return [
        Note(pitch=pitch, tick=tick, velocity=vel, duration_ticks=dur)
        for tick, pitch, vel, dur in specs
    ]


def _vels(events: list[AbstractEvent]) -> list[int]:
    return [e.velocity for e in events if isinstance(e, Note)]


def _mix(
    *,
    voice_events: dict[str, list[AbstractEvent]],
    mix_knobs: dict[str, dict[str, object]] | None = None,
    bar_index: int = 0,
    part_bars: int = 1,
) -> dict[str, list[AbstractEvent]]:
    return apply_mix_pass(
        voice_events=voice_events,
        prev_voice_events={},
        mix_knobs_by_voice=mix_knobs or {},
        bar_index=bar_index,
        ticks_per_bar=1920,
        ppq=480,
        part_bars=part_bars,
    )


def test_evolution_defaults_no_op() -> None:
    events = _notes((0, 60, 100, 60))
    out = _mix(voice_events={"v": events}, bar_index=0, part_bars=16)
    assert out["v"] == events


def test_evolution_start_scales_first_bar() -> None:
    out = _mix(
        voice_events={"v": _notes((0, 60, 100, 60))},
        mix_knobs={"v": {"evolution_start": 0.5, "evolution_end": 1.0}},
        bar_index=0,
        part_bars=16,
    )
    assert _vels(out["v"]) == [50]


def test_evolution_end_scales_last_bar() -> None:
    out = _mix(
        voice_events={"v": _notes((0, 60, 100, 60))},
        mix_knobs={"v": {"evolution_start": 0.5, "evolution_end": 1.0}},
        bar_index=15,
        part_bars=16,
    )
    assert _vels(out["v"]) == [100]


def test_evolution_midpoint_interpolates() -> None:
    out = _mix(
        voice_events={"v": _notes((0, 60, 100, 60))},
        mix_knobs={"v": {"evolution_start": 0.5, "evolution_end": 1.0}},
        bar_index=7,
        part_bars=15,  # progress 7/14 = 0.5
    )
    # 0.5 + 0.5 * 0.5 = 0.75 → vel 75
    assert _vels(out["v"]) == [75]


def test_evolution_can_ramp_down() -> None:
    out = _mix(
        voice_events={"v": _notes((0, 60, 100, 60))},
        mix_knobs={"v": {"evolution_start": 1.0, "evolution_end": 0.2}},
        bar_index=15,
        part_bars=16,
    )
    assert _vels(out["v"]) == [20]


# ----------------------------------------------------- flam_ticks


def _ctx_for_drum() -> BarContext:
    return BarContext(
        bar_index=0,
        tick_offset=0,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs={},
        rng=random.Random(0),
    )


def test_flam_count_emits_extra_hits() -> None:
    clap = DrumOneShot()
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {
        "pulses": 1,
        "offset": 4,
        "velocity": 100,
        "flam_count": 2,
        "flam_spacing_ticks": 12,
    }
    events = clap.generate_bar(ctx)
    hits = sorted((e for e in events if isinstance(e, Hit)), key=lambda e: e.tick)
    assert len(hits) == 3
    main_tick = 4 * (480 // 4)  # step 4 → tick 480
    assert [h.tick for h in hits] == [main_tick, main_tick + 12, main_tick + 24]


def test_flam_count_velocity_decays() -> None:
    clap = DrumOneShot()
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {
        "pulses": 1,
        "offset": 0,
        "velocity": 100,
        "flam_count": 2,
        "flam_spacing_ticks": 12,
        "flam_decay": 0.5,
    }
    events = clap.generate_bar(ctx)
    hits = sorted((e for e in events if isinstance(e, Hit)), key=lambda e: e.tick)
    assert [h.velocity for h in hits] == [100, 50, 25]


def test_flam_count_zero_means_no_flam() -> None:
    clap = DrumOneShot()
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {"pulses": 1, "offset": 0}
    events = clap.generate_bar(ctx)
    assert len([e for e in events if isinstance(e, Hit)]) == 1


# --------------------------------------- drum_pattern vel_curve


def test_vel_curve_flat_is_unchanged() -> None:
    kick = DrumPattern(piece="kick")
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {"style": "four_floor", "velocity": 100, "vel_curve": "flat"}
    events = kick.generate_bar(ctx)
    assert all(h.velocity == 100 for h in events if isinstance(h, Hit))


def test_vel_curve_depth_zero_is_unchanged() -> None:
    kick = DrumPattern(piece="kick")
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {
        "style": "four_floor",
        "velocity": 100,
        "vel_curve": "ramp_up",
        "vel_curve_depth": 0,
    }
    events = kick.generate_bar(ctx)
    assert all(h.velocity == 100 for h in events if isinstance(h, Hit))


def test_vel_curve_ramp_up_increases_across_bar() -> None:
    kick = DrumPattern(piece="kick")
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {
        "style": "four_floor",
        "velocity": 100,
        "vel_curve": "ramp_up",
        "vel_curve_depth": 0.4,
    }
    events = kick.generate_bar(ctx)
    hits = sorted((e for e in events if isinstance(e, Hit)), key=lambda e: e.tick)
    vels = [h.velocity for h in hits]
    assert vels[0] < vels[-1]


def test_vel_curve_arc_peaks_in_middle() -> None:
    kick = DrumPattern(piece="kick")
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {
        "style": "four_floor",
        "velocity": 100,
        "vel_curve": "arc",
        "vel_curve_depth": 0.4,
    }
    events = kick.generate_bar(ctx)
    hits = sorted((e for e in events if isinstance(e, Hit)), key=lambda e: e.tick)
    vels = [h.velocity for h in hits]
    assert max(vels[1], vels[2]) > max(vels[0], vels[3])


def test_vel_curve_pulse_accents_downbeats() -> None:
    hat = DrumPattern(piece="hat")
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {
        "style": "euclid",
        "pulses": 8,
        "velocity": 80,
        "vel_curve": "pulse",
        "vel_curve_depth": 0.4,
    }
    events = hat.generate_bar(ctx)
    hits = sorted((e for e in events if isinstance(e, Hit)), key=lambda e: e.tick)
    s = 480 // 4
    for h in hits:
        step = h.tick // s
        if step % 4 == 0:
            assert h.velocity > 100
        else:
            assert h.velocity == 80


def test_vel_curve_drift_is_seed_deterministic() -> None:
    """Bar-seeded drift: same seed → same per-step variations."""
    ctx_a = _ctx_for_drum()
    ctx_a.rng = random.Random(42)
    ctx_a.pattern_knobs = {
        "style": "four_floor",
        "velocity": 100,
        "vel_curve": "drift",
        "vel_curve_depth": 0.3,
    }
    ctx_b = _ctx_for_drum()
    ctx_b.rng = random.Random(42)
    ctx_b.pattern_knobs = ctx_a.pattern_knobs
    a = DrumPattern(piece="kick").generate_bar(ctx_a)
    b = DrumPattern(piece="kick").generate_bar(ctx_b)
    assert [h.velocity for h in a if isinstance(h, Hit)] == [
        h.velocity for h in b if isinstance(h, Hit)
    ]


def test_vel_curve_drift_differs_for_different_seeds() -> None:
    """Same setting + different seeds = different musical variation."""
    base_knobs = {
        "style": "four_floor",
        "velocity": 100,
        "vel_curve": "drift",
        "vel_curve_depth": 0.5,
    }
    ctx_a = _ctx_for_drum()
    ctx_a.rng = random.Random(1)
    ctx_a.pattern_knobs = base_knobs
    ctx_b = _ctx_for_drum()
    ctx_b.rng = random.Random(2)
    ctx_b.pattern_knobs = base_knobs
    a = DrumPattern(piece="kick").generate_bar(ctx_a)
    b = DrumPattern(piece="kick").generate_bar(ctx_b)
    assert [h.velocity for h in a if isinstance(h, Hit)] != [
        h.velocity for h in b if isinstance(h, Hit)
    ]


def test_vel_curve_unknown_raises() -> None:
    kick = DrumPattern(piece="kick")
    ctx = _ctx_for_drum()
    ctx.pattern_knobs = {
        "style": "four_floor",
        "vel_curve": "bogus",
        "vel_curve_depth": 0.3,
    }
    with pytest.raises(ValueError, match="unknown vel_curve"):
        kick.generate_bar(ctx)


# ------------------------------------- follow_progression on voices


def _player_with_voices(*, follow_kick: bool = True, follow_bass: bool = True) -> SongPlayer:
    setup = Setup(
        id="t",
        name="t",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(
                name="kick",
                type="drum",
                default_role="drum",
                midi_channel=10,
                note=36,
            ),
            VoiceSlot(name="bass", type="mono", default_role="bass", midi_channel=1),
        ],
    )
    kick_pattern: dict[str, object] = {"style": "four_floor"}
    if not follow_kick:
        kick_pattern["follow_progression"] = False
    bass_pattern: dict[str, object] = {
        "drop_prob": 0.0,
        "bend": 0,
        "cycle": 0,
    }
    if not follow_bass:
        bass_pattern["follow_progression"] = False
    song = Song(
        title="t",
        setup_ref="t",
        key=Key(tonic="A", scale="minor"),
        chord_progression=ChordProgression(degrees=["i", "III", "VII"], bars_per_chord=1),
        voices={
            "kick": VoiceConfig(algorithm="drum_pattern", pattern=kick_pattern),
            "bass": VoiceConfig(algorithm="acid_bass", pattern=bass_pattern),
        },
        parts={"drop": Part(bars=4)},
        arrangement=["drop"],
    )
    return SongPlayer(song, setup, "drop")


def test_follow_progression_default_true() -> None:
    """Bass without follow_progression knob — should follow chord changes."""
    player = _player_with_voices()
    # Bar 1 = VI = +8 semitones; bass should fire higher pitches.
    bar0_bass = [
        e.note for e in player.events_for_bar(0) if isinstance(e, NoteOn) and e.channel == 1
    ]
    bar1_bass = [
        e.note for e in player.events_for_bar(1) if isinstance(e, NoteOn) and e.channel == 1
    ]
    # Bar 0: chord_root=0 → root A1 + chord_root = 45 + 0 = 45 ish
    # Bar 1: chord_root=8 → root A1 + 8 = 53 ish (F2)
    # The acid_bass picks among root/oct/m3 so check the min pitches differ.
    assert min(bar0_bass) != min(bar1_bass)


def test_follow_progression_false_stays_on_root() -> None:
    """Bass with follow_progression=false — same pitches every bar."""
    player = _player_with_voices(follow_bass=False)
    bar0_bass = sorted(
        {e.note for e in player.events_for_bar(0) if isinstance(e, NoteOn) and e.channel == 1}
    )
    bar1_bass = sorted(
        {e.note for e in player.events_for_bar(1) if isinstance(e, NoteOn) and e.channel == 1}
    )
    bar2_bass = sorted(
        {e.note for e in player.events_for_bar(2) if isinstance(e, NoteOn) and e.channel == 1}
    )
    # All bars sit on the same root (A) regardless of progression.
    # The pitch *set* (root / octave / m3) should be identical bar-to-bar.
    assert bar0_bass == bar1_bass == bar2_bass


def test_follow_progression_per_voice() -> None:
    """Voices choose independently — bass static while kick (irrelevant
    here, drums don't use chord_root) is unaffected either way."""
    player = _player_with_voices(follow_bass=False, follow_kick=False)
    # No assertion about pitch — kick is a drum, doesn't use chord_root.
    # Just make sure construction + bar generation doesn't crash.
    assert player.events_for_bar(0) != []
