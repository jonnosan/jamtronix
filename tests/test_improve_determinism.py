"""Tests for the determinism guard.

The Phase 2 plan: "Determinism check at loop start: render and score
the corpus with current head twice. If scores differ, the loop refuses
to run." This module's contract is that the guard *catches*
non-determinism, not just that it returns identical values when
nothing is wrong.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from jtx.composer.tuning import Tuning
from jtx.improve.corpus import default_corpus
from jtx.improve.determinism import NonDeterministicReward, assert_deterministic
from jtx.improve.reward import RewardBreakdown
from jtx.persist.json_io import load_setup

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cheap_corpus():
    """Minimal corpus so the determinism check stays cheap in CI."""
    corpus = default_corpus()
    return replace(
        corpus,
        grid=(),
        structure_cases=(),
        jitter_per_anchor=1,
        sensitivity_steps=2,
    )


@pytest.fixture(scope="module")
def setup(cheap_corpus):
    return load_setup(cheap_corpus.setup_path)


def test_default_tuning_is_deterministic(cheap_corpus, setup) -> None:
    """The reward over default Tuning must reproduce exactly twice in a row."""
    breakdown = assert_deterministic(
        cheap_corpus, Tuning(), setup=setup, quick=True
    )
    assert isinstance(breakdown, RewardBreakdown)


def test_quick_mode_uses_smaller_subcorpus(cheap_corpus, setup) -> None:
    """quick=True should still produce a valid breakdown."""
    r = assert_deterministic(cheap_corpus, Tuning(), setup=setup, quick=True)
    # Sub-corpus drops grid + structure cases → S term ≈ 0 (no failures).
    # Smoke test only — exact value depends on the reward shape.
    assert 0.0 <= r.A <= 1.0


def test_non_determinism_is_raised(monkeypatch, cheap_corpus, setup) -> None:
    """Force two scoring passes to disagree → guard must raise."""
    from jtx.improve import determinism

    call_count = {"n": 0}
    original_compute = determinism.compute_reward

    def flaky_compute(*args, **kwargs):
        call_count["n"] += 1
        r = original_compute(*args, **kwargs)
        # First call: untouched. Second call: jiggle R by epsilon.
        if call_count["n"] % 2 == 0:
            return RewardBreakdown(
                R=r.R + 1e-3, A=r.A, D=r.D, C=r.C, S=r.S,
                weights=r.weights, anchor_scores=r.anchor_scores,
            )
        return r

    monkeypatch.setattr(determinism, "compute_reward", flaky_compute)
    with pytest.raises(NonDeterministicReward, match="R drifted"):
        assert_deterministic(cheap_corpus, Tuning(), setup=setup, quick=True)
