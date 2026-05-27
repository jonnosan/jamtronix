"""Tests for the acid_bass algorithm."""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import AcidBass
from jtx.algorithms._theory import note_to_midi
from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, NoteOff, NoteOn, PitchBend
from jtx.model.song import Key


def _ctx(
    *,
    pattern_knobs: dict[str, object] | None = None,
    bar_index: int = 0,
    seed: int = 0,
) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,
        tempo_bpm=124.0,
        ppq=480,
        key=Key(tonic="A", scale="minor"),
        pattern_knobs=pattern_knobs or {},
        rng=random.Random(seed),
    )


def test_theory_note_to_midi() -> None:
    assert note_to_midi("C", 4) == 60
    assert note_to_midi("A", 2) == 45
    assert note_to_midi("F#", 3) == 54
    assert note_to_midi("Bb", 4) == 70


def test_theory_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown note name"):
        note_to_midi("H", 4)


def test_acid_bass_drop_prob_one_emits_no_notes() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 0, "bend": 0}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert note_ons == []


def test_acid_bass_drop_prob_zero_fires_every_step() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0}))
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert len(note_ons) == 16


def test_acid_bass_pitch_uses_key_tonic() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "octave": 0})
    )
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # Tonic A at octave 2 = MIDI 45; with chord_root_semitones=0.
    # Root / minor-third / octave possibilities → MIDI 45, 48, or 57.
    assert all(e.note in {45, 48, 57} for e in note_ons)


def test_acid_bass_octave_knob_shifts_register() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "octave": 1})
    )
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # octave=+1 → register-3 → A3 = 57, +3 = 60, +12 = 69.
    assert all(e.note in {57, 60, 69} for e in note_ons)


def test_acid_bass_chord_root_semitones_transposes_root() -> None:
    bass = AcidBass(midi_channel=2)
    ctx = _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0})
    ctx.chord_root_semitones = 5  # IV in minor (D from A): A2 + 5 = D3 = 50.
    events = bass.generate_bar(ctx)
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # Pitches: 50 (root), 53 (minor 3rd above 50), 62 (octave).
    assert all(e.note in {50, 53, 62} for e in note_ons)


def test_acid_bass_cycle_zero_disables_cc_lfo() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 0, "bend": 0}))
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert ccs == []


def test_acid_bass_cycle_emits_cc74_and_cc71() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 2, "resonance": 100, "bend": 0})
    )
    ccs = [e for e in events if isinstance(e, ControlChange)]
    cc74 = [c for c in ccs if c.cc == 74]
    cc71 = [c for c in ccs if c.cc == 71]
    # 4 quarter notes per bar → 4 of each CC type.
    assert len(cc74) == 4
    assert len(cc71) == 4
    # CC74 values in the documented sweep range (30..110 nominally).
    assert all(0 <= c.value <= 127 for c in cc74)


def test_acid_bass_cycle_phase_continuous_across_bars() -> None:
    """The CC74 value at the end of bar 0 should equal the value at
    the start of bar 1 — that's what continuous-phase means."""
    bass = AcidBass(midi_channel=2)
    bar0 = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 4, "resonance": 0, "bend": 0}, bar_index=0)
    )
    bar1 = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 4, "resonance": 0, "bend": 0}, bar_index=1)
    )
    cc74_bar0 = [c for c in bar0 if isinstance(c, ControlChange) and c.cc == 74]
    cc74_bar1 = [c for c in bar1 if isinstance(c, ControlChange) and c.cc == 74]
    assert len(cc74_bar0) == 4 and len(cc74_bar1) == 4
    # Sine ramps up smoothly — last sample of bar 0 and first of bar 1
    # should be close (consecutive quarter notes on the same LFO).
    assert abs(cc74_bar0[-1].value - cc74_bar1[0].value) <= 15


def test_acid_bass_resonance_zero_disables_cc71() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 2, "resonance": 0, "bend": 0})
    )
    ccs = [e for e in events if isinstance(e, ControlChange)]
    assert all(c.cc != 71 for c in ccs)


def test_acid_bass_bend_emits_pitch_wobble_around_each_note() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 80}))

    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    note_offs = sorted((e for e in events if isinstance(e, NoteOff)), key=lambda e: e.tick)
    pbs = [e for e in events if isinstance(e, PitchBend)]
    # One pitch-bend before each note + one zero-recentre after.
    assert len(pbs) == len(note_ons) * 2
    # Recentres land exactly at each NoteOff tick.
    off_ticks = {off.tick for off in note_offs}
    recentres = [p for p in pbs if p.tick in off_ticks]
    assert len(recentres) == len(note_ons)
    assert all(p.value == 0 for p in recentres)
    wobbles = [p for p in pbs if p.tick not in off_ticks]
    assert all(-80 <= p.value <= 80 for p in wobbles)


def test_acid_bass_bend_zero_emits_no_pitchwheel() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0}))
    assert not any(isinstance(e, PitchBend) for e in events)


def test_acid_bass_gate_knob_controls_note_off_offset() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "gate": 0.5})
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    note_offs = sorted((e for e in events if isinstance(e, NoteOff)), key=lambda e: e.tick)
    step = 120
    for on, off in zip(note_ons, note_offs, strict=True):
        assert off.tick - on.tick == int(step * 0.5)


def test_acid_bass_slide_emits_portamento_latch_on_bar_zero() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(
            pattern_knobs={"slide_prob": 0.5, "drop_prob": 0.0, "cycle": 0, "bend": 0}, bar_index=0
        )
    )
    # CC 65 = 127 (portamento on) + CC 5 = 0 (default time) at tick 0.
    ccs = [e for e in events if isinstance(e, ControlChange) and e.tick == 0]
    cc65 = [c for c in ccs if c.cc == 65]
    cc5_at_zero = [c for c in ccs if c.cc == 5]
    assert len(cc65) == 1 and cc65[0].value == 127
    assert len(cc5_at_zero) >= 1


def test_acid_bass_slide_no_latch_on_later_bars() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(
            pattern_knobs={"slide_prob": 0.5, "drop_prob": 0.0, "cycle": 0, "bend": 0}, bar_index=3
        )
    )
    # No CC 65 on bar 3 — the latch happened at bar 0.
    assert not any(isinstance(e, ControlChange) and e.cc == 65 for e in events)


def test_acid_bass_accent_pattern_on_downbeats() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(
            pattern_knobs={
                "drop_prob": 0.0,
                "cycle": 0,
                "bend": 0,
                "base_vel": 80,
                "intensity": 1.0,
            }
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # Steps 0, 4, 8, 12 (= 120-tick × 0, 4, 8, 12) get +15 velocity boost.
    accents = [e for e in note_ons if e.tick in (0, 480, 960, 1440)]
    others = [e for e in note_ons if e.tick not in (0, 480, 960, 1440)]
    avg_accent = sum(e.velocity for e in accents) / len(accents)
    avg_other = sum(e.velocity for e in others) / len(others)
    # Accent average should be clearly above off-beat average.
    assert avg_accent > avg_other + 8


def test_acid_bass_is_deterministic_for_same_seed() -> None:
    bass1 = AcidBass(midi_channel=2)
    bass2 = AcidBass(midi_channel=2)
    e1 = bass1.generate_bar(_ctx(seed=42))
    e2 = bass2.generate_bar(_ctx(seed=42))
    assert e1 == e2


def test_acid_bass_differs_for_different_seeds() -> None:
    bass = AcidBass(midi_channel=2)
    e1 = bass.generate_bar(_ctx(seed=1))
    e2 = bass.generate_bar(_ctx(seed=2))
    # Different seeds → different step choices and pitch picks.
    assert e1 != e2


def test_acid_bass_triplet_prob_one_replaces_every_beat() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(
            pattern_knobs={
                "drop_prob": 0.0,
                "cycle": 0,
                "bend": 0,
                "triplet_prob": 1.0,
                "triplet_subdiv": "16t",
            }
        )
    )
    note_ons = sorted((e for e in events if isinstance(e, NoteOn)), key=lambda e: e.tick)
    # Every beat replaced: 4 beats × 3 triplet positions = 12 notes.
    assert len(note_ons) == 12
    # Triplet positions: 0, 80, 160; 480, 560, 640; 960, 1040, 1120; 1440, 1520, 1600.
    expected_ticks = []
    for beat in range(4):
        for i in range(3):
            expected_ticks.append(beat * 480 + i * 80)
    assert [e.tick for e in note_ons] == expected_ticks


def test_acid_bass_triplet_prob_zero_keeps_pattern_on_16ths() -> None:
    bass = AcidBass(midi_channel=2)
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "triplet_prob": 0.0})
    )
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    # No triplet rolls → standard 16 16ths.
    assert len(note_ons) == 16
    # No off-grid ticks (every tick divisible by step_ticks=120).
    assert all(e.tick % 120 == 0 for e in note_ons)
