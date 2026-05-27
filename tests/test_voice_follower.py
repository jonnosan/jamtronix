"""Tests for the voice_follower fixed pipeline."""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import VoiceFollower
from jtx.engine.context import BarContext
from jtx.engine.events import Event, NoteOff, NoteOn
from jtx.model.song import Key


def _ctx(
    *,
    pattern_knobs: dict[str, object] | None = None,
    source_events: list[Event] | None = None,
    prev_source_events: list[Event] | None = None,
    seed: int = 0,
) -> BarContext:
    return BarContext(
        bar_index=0,
        tick_offset=0,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(seed),
        source_events=source_events,
        prev_source_events=prev_source_events,
    )


def _source_notes(*specs: tuple[int, int, int, int]) -> list[Event]:
    """Build a list of NoteOn/NoteOff events from (tick, pitch, vel, dur) specs."""
    events: list[Event] = []
    for tick, pitch, vel, dur in specs:
        events.append(NoteOn(tick=tick, channel=1, note=pitch, velocity=vel))
        events.append(NoteOff(tick=tick + dur, channel=1, note=pitch))
    return events


def _extract_notes(events: list[Event]) -> list[tuple[int, int, int]]:
    """Helper: return (tick, note, velocity) for each NoteOn."""
    return [(e.tick, e.note, e.velocity) for e in events if isinstance(e, NoteOn)]


# ------------------------------------------------------------ basics


def test_follower_with_no_source_emits_nothing() -> None:
    follower = VoiceFollower(midi_channel=5)
    assert follower.generate_bar(_ctx(source_events=None)) == []
    assert follower.generate_bar(_ctx(source_events=[])) == []


def test_follower_passthrough_with_defaults() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120), (480, 64, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src))
    assert _extract_notes(events) == [(0, 60, 100), (480, 64, 100)]
    # Output channel is the follower's, not the source's.
    assert all(isinstance(e, NoteOn | NoteOff) and e.channel == 5 for e in events)


# ------------------------------------------------------------ latch


def test_follower_latch_first_per_bar() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120), (480, 64, 100, 120), (960, 67, 100, 120))
    events = follower.generate_bar(
        _ctx(source_events=src, pattern_knobs={"latch": "first_per_bar"})
    )
    assert _extract_notes(events) == [(0, 60, 100)]


def test_follower_latch_every_nth() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes(
        (0, 60, 100, 60), (120, 62, 100, 60), (240, 64, 100, 60), (360, 65, 100, 60)
    )
    events = follower.generate_bar(
        _ctx(source_events=src, pattern_knobs={"latch": "every_nth", "every_nth": 2})
    )
    assert _extract_notes(events) == [(0, 60, 100), (240, 64, 100)]


def test_follower_latch_accent_only() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 110, 120), (120, 62, 80, 120), (240, 64, 105, 120))
    events = follower.generate_bar(
        _ctx(
            source_events=src,
            pattern_knobs={"latch": "accent_only", "accent_threshold": 100},
        )
    )
    notes = _extract_notes(events)
    assert (0, 60, 110) in notes
    assert (240, 64, 105) in notes
    assert all(n[2] >= 100 for n in notes)


def test_follower_latch_unknown_raises() -> None:
    follower = VoiceFollower(midi_channel=5)
    with pytest.raises(ValueError, match="unknown latch"):
        follower.generate_bar(
            _ctx(source_events=_source_notes((0, 60, 100, 120)), pattern_knobs={"latch": "bogus"})
        )


# -------------------------------------------------- pattern_transform


def test_follower_transform_invert_mirrors_around_axis() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120), (240, 67, 100, 120))
    events = follower.generate_bar(
        _ctx(source_events=src, pattern_knobs={"transform": "invert", "invert_axis": 60})
    )
    notes = _extract_notes(events)
    assert [n[1] for n in notes] == [60, 53]  # 60 → 60, 67 → 53 (= 60 - 7)


def test_follower_transform_retrograde_reverses_in_bar() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120), (960, 64, 100, 120))
    events = follower.generate_bar(
        _ctx(source_events=src, pattern_knobs={"transform": "retrograde"})
    )
    notes = sorted(_extract_notes(events))
    # Original ticks 0, 960 in a 1920-bar reverse to 840, 1800.
    assert [n[0] for n in notes] == [840, 1800]
    # Pitch ordering inverts.
    assert [n[1] for n in notes] == [64, 60]


def test_follower_transform_thin_drops_some_notes() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes(*[(i * 120, 60 + i, 100, 60) for i in range(16)])
    events = follower.generate_bar(
        _ctx(
            source_events=src,
            pattern_knobs={"transform": "thin", "thin_prob": 1.0},
            seed=0,
        )
    )
    # thin_prob=1.0 → all dropped.
    assert _extract_notes(events) == []


def test_follower_transform_unknown_raises() -> None:
    follower = VoiceFollower(midi_channel=5)
    with pytest.raises(ValueError, match="unknown transform"):
        follower.generate_bar(
            _ctx(
                source_events=_source_notes((0, 60, 100, 120)),
                pattern_knobs={"transform": "bogus"},
            )
        )


# ------------------------------------------------------------ transpose


def test_follower_transpose_semitones() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120))
    events = follower.generate_bar(
        _ctx(source_events=src, pattern_knobs={"transpose_semitones": 5})
    )
    assert _extract_notes(events) == [(0, 65, 100)]


def test_follower_transpose_octaves() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"transpose_octaves": 1}))
    assert _extract_notes(events) == [(0, 72, 100)]


# ------------------------------------------------------------- chord


def test_follower_chord_emits_one_note_per_interval() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"chord": [0, 4, 7]}))
    pitches = sorted(e.note for e in events if isinstance(e, NoteOn))
    assert pitches == [60, 64, 67]


def test_follower_chord_default_zero_no_change() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"chord": [0]}))
    assert _extract_notes(events) == [(0, 60, 100)]


# --------------------------------------------------------- quantize


def test_follower_quantize_nearest_snaps_to_scale() -> None:
    follower = VoiceFollower(midi_channel=5)
    # A natural minor pcs: {9, 11, 0, 2, 4, 5, 7} = A B C D E F G.
    # MIDI 73 (C#, pc=1) is NOT in A minor. Nearest scale: 72 (C, pc=0)
    # or 74 (D, pc=2). Both 1 semitone away.
    src = _source_notes((0, 73, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"quantize": "nearest"}))
    note = next(e for e in events if isinstance(e, NoteOn))
    assert note.note in (72, 74)


def test_follower_quantize_up_snaps_upward() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 73, 100, 120))  # C# — out of A minor.
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"quantize": "up"}))
    note = next(e for e in events if isinstance(e, NoteOn))
    assert note.note == 74  # D, pc 2 — first scale member going up.


def test_follower_quantize_down_snaps_downward() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 73, 100, 120))  # C#
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"quantize": "down"}))
    note = next(e for e in events if isinstance(e, NoteOn))
    assert note.note == 72  # C, pc 0.


def test_follower_quantize_off_passes_through() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 73, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"quantize": "off"}))
    note = next(e for e in events if isinstance(e, NoteOn))
    assert note.note == 73


def test_follower_quantize_scale_override() -> None:
    follower = VoiceFollower(midi_channel=5)
    # In A major (pcs {9, 11, 1, 2, 4, 6, 8}), MIDI 73 (C#, pc 1) IS in scale.
    src = _source_notes((0, 73, 100, 120))
    events = follower.generate_bar(
        _ctx(
            source_events=src,
            pattern_knobs={"quantize": "nearest", "quantize_scale": "major"},
        )
    )
    note = next(e for e in events if isinstance(e, NoteOn))
    assert note.note == 73  # already in A major, no change.


# ---------------------------------------------------------- ratchet


def test_follower_ratchet_one_no_change() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"ratchet": 1}))
    assert _extract_notes(events) == [(0, 60, 100)]


def test_follower_ratchet_four_emits_four_evenly_spaced() -> None:
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes((0, 60, 100, 120))
    events = follower.generate_bar(_ctx(source_events=src, pattern_knobs={"ratchet": 4}))
    ticks = sorted(e.tick for e in events if isinstance(e, NoteOn))
    # 4 retriggers over 120-tick duration → 30-tick spacing.
    assert ticks == [0, 30, 60, 90]


# ---------------------------------------------------------- combos


# ---------------------------------------------------------- shift_bars


def test_follower_shift_one_uses_prev_bar_source() -> None:
    """``shift_bars=1`` echoes the previous bar's source into this bar."""
    follower = VoiceFollower(midi_channel=5)
    curr = _source_notes((0, 60, 100, 60), (480, 64, 100, 60))
    prev = _source_notes((0, 67, 100, 60), (960, 72, 100, 60))
    events = follower.generate_bar(
        _ctx(
            source_events=curr,
            prev_source_events=prev,
            pattern_knobs={"shift_bars": 1},
        )
    )
    # Output should mirror PREV (67, 72), not CURR (60, 64).
    assert _extract_notes(events) == [(0, 67, 100), (960, 72, 100)]


def test_follower_shift_one_with_no_prev_emits_nothing() -> None:
    """First bar of a part with shift_bars=1 is silent."""
    follower = VoiceFollower(midi_channel=5)
    curr = _source_notes((0, 60, 100, 60))
    assert (
        follower.generate_bar(
            _ctx(
                source_events=curr,
                prev_source_events=None,
                pattern_knobs={"shift_bars": 1},
            )
        )
        == []
    )


def test_follower_shift_zero_is_default_behaviour() -> None:
    """Explicit shift_bars=0 reads current-bar source like the default."""
    follower = VoiceFollower(midi_channel=5)
    curr = _source_notes((240, 65, 100, 60))
    prev = _source_notes((0, 99, 100, 60))
    events = follower.generate_bar(
        _ctx(
            source_events=curr,
            prev_source_events=prev,
            pattern_knobs={"shift_bars": 0},
        )
    )
    assert _extract_notes(events) == [(240, 65, 100)]


def test_follower_shift_greater_than_one_returns_empty() -> None:
    """v1 only caches one bar; deeper shifts return nothing."""
    follower = VoiceFollower(midi_channel=5)
    curr = _source_notes((0, 60, 100, 60))
    prev = _source_notes((0, 64, 100, 60))
    assert (
        follower.generate_bar(
            _ctx(
                source_events=curr,
                prev_source_events=prev,
                pattern_knobs={"shift_bars": 2},
            )
        )
        == []
    )


def test_follower_shift_negative_raises() -> None:
    import pytest

    follower = VoiceFollower(midi_channel=5)
    curr = _source_notes((0, 60, 100, 60))
    with pytest.raises(ValueError, match="shift_bars"):
        follower.generate_bar(_ctx(source_events=curr, pattern_knobs={"shift_bars": -1}))


def test_follower_shift_composes_with_pipeline_steps() -> None:
    """Shifted source still goes through latch/transpose/chord/etc."""
    follower = VoiceFollower(midi_channel=5)
    prev = _source_notes((0, 60, 100, 60), (480, 62, 100, 60), (960, 64, 100, 60))
    events = follower.generate_bar(
        _ctx(
            source_events=_source_notes((0, 99, 100, 60)),  # ignored
            prev_source_events=prev,
            pattern_knobs={
                "shift_bars": 1,
                "latch": "first_per_bar",
                "transpose_octaves": 1,
            },
        )
    )
    # first_per_bar of prev → pitch 60, +12 octave → 72.
    assert _extract_notes(events) == [(0, 72, 100)]


# ---------------------------------------------------------- combos


def test_follower_full_pipeline_composes_correctly() -> None:
    """Latch first → transpose +12 → chord [0,4,7] → ratchet 2."""
    follower = VoiceFollower(midi_channel=5)
    src = _source_notes(
        (0, 60, 100, 120),
        (240, 64, 100, 120),
        (480, 67, 100, 120),
    )
    events = follower.generate_bar(
        _ctx(
            source_events=src,
            pattern_knobs={
                "latch": "first_per_bar",
                "transpose_octaves": 1,
                "chord": [0, 4, 7],
                "ratchet": 2,
            },
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: (e.tick, e.note))
    # first_per_bar → only source[0] survives.
    # +1 octave → pitch 72.
    # chord [0,4,7] → pitches 72, 76, 79.
    # ratchet=2 → each at tick 0 + tick 60.
    pitches_by_tick: dict[int, list[int]] = {}
    for n in note_ons:
        pitches_by_tick.setdefault(n.tick, []).append(n.note)
    assert sorted(pitches_by_tick) == [0, 60]
    assert sorted(pitches_by_tick[0]) == [72, 76, 79]
    assert sorted(pitches_by_tick[60]) == [72, 76, 79]
