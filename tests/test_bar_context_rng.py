"""Tests for :class:`BarContext` cyclic-RNG factories.

The factories delegate to :func:`jtx.seed.derive_loop_seed` /
:func:`jtx.seed.derive_hold_seed`; these tests pin the integration —
period / salt routing and the off-sentinel fall-through to ``ctx.rng``.
"""

from __future__ import annotations

import random

from jtx.engine.context import BarContext
from jtx.model.song import Key
from jtx.seed import derive_part_voice_seed, seed_from_title


def _ctx(bar_index: int) -> BarContext:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    return BarContext(
        bar_index=bar_index,
        tick_offset=0,
        ticks_per_bar=1920,
        tempo_bpm=128.0,
        ppq=480,
        key=Key(tonic="C", scale="minor"),
        rng=random.Random(12345),
        part_voice_seed=pv,
    )


def _draw(rng: random.Random, n: int = 8) -> tuple[float, ...]:
    return tuple(rng.random() for _ in range(n))


def test_rng_loop_off_returns_bar_rng() -> None:
    ctx = _ctx(0)
    assert ctx.rng_loop(0) is ctx.rng


def test_rng_hold_off_returns_bar_rng() -> None:
    ctx = _ctx(0)
    assert ctx.rng_hold(0) is ctx.rng


def test_rng_loop_period_4_repeats_every_4_bars() -> None:
    draws_by_bar = {b: _draw(_ctx(b).rng_loop(4)) for b in range(8)}
    assert draws_by_bar[0] == draws_by_bar[4]
    assert draws_by_bar[1] == draws_by_bar[5]
    assert draws_by_bar[2] == draws_by_bar[6]
    assert draws_by_bar[3] == draws_by_bar[7]
    assert draws_by_bar[0] != draws_by_bar[1]
    assert draws_by_bar[0] != draws_by_bar[2]


def test_rng_loop_period_1_makes_every_bar_identical() -> None:
    seq = _draw(_ctx(0).rng_loop(1))
    for b in [1, 2, 5, 17]:
        assert _draw(_ctx(b).rng_loop(1)) == seq


def test_rng_hold_period_4_holds_4_bars_then_changes() -> None:
    epoch0 = _draw(_ctx(0).rng_hold(4))
    for b in [1, 2, 3]:
        assert _draw(_ctx(b).rng_hold(4)) == epoch0
    epoch1 = _draw(_ctx(4).rng_hold(4))
    assert epoch1 != epoch0
    assert _draw(_ctx(5).rng_hold(4)) == epoch1


def test_rng_loop_and_hold_are_distinct_streams() -> None:
    # Same period, same bar — different streams.
    for b in range(4):
        ctx = _ctx(b)
        assert _draw(ctx.rng_loop(4)) != _draw(ctx.rng_hold(4))


def test_salt_separates_streams() -> None:
    ctx = _ctx(0)
    assert _draw(ctx.rng_loop(4, salt="a")) != _draw(ctx.rng_loop(4, salt="b"))
    assert _draw(ctx.rng_hold(4, salt="a")) != _draw(ctx.rng_hold(4, salt="b"))


def test_rng_loop_part_constant_across_bars() -> None:
    seq = _draw(_ctx(0).rng_loop("part"))
    for b in [1, 7, 31]:
        assert _draw(_ctx(b).rng_loop("part")) == seq


def test_rng_hold_part_constant_across_bars() -> None:
    seq = _draw(_ctx(0).rng_hold("part"))
    for b in [1, 7, 31]:
        assert _draw(_ctx(b).rng_hold("part")) == seq


def test_factories_return_fresh_random_per_call() -> None:
    # Repeated calls at the same bar/period give independent Random
    # instances seeded identically (not the same object).
    ctx = _ctx(0)
    a = ctx.rng_loop(4)
    b = ctx.rng_loop(4)
    assert a is not b
    assert _draw(a) == _draw(b)
