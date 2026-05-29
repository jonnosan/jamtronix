"""Tests for the four-term reward function.

The reward is the optimizer's only signal — it must be deterministic
across calls (no hidden RNG), responsive to the override layer (a
deliberately bad Tuning must score lower), and shaped so the four
components compose intelligibly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.composer.tuning import Tuning
from jtx.improve.corpus import default_corpus
from jtx.improve.reward import (
    RewardBreakdown,
    RewardWeights,
    compute_reward,
    hard_floor_violation,
)
from jtx.persist.json_io import load_setup

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cheap_corpus():
    """A trimmed corpus so the reward tests finish in a few seconds.

    Keeps the four anchor-scoring sonics + the three mood anchors but
    drops grid + structure cases (they're slow and the reward shape
    tests just need *some* signal in each term).
    """
    from dataclasses import replace
    corpus = default_corpus()
    return replace(
        corpus,
        grid=(),
        structure_cases=corpus.structure_cases[:2],  # 2 formats is enough
        jitter_per_anchor=1,
        sensitivity_steps=3,
    )


@pytest.fixture(scope="module")
def setup(cheap_corpus):
    return load_setup(cheap_corpus.setup_path)


def test_reward_breakdown_shape(cheap_corpus, setup) -> None:
    r = compute_reward(cheap_corpus, Tuning(), setup=setup)
    assert isinstance(r, RewardBreakdown)
    assert 0.0 <= r.A <= 1.0
    assert 0.0 <= r.D <= 1.0
    assert 0.0 <= r.C <= 1.0
    assert 0.0 <= r.S <= 1.0
    # R is a linear combination; verify the formula explicitly.
    w = r.weights
    expected = w.anchor * r.A - w.dead * r.D - w.collapse * r.C - w.struct * r.S
    assert r.R == pytest.approx(expected)


def test_reward_default_tuning_is_deterministic(cheap_corpus, setup) -> None:
    """Two consecutive scoring passes must agree exactly — the optimizer's contract."""
    a = compute_reward(cheap_corpus, Tuning(), setup=setup)
    b = compute_reward(cheap_corpus, Tuning(), setup=setup)
    assert a.R == pytest.approx(b.R)
    assert a.anchor_scores == b.anchor_scores


def test_reward_seven_anchors_scored(cheap_corpus, setup) -> None:
    r = compute_reward(cheap_corpus, Tuning(), setup=setup)
    assert set(r.anchor_scores.keys()) == set(cheap_corpus.anchors.keys())


def test_reward_responds_to_destructive_tuning(cheap_corpus, setup) -> None:
    """Force every voice_tau to 1.0 — every palette voice rests; A drops.

    This is the Phase 2 verification's "should-fail seeded override #1":
    if the reward doesn't penalize a known-bad override, the
    optimization loop has no signal.
    """
    baseline = compute_reward(cheap_corpus, Tuning(), setup=setup)
    destroyed = Tuning(voice_tau={k: 1.0 for k in Tuning().voice_tau})
    poisoned = compute_reward(cheap_corpus, destroyed, setup=setup)
    assert poisoned.A < baseline.A


def test_reward_weights_can_zero_out_terms(cheap_corpus, setup) -> None:
    """Setting a weight to 0 must zero its contribution to R."""
    only_A = RewardWeights(anchor=1.0, dead=0.0, collapse=0.0, struct=0.0)
    r = compute_reward(cheap_corpus, Tuning(), weights=only_A, setup=setup)
    assert r.R == pytest.approx(r.A)


# ---------- hard floor ------------------------------------------------


def _fake_breakdown(scores: dict[str, float], R: float = 0.5) -> RewardBreakdown:
    return RewardBreakdown(
        R=R, A=0.5, D=0.0, C=0.0, S=0.0,
        weights=RewardWeights(),
        anchor_scores=scores,
    )


def test_hard_floor_blocks_single_anchor_regression() -> None:
    best = _fake_breakdown({"acid": 0.8, "sad": 0.7})
    candidate = _fake_breakdown({"acid": 0.6, "sad": 0.7})  # acid drops 0.2
    msg = hard_floor_violation(candidate, best, epsilon=0.05)
    assert msg is not None
    assert "acid" in msg


def test_hard_floor_passes_within_epsilon() -> None:
    best = _fake_breakdown({"acid": 0.8})
    candidate = _fake_breakdown({"acid": 0.77})  # tiny dip, allowed
    assert hard_floor_violation(candidate, best, epsilon=0.05) is None


def test_hard_floor_passes_when_improving() -> None:
    best = _fake_breakdown({"acid": 0.5})
    candidate = _fake_breakdown({"acid": 0.9})
    assert hard_floor_violation(candidate, best, epsilon=0.05) is None
