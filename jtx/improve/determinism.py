"""Determinism guard — refuse to optimize on a non-reproducible reward.

A reward function with hidden randomness (uninitialized RNGs, time-
dependent calls, etc.) makes ΔR meaningless: a change might appear
to improve R purely because the next render rolled differently. This
module renders + scores a small subcorpus twice and asserts the two
reward breakdowns match exactly.

Two failure modes the check catches:

* The composer or evaluator gained a non-deterministic dependency.
* The optimizer wrote ``tuning.toml`` between the two reads
  (signalling a missing cache invalidation in the driver).

The loop calls :func:`assert_deterministic` at session start (full
sub-corpus) and once per accept (cheap re-check against the new
running best).
"""

from __future__ import annotations

import math
from dataclasses import replace

from jtx.composer.tuning import Tuning
from jtx.improve.corpus import Corpus
from jtx.improve.reward import RewardBreakdown, RewardWeights, compute_reward
from jtx.model.setup import Setup


class NonDeterministicReward(Exception):
    """Raised when two scoring passes against the same inputs disagree."""

    def __init__(
        self,
        first: RewardBreakdown,
        second: RewardBreakdown,
        detail: str,
    ) -> None:
        super().__init__(detail)
        self.first = first
        self.second = second
        self.detail = detail


def _subcorpus(corpus: Corpus) -> Corpus:
    """Smaller corpus for the per-iteration determinism check.

    Drops grid + structure cases (they multiply scoring time) and
    halves the sensitivity step count. The four anchor-fidelity scores
    + the discriminability check still run — that's where non-
    determinism is most likely to show up.
    """
    new_steps = max(2, corpus.sensitivity_steps // 2)
    return replace(
        corpus,
        grid=(),
        structure_cases=(),
        sensitivity_steps=new_steps,
        jitter_per_anchor=min(2, corpus.jitter_per_anchor),
    )


def _close(a: float, b: float, *, atol: float = 1e-9) -> bool:
    return math.isclose(a, b, abs_tol=atol)


def _diff(a: RewardBreakdown, b: RewardBreakdown) -> str | None:
    """Return a short diff string if *a* and *b* differ; else ``None``."""
    if not _close(a.R, b.R):
        return f"R drifted {a.R:.9f} → {b.R:.9f}"
    if not _close(a.A, b.A) or not _close(a.D, b.D) or not _close(a.C, b.C) or not _close(a.S, b.S):
        return (
            f"term drift "
            f"(A {a.A:.9f}↔{b.A:.9f}, D {a.D:.9f}↔{b.D:.9f}, "
            f"C {a.C:.9f}↔{b.C:.9f}, S {a.S:.9f}↔{b.S:.9f})"
        )
    for name, score in a.anchor_scores.items():
        other = b.anchor_scores.get(name)
        if other is None or not _close(score, other):
            return f"anchor {name!r} drifted {score:.9f} → {other}"
    return None


def assert_deterministic(
    corpus: Corpus,
    tuning: Tuning,
    *,
    setup: Setup,
    weights: RewardWeights | None = None,
    quick: bool = False,
) -> RewardBreakdown:
    """Score *tuning* twice and assert identical R + per-anchor scores.

    Returns the (first) :class:`RewardBreakdown` so the caller can
    reuse it as the running-best baseline. Raises
    :class:`NonDeterministicReward` on disagreement.

    *quick* swaps in a shrunken sub-corpus (no grid / structure /
    minimal jitter). The driver uses ``quick=True`` per iteration and
    ``quick=False`` once at session start.
    """
    eval_corpus = _subcorpus(corpus) if quick else corpus
    first = compute_reward(eval_corpus, tuning, weights=weights, setup=setup)
    second = compute_reward(eval_corpus, tuning, weights=weights, setup=setup)
    diff = _diff(first, second)
    if diff is not None:
        raise NonDeterministicReward(first=first, second=second, detail=diff)
    return first


__all__ = [
    "NonDeterministicReward",
    "assert_deterministic",
]
