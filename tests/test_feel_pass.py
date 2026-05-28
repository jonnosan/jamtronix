"""Tests for the post-emit feel pass.

Schema v3 + abstract-events refactor: apply_feel operates on abstract
events (Hit / Note / Param / PolyAftertouch). Pump + Tension are
handled elsewhere; this pass implements Groove, Drive, Wander.
"""

from __future__ import annotations

import random

import pytest

from jtx.engine.feel import apply_feel
from jtx.model.events import AbstractEvent, Hit, Note, Param
from jtx.model.setup import VoiceSlot


def _lead_slot(channel: int = 1) -> VoiceSlot:
    return VoiceSlot(name="lead", type="mono", default_role="lead", midi_channel=channel)


def _bass_slot(channel: int = 1) -> VoiceSlot:
    return VoiceSlot(name="bass", type="mono", default_role="bass", midi_channel=channel)


def _kick_slot(channel: int = 10) -> VoiceSlot:
    return VoiceSlot(
        name="kick", type="drum", default_role="drum", midi_channel=channel, note=36
    )


def _kit_slot() -> VoiceSlot:
    from jtx.model.setup import KitPiece

    return VoiceSlot(
        name="kit",
        type="drum_kit",
        default_role="drum_kit",
        midi_channel=10,
        kit_map={
            "kick": KitPiece(note=36, channel=10),
            "snare": KitPiece(note=38, channel=10),
            "chh": KitPiece(note=42, channel=11),
        },
    )


def _notes(*specs: tuple[int, int, int, int]) -> list[AbstractEvent]:
    """Build Note events from (pitch, tick, velocity, duration) specs."""
    return [
        Note(pitch=pitch, tick=tick, velocity=vel, duration_ticks=dur)
        for pitch, tick, vel, dur in specs
    ]


def _hits(*specs: tuple[str, int, int, int]) -> list[AbstractEvent]:
    """Build Hit events from (instrument, tick, velocity, duration) specs."""
    return [
        Hit(instrument=instrument, tick=tick, velocity=vel, duration_ticks=dur)
        for instrument, tick, vel, dur in specs
    ]


# ---------------------------------------------------------- identity


def test_apply_feel_zero_song_feel_is_identity() -> None:
    events = _notes((60, 0, 100, 120), (64, 480, 100, 120))
    out = apply_feel(events, {}, _lead_slot(), ppq=480, rng=random.Random(0))
    assert out == events


def test_apply_feel_passes_param_through() -> None:
    events: list[AbstractEvent] = [Param(name="cutoff", tick=0, value=0.5)]
    out = apply_feel(events, {"groove": 0.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    assert len(out) == 1
    assert isinstance(out[0], Param)
    assert out[0].name == "cutoff" and out[0].value == 0.5


# ---------------------------------------------------------- groove → swing


def test_groove_full_swings_lead_note_ticks() -> None:
    # Notes on steps 0, 1, 2, 3 (ticks 0, 120, 240, 360 at PPQ 480).
    events = _notes(
        (60, 0, 100, 60),
        (62, 120, 100, 60),
        (64, 240, 100, 60),
        (65, 360, 100, 60),
    )
    out = apply_feel(events, {"groove": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    ticks = sorted(n.tick for n in out if isinstance(n, Note))
    # Even steps stay within humanize ±8; odd steps shift +40 ±8.
    assert ticks[0] < ticks[1]
    assert 150 <= ticks[1] <= 170
    assert 390 <= ticks[3] <= 410


def test_groove_does_not_swing_bass_notes() -> None:
    events = _notes((60, 120, 100, 60))  # step 1 — would swing on lead
    out = apply_feel(events, {"groove": 1.0}, _bass_slot(), ppq=480, rng=random.Random(0))
    note = next(n for n in out if isinstance(n, Note))
    # No swing shift; only humanize (±8). Stays in [112, 128].
    assert 112 <= note.tick <= 128


def test_groove_swings_hat_hits_in_drum_kit_but_not_kick() -> None:
    """Inside a drum_kit voice, hat-name Hits swing but kick Hits don't."""
    events = _hits(
        ("kick", 120, 100, 30),
        ("chh", 120, 100, 30),
    )
    out = apply_feel(events, {"groove": 1.0}, _kit_slot(), ppq=480, rng=random.Random(0))
    by_inst = {h.instrument: h for h in out if isinstance(h, Hit)}
    # Kick: only humanize ±8.
    assert 112 <= by_inst["kick"].tick <= 128
    # Hat: humanize ±8 + swing +40 → [152, 168].
    assert 152 <= by_inst["chh"].tick <= 168


def test_groove_accent_boosts_velocity_on_beats_2_and_4() -> None:
    """Beats 2 (step 4) and 4 (step 12) get accented."""
    events = _notes(
        (60, 0, 90, 60),  # step 0 — not accented
        (60, 480, 90, 60),  # step 4 — beat 2 — accented
        (60, 1440, 90, 60),  # step 12 — beat 4 — accented
    )
    out = apply_feel(events, {"groove": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    notes = sorted((n for n in out if isinstance(n, Note)), key=lambda n: n.tick)
    assert notes[0].velocity == 90
    assert notes[1].velocity == 104
    assert notes[2].velocity == 104


# ---------------------------------------------------------- drive → velocity


def test_drive_full_boosts_velocity_globally() -> None:
    events = _notes((60, 0, 80, 60))
    out = apply_feel(events, {"drive": 1.0}, _bass_slot(), ppq=480, rng=random.Random(0))
    note = next(n for n in out if isinstance(n, Note))
    assert note.velocity == 95  # 80 + 15


def test_drive_clamps_at_127() -> None:
    events = _notes((60, 0, 125, 60))
    out = apply_feel(events, {"drive": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    note = next(n for n in out if isinstance(n, Note))
    assert note.velocity == 127


def test_drive_boosts_hit_velocity_too() -> None:
    """Drive applies to Hit events on drum-kit voices."""
    events = _hits(("kick", 0, 100, 30))
    out = apply_feel(events, {"drive": 1.0}, _kit_slot(), ppq=480, rng=random.Random(0))
    hit = next(h for h in out if isinstance(h, Hit))
    assert hit.velocity == 115


def test_drive_pushes_cutoff_param_upward() -> None:
    """Drive shifts every Param(name='cutoff').value up by drive*0.2,
    clamped at 1.0. Pairs with the velocity boost for the 'push the
    mix harder' feel."""
    events: list[AbstractEvent] = [Param(name="cutoff", tick=0, value=0.5)]
    out = apply_feel(events, {"drive": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    param = out[0]
    assert isinstance(param, Param)
    # drive=1.0 → +0.2 → 0.7.
    assert param.value == pytest.approx(0.7)


def test_drive_cutoff_push_clamps_at_one() -> None:
    events: list[AbstractEvent] = [Param(name="cutoff", tick=0, value=0.95)]
    out = apply_feel(events, {"drive": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    assert isinstance(out[0], Param)
    assert out[0].value == pytest.approx(1.0)


def test_drive_cutoff_push_scales_with_drive() -> None:
    """drive=0.5 → +0.1; drive=0 → no change."""
    events: list[AbstractEvent] = [Param(name="cutoff", tick=0, value=0.5)]
    half = apply_feel(events, {"drive": 0.5}, _lead_slot(), ppq=480, rng=random.Random(0))
    zero = apply_feel(events, {"drive": 0.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    assert isinstance(half[0], Param) and isinstance(zero[0], Param)
    assert half[0].value == pytest.approx(0.6)
    assert zero[0].value == pytest.approx(0.5)


def test_drive_does_not_affect_non_cutoff_params() -> None:
    """Only ``cutoff`` is in _DRIVE_PUSH_FUNCTIONS; other functions
    (resonance, glide, bend, …) pass through unchanged."""
    events: list[AbstractEvent] = [
        Param(name="resonance", tick=0, value=0.5),
        Param(name="glide", tick=0, value=0.2),
        Param(name="bend", tick=0, value=0.1),
    ]
    out = apply_feel(events, {"drive": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    values = [e.value for e in out if isinstance(e, Param)]
    assert values == [0.5, 0.2, 0.1]


# ---------------------------------------------------------- wander → mute / octave


def test_wander_full_can_drop_entire_bar() -> None:
    events = _notes((60, 0, 100, 60), (62, 240, 100, 60))
    dropped = 0
    total = 200
    for seed in range(total):
        out = apply_feel(events, {"wander": 1.0}, _lead_slot(), ppq=480, rng=random.Random(seed))
        if not out:
            dropped += 1
    # Expected ~10% (= 20). Generous tolerance.
    assert 5 <= dropped <= 40, f"dropped {dropped}/{total}"


def test_wander_zero_never_drops() -> None:
    events = _notes((60, 0, 100, 60))
    for seed in range(20):
        out = apply_feel(events, {"wander": 0.0}, _lead_slot(), ppq=480, rng=random.Random(seed))
        assert len(out) == len(events)


def test_wander_octave_jump_only_on_melodic_voices() -> None:
    """Octave jump fires on lead/bass/etc., never on drum / drum_kit voices."""
    events = _hits(("kick", 0, 100, 30))
    for seed in range(50):
        out = apply_feel(events, {"wander": 1.0}, _kick_slot(), ppq=480, rng=random.Random(seed))
        if out:
            # Hits never carry pitch; they shouldn't be transformed.
            assert all(isinstance(h, Hit) and h.instrument == "kick" for h in out)


def test_wander_octave_jump_can_shift_melodic_note() -> None:
    events = _notes((60, 0, 100, 60))
    shifted_count = 0
    for seed in range(50):
        out = apply_feel(events, {"wander": 1.0}, _lead_slot(), ppq=480, rng=random.Random(seed))
        if not out:
            continue
        note = next(n for n in out if isinstance(n, Note))
        if note.pitch != 60:
            shifted_count += 1
            assert note.pitch in (48, 72)
    assert shifted_count > 0


# ---------------------------------------------------------- determinism


def test_apply_feel_is_deterministic_with_same_seed() -> None:
    events = _notes((60, 0, 100, 60), (62, 240, 100, 60))
    feel = {"groove": 0.7, "drive": 0.5, "wander": 0.3}
    out1 = apply_feel(events, feel, _lead_slot(), ppq=480, rng=random.Random(42))
    out2 = apply_feel(events, feel, _lead_slot(), ppq=480, rng=random.Random(42))
    assert out1 == out2


def test_apply_feel_humanize_clamps_to_zero() -> None:
    events = _notes((60, 5, 100, 60))
    out = apply_feel(events, {"groove": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    note = next(n for n in out if isinstance(n, Note))
    assert note.tick >= 0


# ---------------------------------------------------------- pump is not handled here


def test_pump_in_song_feel_is_no_op_in_feel_pass() -> None:
    events = _notes((60, 0, 100, 60))
    out = apply_feel(events, {"pump": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    assert out == events
