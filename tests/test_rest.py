"""Tests for the rest algorithm — voice-level explicit silence."""

from __future__ import annotations

import random

from jtx.algorithms import Rest
from jtx.engine.context import BarContext
from jtx.model.song import Key


def _ctx(*, bar_index: int = 0, intensity: float = 0.6) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,
        tempo_bpm=125,
        ppq=480,
        key=Key("A", "minor"),
        rng=random.Random(bar_index),
        pattern_knobs={},
        part_intensity=intensity,
        part_progress=0.5,
        song_feel={},
    )


def test_rest_returns_empty_list_at_bar_0() -> None:
    assert Rest().generate_bar(_ctx(bar_index=0)) == []


def test_rest_returns_empty_list_at_arbitrary_bar() -> None:
    rest = Rest()
    for bar in (1, 7, 17, 64, 128):
        assert rest.generate_bar(_ctx(bar_index=bar)) == []


def test_rest_ignores_intensity_and_song_feel() -> None:
    """Rest emits nothing regardless of part_intensity or song_feel."""
    rest = Rest()
    ctx_low = _ctx(intensity=0.0)
    ctx_high = _ctx(intensity=1.0)
    assert rest.generate_bar(ctx_low) == []
    assert rest.generate_bar(ctx_high) == []


def test_rest_default_param_map_is_empty() -> None:
    """Rest has no parameter routing — it emits no Params either."""
    assert Rest.DEFAULT_PARAM_MAP == {}


def test_rest_instantiable_via_player() -> None:
    """The player's instantiate_algorithm switch wires 'rest' to Rest."""
    from jtx.model.setup import VoiceSlot
    from jtx.player import instantiate_algorithm

    slot = VoiceSlot(
        name="anything",
        type="mono",
        default_role="bass",
        midi_channel=1,
    )
    algo = instantiate_algorithm("rest", slot)
    assert isinstance(algo, Rest)
    assert algo.generate_bar(_ctx()) == []
