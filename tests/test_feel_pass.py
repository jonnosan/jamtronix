"""Tests for the feel post-emit pass."""

from __future__ import annotations

import random

from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn
from jtx.engine.feel import apply_feel


def _notes(*specs: tuple[int, int, int, int, int]) -> list[Event]:
    """Build NoteOn/NoteOff pairs from (tick, channel, note, vel, dur) specs."""
    out: list[Event] = []
    for tick, ch, note, vel, dur in specs:
        out.append(NoteOn(tick=tick, channel=ch, note=note, velocity=vel))
        out.append(NoteOff(tick=tick + dur, channel=ch, note=note))
    return out


def test_apply_feel_empty_knobs_is_identity() -> None:
    events = _notes((0, 1, 60, 100, 120), (480, 1, 64, 100, 120))
    out = apply_feel(events, {}, ppq=480, rng=random.Random(0))
    assert out == events


def test_apply_feel_mute_prob_one_drops_everything() -> None:
    events = _notes((0, 1, 60, 100, 120))
    out = apply_feel(events, {"mute_prob": 1.0}, ppq=480, rng=random.Random(0))
    assert out == []


def test_apply_feel_swing_delays_odd_steps() -> None:
    # Notes on steps 0, 1, 2, 3 (= ticks 0, 120, 240, 360 at PPQ 480).
    events = _notes(
        (0, 1, 60, 100, 60),
        (120, 1, 62, 100, 60),
        (240, 1, 64, 100, 60),
        (360, 1, 65, 100, 60),
    )
    out = apply_feel(events, {"swing": 1.0}, ppq=480, rng=random.Random(0))
    on_ticks = sorted(e.tick for e in out if isinstance(e, NoteOn))
    # swing=1.0 → odd 16ths land on the triplet position (2/3 of the
    # containing 8th). At PPQ=480, step_ticks=120, max shift = 40.
    # Steps 0 + 2 stay; steps 1 + 3 shift by +40.
    assert on_ticks == [0, 160, 240, 400]


def test_apply_feel_swing_half_lands_between_straight_and_triplet() -> None:
    events = _notes(
        (0, 1, 60, 100, 60),
        (120, 1, 62, 100, 60),
    )
    out = apply_feel(events, {"swing": 0.5}, ppq=480, rng=random.Random(0))
    on_ticks = sorted(e.tick for e in out if isinstance(e, NoteOn))
    # swing=0.5 → shift = step_ticks * 0.5 / 3 ≈ 20.
    assert on_ticks == [0, 140]


def test_apply_feel_vel_jitter_keeps_velocity_in_range() -> None:
    events = _notes((0, 1, 60, 100, 60))
    out = apply_feel(events, {"vel_jitter": 30}, ppq=480, rng=random.Random(0))
    on = next(e for e in out if isinstance(e, NoteOn))
    assert 70 <= on.velocity <= 127  # 100 ± 30, clamped
    assert on.velocity != 100  # almost certainly perturbed


def test_apply_feel_accent_boosts_configured_beats() -> None:
    # Steps 0 and 8 are the default accent beats.
    events = _notes(
        (0, 1, 60, 90, 60),  # step 0 — accented
        (120, 1, 60, 90, 60),  # step 1 — not
        (960, 1, 60, 90, 60),  # step 8 — accented
    )
    out = apply_feel(events, {"accent": 15}, ppq=480, rng=random.Random(0))
    ons = sorted((e for e in out if isinstance(e, NoteOn)), key=lambda e: e.tick)
    assert ons[0].velocity == 105
    assert ons[1].velocity == 90
    assert ons[2].velocity == 105


def test_apply_feel_accent_beats_knob_overrides_default() -> None:
    events = _notes((0, 1, 60, 90, 60), (120, 1, 60, 90, 60))
    out = apply_feel(events, {"accent": 20, "accent_beats": [1]}, ppq=480, rng=random.Random(0))
    ons = sorted((e for e in out if isinstance(e, NoteOn)), key=lambda e: e.tick)
    assert ons[0].velocity == 90
    assert ons[1].velocity == 110


def test_apply_feel_humanize_jitters_ticks() -> None:
    events = _notes((480, 1, 60, 100, 60))
    out = apply_feel(events, {"humanize": 20}, ppq=480, rng=random.Random(0))
    on = next(e for e in out if isinstance(e, NoteOn))
    assert 460 <= on.tick <= 500
    # The matching NoteOff also receives independent humanize jitter.
    off = next(e for e in out if isinstance(e, NoteOff))
    assert 520 <= off.tick <= 560


def test_apply_feel_octave_jump_can_shift_a_note() -> None:
    # With probability 1, every note jumps by ±12 (clamped to MIDI range).
    events = _notes((0, 1, 60, 100, 60))
    out = apply_feel(events, {"octave_jump": 1.0}, ppq=480, rng=random.Random(0))
    on = next(e for e in out if isinstance(e, NoteOn))
    off = next(e for e in out if isinstance(e, NoteOff))
    assert on.note in (48, 72)
    # Note-off should follow the same shift so the synth gets a matching off.
    assert off.note == on.note


def test_apply_feel_passes_control_change_through() -> None:
    events: list[Event] = [
        ControlChange(tick=0, channel=2, cc=74, value=64),
    ]
    out = apply_feel(events, {"humanize": 5}, ppq=480, rng=random.Random(0))
    assert len(out) == 1
    cc = out[0]
    assert isinstance(cc, ControlChange)
    assert cc.cc == 74 and cc.value == 64


def test_apply_feel_is_deterministic_with_same_seed() -> None:
    events = _notes((0, 1, 60, 100, 60), (240, 1, 62, 100, 60))
    out1 = apply_feel(events, {"humanize": 10, "vel_jitter": 10}, ppq=480, rng=random.Random(42))
    out2 = apply_feel(events, {"humanize": 10, "vel_jitter": 10}, ppq=480, rng=random.Random(42))
    assert out1 == out2


def test_apply_feel_negative_humanize_clamps_to_zero() -> None:
    # Note at tick 5 with humanize 20 might go negative → clamp at 0.
    events = _notes((5, 1, 60, 100, 60))
    out = apply_feel(events, {"humanize": 20}, ppq=480, rng=random.Random(0))
    on = next(e for e in out if isinstance(e, NoteOn))
    assert on.tick >= 0
