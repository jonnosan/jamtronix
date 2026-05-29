"""Texture + motion drive voice activation, algorithm shortlists, filter LFO.

Covers:

* Determinism — same ``(title, mood, fmt, chaos, texture, motion)`` → byte-identical Song.
* Texture monotonicity — sweeping texture across [0, 1] (fixed motion)
  produces a non-decreasing active-voice count.
* Motion monotonicity — sweeping motion across [0, 1] produces a
  non-decreasing filter LFO depth.
* Genre-region sanity — sampling the centre of each known region
  (acid / deep_techno / psytrance from epic #134) produces voice
  activation matching that style's historical palette.
"""

from __future__ import annotations

import dataclasses
import json

from jtx.composer import build_recipe, compose
from jtx.composer.mood import MoodSpec


def _song_json(song) -> str:
    return json.dumps(dataclasses.asdict(song), sort_keys=True)


def _active_voice_count(recipe) -> int:
    return sum(1 for v in recipe.voices.values() if v.algorithm != "rest")


# ---------- determinism -------------------------------------------------


def test_texture_motion_determinism() -> None:
    """Same inputs (incl. texture + motion) → byte-identical Song."""
    args = ("Same", "iac", MoodSpec(valence=-0.2, energy=0.4), "song")
    a = compose(*args, chaos=0.3, texture=0.6, motion=0.7)
    b = compose(*args, chaos=0.3, texture=0.6, motion=0.7)
    assert _song_json(a) == _song_json(b)


def test_texture_motion_clamped() -> None:
    """Out-of-range texture/motion get clamped to [0, 1] silently."""
    args = ("Same", "iac", MoodSpec(valence=0.0, energy=0.0), "song")
    a = compose(*args, chaos=0.0, texture=5.0, motion=-3.0)
    b = compose(*args, chaos=0.0, texture=1.0, motion=0.0)
    assert _song_json(a) == _song_json(b)


# ---------- monotonicity ------------------------------------------------


def test_texture_monotonically_activates_voices() -> None:
    """Sweep texture across [0, 1] at fixed motion: active-voice count
    is non-decreasing across the sweep."""
    mood = MoodSpec(valence=0.0, energy=0.0)
    counts: list[int] = []
    for t in (0.0, 0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0):
        recipe = build_recipe(mood, "song", chaos=0.0, texture=t, motion=0.5)
        counts.append(_active_voice_count(recipe))
    # Non-decreasing across the sweep.
    for prev, cur in zip(counts, counts[1:]):
        assert cur >= prev, counts
    # Texture=0 activates only τ=0 voices (drumkit + bass).
    assert counts[0] == 2, counts
    # Texture=1 activates every palette voice.
    assert counts[-1] == 9, counts


def test_motion_monotonically_deepens_filter_lfo() -> None:
    """Sweep motion across [0, 1]: filter voice's LFO depth is non-decreasing."""
    mood = MoodSpec(valence=0.0, energy=0.0)
    depths: list[float] = []
    for m in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        song = compose(
            "Sweep", "iac", mood, "song", chaos=0.0, texture=0.5, motion=m,
        )
        depths.append(float(song.voices["filter"].pattern["depth"]))
    for prev, cur in zip(depths, depths[1:]):
        assert cur >= prev, depths
    # Low motion = shallow; high motion = near-full sweep.
    assert depths[0] < 0.05
    assert depths[-1] > 0.9


# ---------- genre-region centres (from epic #134 table) ----------------


# Region centres: midpoint of each (low, high) range in the epic table.
_ACID_CENTRE = {
    "mood": MoodSpec(valence=-0.15, energy=0.55),
    "texture": 0.475,
    "motion": 0.725,
}
_DEEP_TECHNO_CENTRE = {
    "mood": MoodSpec(valence=-0.35, energy=0.4),
    "texture": 0.775,
    "motion": 0.25,
}
_PSY_CENTRE = {
    "mood": MoodSpec(valence=-0.25, energy=0.9),
    "texture": 0.425,
    "motion": 0.85,
}


def test_acid_centre_voice_activation() -> None:
    """Acid: bass + lead active, filter swirls hard."""
    song = compose(
        "Acid", "iac", _ACID_CENTRE["mood"], "song", chaos=0.0,
        texture=_ACID_CENTRE["texture"], motion=_ACID_CENTRE["motion"],
    )
    assert song.voices["bass"].algorithm == "acid_bass"
    assert song.voices["lead"].algorithm != "rest"
    # High motion → filter LFO swirls.
    assert float(song.voices["filter"].pattern["depth"]) > 0.6


def test_deep_techno_centre_voice_activation() -> None:
    """Deep techno: sub + pad active, filter barely moves (low motion)."""
    song = compose(
        "Deep", "iac", _DEEP_TECHNO_CENTRE["mood"], "song", chaos=0.0,
        texture=_DEEP_TECHNO_CENTRE["texture"], motion=_DEEP_TECHNO_CENTRE["motion"],
    )
    assert song.voices["sub"].algorithm == "sub_drone"
    assert song.voices["pad"].algorithm == "sustained_chord"
    # Low motion → shallow filter sweep.
    assert float(song.voices["filter"].pattern["depth"]) < 0.4


def test_psy_centre_voice_activation_and_rolling_bass() -> None:
    """Psy: arp active, bass uses LFO cycle knob (rolling acid)."""
    song = compose(
        "Psy", "iac", _PSY_CENTRE["mood"], "song", chaos=0.0,
        texture=_PSY_CENTRE["texture"], motion=_PSY_CENTRE["motion"],
    )
    assert song.voices["arp"].algorithm == "arp"
    # Rolling bass: acid_bass with elevated `cycle` (psy character).
    assert song.voices["bass"].algorithm == "acid_bass"
    assert song.voices["bass"].pattern.get("cycle", 0) >= 3
    # High motion → filter LFO swirls; arp subdivision is fast.
    assert float(song.voices["filter"].pattern["depth"]) > 0.6
    assert song.voices["arp"].pattern["subdivision"] in ("16", "16t")


# ---------- feel knobs derive from texture + motion --------------------


def test_motion_drops_pump_target() -> None:
    """Pump (sidechain) drops as motion rises — psy stays high motion + low pump."""
    mood = MoodSpec(valence=0.0, energy=0.6)
    low = build_recipe(mood, "song", chaos=0.0, texture=0.5, motion=0.0)
    high = build_recipe(mood, "song", chaos=0.0, texture=0.5, motion=1.0)
    # Sample window centre as the feel-target midpoint.
    low_pump = sum(low.mood.feel_targets["pump"]) / 2
    high_pump = sum(high.mood.feel_targets["pump"]) / 2
    assert low_pump > high_pump


def test_motion_raises_drive_target() -> None:
    """Drive rises with motion."""
    mood = MoodSpec(valence=0.0, energy=0.5)
    low = build_recipe(mood, "song", chaos=0.0, texture=0.5, motion=0.0)
    high = build_recipe(mood, "song", chaos=0.0, texture=0.5, motion=1.0)
    low_drive = sum(low.mood.feel_targets["drive"]) / 2
    high_drive = sum(high.mood.feel_targets["drive"]) / 2
    assert high_drive > low_drive
