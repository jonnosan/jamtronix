"""Tests for the reese_bass algorithm.

Schema v3: MIDI-naive. Emits :class:`Note` for the held tone and
:class:`Param` for the cutoff wobble + detune modulation.
"""

from __future__ import annotations

import random

from jtx.algorithms import ReeseBass
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


def test_reese_bass_emits_one_note_per_bar() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(_ctx())
    assert len(_notes(events)) == 1


def test_reese_bass_root_default_octave_register_1() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(_ctx(pattern_knobs={"wobble_depth": 0.0, "detune_depth": 0.0}))
    assert _notes(events)[0].pitch == 33  # A1


def test_reese_bass_alternates_root_and_fifth_per_cell() -> None:
    reese = ReeseBass()
    knobs = {"wobble_depth": 0.0, "detune_depth": 0.0, "bars_per_chord": 2}
    pitches = [
        _notes(reese.generate_bar(_ctx(pattern_knobs=knobs, bar_index=b)))[0].pitch
        for b in range(4)
    ]
    assert pitches[0] == pitches[1]
    assert pitches[2] == pitches[3]
    assert pitches[2] - pitches[0] == 7


def test_reese_bass_wobble_emits_cutoff_on_subdivision() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(
        _ctx(pattern_knobs={"wobble_subdiv": "8", "wobble_depth": 1.0, "detune_depth": 0.0})
    )
    assert len(_params(events, "cutoff")) == 8


def test_reese_bass_wobble_triplet_subdivision() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(
        _ctx(pattern_knobs={"wobble_subdiv": "8t", "wobble_depth": 0.8, "detune_depth": 0.0})
    )
    assert len(_params(events, "cutoff")) == 12


def test_reese_bass_wobble_zero_emits_no_cutoff() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(_ctx(pattern_knobs={"wobble_depth": 0.0, "detune_depth": 0.0}))
    assert _params(events, "cutoff") == []


def test_reese_bass_detune_emits_detune_param() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(_ctx(pattern_knobs={"wobble_depth": 0.0, "detune_depth": 0.5}))
    assert _params(events, "detune")


def test_reese_bass_gate_controls_duration() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(_ctx(pattern_knobs={"gate": 0.5, "wobble_depth": 0.0}))
    assert _notes(events)[0].duration_ticks == int(1920 * 0.5)


def test_reese_bass_octave_shift_changes_register() -> None:
    reese = ReeseBass()
    events = reese.generate_bar(
        _ctx(pattern_knobs={"octave": 1, "wobble_depth": 0.0, "detune_depth": 0.0})
    )
    assert _notes(events)[0].pitch == 45  # A2
