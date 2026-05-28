"""Tests for the post-emit feel pass.

Schema v3: the per-voice "feel" knob dict is gone. apply_feel takes
:attr:`Song.feel` (pump / groove / drive / tension / wander) and the
voice's :class:`VoiceSlot`. Pump + Tension are handled elsewhere; the
post-emit pass implements Groove, Drive, Wander.
"""

from __future__ import annotations

import random

from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn
from jtx.engine.feel import apply_feel
from jtx.model.setup import KitPiece, VoiceSlot


def _notes(*specs: tuple[int, int, int, int, int]) -> list[Event]:
    """Build NoteOn/NoteOff pairs from (tick, channel, note, vel, dur) specs."""
    out: list[Event] = []
    for tick, ch, note, vel, dur in specs:
        out.append(NoteOn(tick=tick, channel=ch, note=note, velocity=vel))
        out.append(NoteOff(tick=tick + dur, channel=ch, note=note))
    return out


def _lead_slot(channel: int = 1) -> VoiceSlot:
    return VoiceSlot(name="lead", type="mono", default_role="lead", midi_channel=channel)


def _bass_slot(channel: int = 1) -> VoiceSlot:
    return VoiceSlot(name="bass", type="mono", default_role="bass", midi_channel=channel)


def _kick_slot(channel: int = 10) -> VoiceSlot:
    return VoiceSlot(
        name="kick", type="drum", default_role="drum", midi_channel=channel, note=36
    )


def _hat_slot(channel: int = 11) -> VoiceSlot:
    return VoiceSlot(
        name="chh", type="drum", default_role="drum", midi_channel=channel, note=42
    )


def _kit_slot() -> VoiceSlot:
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


# ---------------------------------------------------------- identity


def test_apply_feel_zero_song_feel_is_identity() -> None:
    events = _notes((0, 1, 60, 100, 120), (480, 1, 64, 100, 120))
    out = apply_feel(events, {}, _lead_slot(), ppq=480, rng=random.Random(0))
    assert out == events


def test_apply_feel_passes_control_change_through() -> None:
    events: list[Event] = [
        ControlChange(tick=0, channel=2, cc=74, value=64),
    ]
    out = apply_feel(events, {"groove": 0.0}, _lead_slot(), ppq=480, rng=random.Random(0))
    assert len(out) == 1
    cc = out[0]
    assert isinstance(cc, ControlChange)
    assert cc.cc == 74 and cc.value == 64


# ---------------------------------------------------------- groove → swing


def test_groove_full_swings_lead_note_ticks() -> None:
    # Notes on steps 0, 1, 2, 3 (= ticks 0, 120, 240, 360 at PPQ 480).
    # We need humanize=0 so we can verify the exact tick. Trick: groove=1.0
    # implies humanize=8. Compensate by using a seed where humanize draws
    # zero for the events we measure — easier to just measure offsets
    # statistically. Instead, isolate by reducing groove to ratio of swing
    # only by using a custom test seed that yields humanize=0... too tricky.
    # Just measure the on-step displacement: odd steps shift by ~40 ticks.
    events = _notes(
        (0, 1, 60, 100, 60),
        (120, 1, 62, 100, 60),
        (240, 1, 64, 100, 60),
        (360, 1, 65, 100, 60),
    )
    out = apply_feel(
        events, {"groove": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0)
    )
    on_ticks = sorted(e.tick for e in out if isinstance(e, NoteOn))
    # Even steps (0, 240) ≈ unchanged within ±8 humanize; odd steps shift +40 ±8.
    # Verify the ordering and gross structure.
    assert on_ticks[0] < on_ticks[1]
    assert on_ticks[1] > on_ticks[0] + 100  # +120 base + 40 swing > 100 minimum
    # Odd-step shift (≈40) places step-1 between 152 and 168.
    assert 150 <= on_ticks[1] <= 170
    assert 390 <= on_ticks[3] <= 410


def test_groove_does_not_swing_bass_notes() -> None:
    """Bass voice (role=bass) doesn't swing under Groove — only humanize."""
    events = _notes((120, 1, 60, 100, 60))  # step 1 — would swing on a lead
    out = apply_feel(
        events, {"groove": 1.0}, _bass_slot(), ppq=480, rng=random.Random(0)
    )
    on = next(e for e in out if isinstance(e, NoteOn))
    # No swing shift (+40); only humanize (±8). So tick stays in [112, 128].
    assert 112 <= on.tick <= 128


def test_groove_swings_hat_pieces_in_drum_kit_but_not_kicks() -> None:
    """Inside a drum_kit, only hat-named pieces swing — kicks stay grid."""
    events = _notes(
        (120, 10, 36, 100, 30),  # kick on odd step — should NOT swing
        (120, 11, 42, 100, 30),  # chh on odd step — SHOULD swing
    )
    out = apply_feel(
        events, {"groove": 1.0}, _kit_slot(), ppq=480, rng=random.Random(0)
    )
    on_by_note = {e.note: e for e in out if isinstance(e, NoteOn)}
    # Kick (note 36): only humanize ±8.
    assert 112 <= on_by_note[36].tick <= 128
    # Hat (note 42): humanize ±8 + swing +40 → tick in [152, 168].
    assert 152 <= on_by_note[42].tick <= 168


def test_groove_accent_boosts_velocity_on_beats_2_and_4() -> None:
    """Beats 2 (step 4 = tick 480) and 4 (step 12 = tick 1440) get accented."""
    events = _notes(
        (0, 1, 60, 90, 60),  # step 0 — not accented
        (480, 1, 60, 90, 60),  # step 4 — beat 2 — accented
        (1440, 1, 60, 90, 60),  # step 12 — beat 4 — accented
    )
    out = apply_feel(
        events, {"groove": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0)
    )
    ons = sorted((e for e in out if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # Step 0 → 90; steps 4 + 12 → 90 + 14 = 104.
    assert ons[0].velocity == 90
    assert ons[1].velocity == 104
    assert ons[2].velocity == 104


# ---------------------------------------------------------- drive → velocity


def test_drive_full_boosts_velocity_globally() -> None:
    """drive=1.0 → +15 vel on every NoteOn, regardless of role."""
    events = _notes((0, 1, 60, 80, 60))
    out = apply_feel(
        events, {"drive": 1.0}, _bass_slot(), ppq=480, rng=random.Random(0)
    )
    on = next(e for e in out if isinstance(e, NoteOn))
    assert on.velocity == 95  # 80 + 15


def test_drive_clamps_at_127() -> None:
    events = _notes((0, 1, 60, 125, 60))
    out = apply_feel(
        events, {"drive": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0)
    )
    on = next(e for e in out if isinstance(e, NoteOn))
    assert on.velocity == 127


def test_drive_does_not_affect_control_change() -> None:
    events: list[Event] = [ControlChange(tick=0, channel=1, cc=74, value=64)]
    out = apply_feel(
        events, {"drive": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0)
    )
    assert out == events


# ---------------------------------------------------------- wander → mute / octave


def test_wander_full_can_drop_entire_bar() -> None:
    """With wander=1.0 (10% mute prob) we expect SOME seeds to drop the bar."""
    events = _notes((0, 1, 60, 100, 60), (240, 1, 62, 100, 60))
    dropped = 0
    total = 200
    for seed in range(total):
        out = apply_feel(
            events, {"wander": 1.0}, _lead_slot(), ppq=480, rng=random.Random(seed)
        )
        if not out:
            dropped += 1
    # Expected ~10% (= 20). Allow generous wiggle room.
    assert 5 <= dropped <= 40, f"dropped {dropped}/{total} — expected ~20"


def test_wander_zero_never_drops() -> None:
    events = _notes((0, 1, 60, 100, 60))
    for seed in range(20):
        out = apply_feel(
            events, {"wander": 0.0}, _lead_slot(), ppq=480, rng=random.Random(seed)
        )
        assert len(out) == len(events)


def test_wander_octave_jump_only_on_melodic_voices() -> None:
    """Octave jump fires on lead/bass/etc., never on drum / drum_kit voices."""
    events = _notes((0, 10, 36, 100, 30))  # a kick hit
    # With wander=1.0 (15% per-note jump) on a drum voice, the kick
    # should NEVER move pitch. Try many seeds.
    for seed in range(50):
        out = apply_feel(
            events, {"wander": 1.0}, _kick_slot(), ppq=480, rng=random.Random(seed)
        )
        if out:
            assert all(
                not isinstance(e, NoteOn) or e.note == 36 for e in out
            ), f"kick pitch moved at seed {seed}"


def test_wander_octave_jump_can_shift_melodic_note() -> None:
    """High wander on a lead — at least one seed should jump the note."""
    events = _notes((0, 1, 60, 100, 60))
    shifted_count = 0
    for seed in range(50):
        out = apply_feel(
            events, {"wander": 1.0}, _lead_slot(), ppq=480, rng=random.Random(seed)
        )
        if not out:
            continue
        on = next(e for e in out if isinstance(e, NoteOn))
        if on.note != 60:
            shifted_count += 1
            assert on.note in (48, 72)
            off = next(e for e in out if isinstance(e, NoteOff))
            assert off.note == on.note
    assert shifted_count > 0


# ---------------------------------------------------------- determinism


def test_apply_feel_is_deterministic_with_same_seed() -> None:
    events = _notes((0, 1, 60, 100, 60), (240, 1, 62, 100, 60))
    feel = {"groove": 0.7, "drive": 0.5, "wander": 0.3}
    out1 = apply_feel(events, feel, _lead_slot(), ppq=480, rng=random.Random(42))
    out2 = apply_feel(events, feel, _lead_slot(), ppq=480, rng=random.Random(42))
    assert out1 == out2


def test_apply_feel_humanize_clamps_to_zero() -> None:
    """Negative humanize ticks clamp to 0 rather than going negative."""
    events = _notes((5, 1, 60, 100, 60))
    out = apply_feel(
        events, {"groove": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0)
    )
    on = next(e for e in out if isinstance(e, NoteOn))
    assert on.tick >= 0


# ---------------------------------------------------------- pump is not handled here


def test_pump_in_song_feel_is_no_op_in_feel_pass() -> None:
    """Pump → mix-pass sidechain via compile_global_feel, not the feel pass."""
    events = _notes((0, 1, 60, 100, 60))
    out = apply_feel(
        events, {"pump": 1.0}, _lead_slot(), ppq=480, rng=random.Random(0)
    )
    # No swing, no humanize, no accent, no drive, no mute — pure passthrough.
    assert out == events
