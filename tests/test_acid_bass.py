"""Tests for the acid_bass algorithm.

Schema v3: MIDI-naive. Emits :class:`Note` for pitched events and
:class:`Param` for cutoff/resonance/glide/glide_on/bend.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import AcidBass
from jtx.algorithms._theory import note_to_midi
from jtx.engine.context import BarContext
from jtx.model.events import Note, Param
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


def _notes(events) -> list[Note]:
    return [e for e in events if isinstance(e, Note)]


def _params(events, name: str) -> list[Param]:
    return [e for e in events if isinstance(e, Param) and e.name == name]


def test_theory_note_to_midi() -> None:
    assert note_to_midi("C", 4) == 60
    assert note_to_midi("A", 2) == 45
    assert note_to_midi("F#", 3) == 54
    assert note_to_midi("Bb", 4) == 70


def test_theory_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown note name"):
        note_to_midi("H", 4)


def test_acid_bass_drop_prob_one_emits_no_notes() -> None:
    bass = AcidBass()
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 0, "bend": 0}))
    assert _notes(events) == []


def test_acid_bass_drop_prob_zero_fires_every_step() -> None:
    bass = AcidBass()
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0}))
    assert len(_notes(events)) == 16


def test_acid_bass_pitch_uses_key_tonic() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "octave": 0})
    )
    assert all(n.pitch in {45, 48, 57} for n in _notes(events))


def test_acid_bass_octave_knob_shifts_register() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "octave": 1})
    )
    assert all(n.pitch in {57, 60, 69} for n in _notes(events))


def test_acid_bass_chord_root_semitones_transposes_root() -> None:
    bass = AcidBass()
    ctx = _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0})
    ctx.chord_root_semitones = 5
    events = bass.generate_bar(ctx)
    assert all(n.pitch in {50, 53, 62} for n in _notes(events))


def test_acid_bass_cycle_zero_disables_cutoff_lfo() -> None:
    bass = AcidBass()
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 0, "bend": 0}))
    assert _params(events, "cutoff") == []
    assert _params(events, "resonance") == []


def test_acid_bass_cycle_emits_cutoff_and_resonance() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 2, "resonance": 100, "bend": 0})
    )
    cutoffs = _params(events, "cutoff")
    resonances = _params(events, "resonance")
    assert len(cutoffs) == 4
    assert len(resonances) == 4
    assert all(0.0 <= p.value <= 1.0 for p in cutoffs)


def test_acid_bass_cycle_phase_continuous_across_bars() -> None:
    bass = AcidBass()
    bar0 = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 4, "resonance": 0, "bend": 0}, bar_index=0)
    )
    bar1 = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 4, "resonance": 0, "bend": 0}, bar_index=1)
    )
    c0 = _params(bar0, "cutoff")
    c1 = _params(bar1, "cutoff")
    assert len(c0) == 4 and len(c1) == 4
    # Last of bar 0 and first of bar 1 are consecutive on the same LFO.
    assert abs(c0[-1].value - c1[0].value) <= 15 / 127.0


def test_acid_bass_resonance_zero_disables_resonance_param() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 1.0, "cycle": 2, "resonance": 0, "bend": 0})
    )
    assert _params(events, "resonance") == []


def test_acid_bass_bend_emits_pitch_wobble_around_each_note() -> None:
    bass = AcidBass()
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 80}))

    notes = sorted(_notes(events), key=lambda n: n.tick)
    bends = _params(events, "bend")
    # One bend before each note + one zero-recentre after.
    assert len(bends) == len(notes) * 2
    note_off_ticks = {n.tick + n.duration_ticks for n in notes}
    recentres = [p for p in bends if p.tick in note_off_ticks]
    assert len(recentres) == len(notes)
    assert all(p.value == 0.0 for p in recentres)
    wobbles = [p for p in bends if p.tick not in note_off_ticks]
    # Normalised ±1 — bend in {-80..80} / 8192.
    assert all(-1.0 <= p.value <= 1.0 for p in wobbles)


def test_acid_bass_bend_zero_emits_no_bend_param() -> None:
    bass = AcidBass()
    events = bass.generate_bar(_ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0}))
    assert _params(events, "bend") == []


def test_acid_bass_gate_knob_controls_duration() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "gate": 0.5})
    )
    step = 120
    for n in _notes(events):
        assert n.duration_ticks == int(step * 0.5)


def test_acid_bass_slide_emits_portamento_latch_on_bar_zero() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(
            pattern_knobs={"slide_prob": 0.5, "drop_prob": 0.0, "cycle": 0, "bend": 0}, bar_index=0
        )
    )
    glide_on = [p for p in events if isinstance(p, Param) and p.name == "glide_on" and p.tick == 0]
    glide = [p for p in events if isinstance(p, Param) and p.name == "glide" and p.tick == 0]
    assert len(glide_on) == 1
    assert glide_on[0].value == pytest.approx(1.0)
    assert len(glide) >= 1


def test_acid_bass_slide_no_latch_on_later_bars() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(
            pattern_knobs={"slide_prob": 0.5, "drop_prob": 0.0, "cycle": 0, "bend": 0}, bar_index=3
        )
    )
    assert not any(isinstance(e, Param) and e.name == "glide_on" for e in events)


def test_acid_bass_accent_pattern_on_downbeats() -> None:
    bass = AcidBass()
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
    notes = sorted(_notes(events), key=lambda n: n.tick)
    accents = [n for n in notes if n.tick in (0, 480, 960, 1440)]
    others = [n for n in notes if n.tick not in (0, 480, 960, 1440)]
    avg_accent = sum(n.velocity for n in accents) / len(accents)
    avg_other = sum(n.velocity for n in others) / len(others)
    assert avg_accent > avg_other + 8


def test_acid_bass_is_deterministic_for_same_seed() -> None:
    e1 = AcidBass().generate_bar(_ctx(seed=42))
    e2 = AcidBass().generate_bar(_ctx(seed=42))
    assert e1 == e2


def test_acid_bass_differs_for_different_seeds() -> None:
    e1 = AcidBass().generate_bar(_ctx(seed=1))
    e2 = AcidBass().generate_bar(_ctx(seed=2))
    assert e1 != e2


def test_acid_bass_triplet_prob_one_replaces_every_beat() -> None:
    bass = AcidBass()
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
    notes = sorted(_notes(events), key=lambda n: n.tick)
    assert len(notes) == 12
    expected_ticks = []
    for beat in range(4):
        for i in range(3):
            expected_ticks.append(beat * 480 + i * 80)
    assert [n.tick for n in notes] == expected_ticks


def test_acid_bass_triplet_prob_zero_keeps_pattern_on_16ths() -> None:
    bass = AcidBass()
    events = bass.generate_bar(
        _ctx(pattern_knobs={"drop_prob": 0.0, "cycle": 0, "bend": 0, "triplet_prob": 0.0})
    )
    notes = _notes(events)
    assert len(notes) == 16
    assert all(n.tick % 120 == 0 for n in notes)
