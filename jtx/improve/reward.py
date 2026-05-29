"""Single-scalar reward R for ``jtx-improve``.

The closed loop optimizes::

    R = w_anchor·A − w_dead·D − w_collapse·C − w_struct·S

where the four terms are:

* ``A`` — mean anchor-fidelity (intent × delivery) over the corpus's
  named anchors. Uses :func:`jtx.evaluation.score_anchor` with the
  matching :data:`jtx.evaluation.ANCHORS` target.
* ``D`` — dead-knob fraction = (count of (axis, descriptor) cells with
  ``|slope| < ε``) ÷ (total cells). Uses :func:`jtx.evaluation.sweep`
  across all four composer input axes.
* ``C`` — discriminability collapse penalty = ``1 - pass_fraction``
  from :func:`jtx.evaluation.discriminability_report` over the four
  sonics anchors with jitter samples drawn per corpus config.
* ``S`` — structural-integrity failure count, normalized by total
  checks. Uses :func:`jtx.evaluation.structural_integrity` across
  the per-format structure cases.

The driver feeds the per-anchor scores into a hard-floor check
separately so the floor catches single-anchor regressions even when
the overall R appears to improve.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jtx.composer import compose
from jtx.composer.tuning import Tuning
from jtx.evaluation import (
    ANCHORS,
    ScoreReport,
    StructureReport,
    discriminability_report,
    render_sample,
    score_anchor,
    structural_integrity,
    sweep,
)
from jtx.evaluation.sensitivity import SensitivityFixed
from jtx.improve.corpus import Corpus, CorpusCase
from jtx.model.setup import Setup
from jtx.persist.json_io import load_setup


@dataclass(frozen=True)
class RewardWeights:
    """Multipliers on the four terms of R.

    Defaults match the Phase 2 plan: anchor 1.0, dead 0.4, collapse
    0.6, struct 0.3. The dead-knob and collapse terms get smaller
    weights so the optimizer isn't pushed to perfectly tile the
    descriptor space at the cost of anchor identity.
    """

    anchor: float = 1.0
    dead: float = 0.4
    collapse: float = 0.6
    struct: float = 0.3


@dataclass(frozen=True)
class RewardBreakdown:
    """All four term values + the final R + per-anchor diagnostics.

    *anchor_scores* is the per-anchor total score; the hard-floor check
    consumes this so a 5%+ regression on any anchor auto-rejects.
    *anchor_intent* / *anchor_delivery* expose the intent × delivery
    decomposition for the log report.
    """

    R: float
    A: float
    D: float
    C: float
    S: float
    weights: RewardWeights
    anchor_scores: dict[str, float] = field(default_factory=dict)
    anchor_intent: dict[str, float] = field(default_factory=dict)
    anchor_delivery: dict[str, float] = field(default_factory=dict)
    structure_pass_fraction: float = 1.0
    sensitivity_dead_keys: tuple[tuple[str, str], ...] = ()
    """Each entry is ``(axis, feature_key)`` for a cell judged dead."""

    discriminability_pass_fraction: float = 1.0

    def anchor_total(self, name: str) -> float:
        """Anchor total score, defaulting to 0.0 if missing."""
        return self.anchor_scores.get(name, 0.0)


def _compose_case(case: CorpusCase, tuning: Tuning):
    """Compose one CorpusCase under *tuning*."""
    return compose(
        case.title,
        "iac",
        case.mood,
        case.fmt,
        chaos=case.chaos,
        texture=case.texture,
        motion=case.motion,
        tuning=tuning,
    )


def _anchor_term(
    corpus: Corpus, setup: Setup, tuning: Tuning
) -> tuple[float, dict[str, float], dict[str, float], dict[str, float]]:
    scores: dict[str, float] = {}
    intent: dict[str, float] = {}
    delivery: dict[str, float] = {}
    for name, case in corpus.anchors.items():
        target = ANCHORS.get(name)
        if target is None:
            # Corpus declares an anchor we don't have a target for —
            # skip rather than fail; the optimizer still gets signal
            # from the others.
            continue
        song = _compose_case(case, tuning)
        report: ScoreReport = score_anchor(
            song, setup, target, parts=corpus.parts, bars=corpus.bars
        )
        scores[name] = report.total_score
        intent[name] = report.intent_score
        delivery[name] = report.delivery_score
    if not scores:
        return 0.0, {}, {}, {}
    A = sum(scores.values()) / len(scores)
    return A, scores, intent, delivery


def _dead_term(
    corpus: Corpus, setup: Setup, tuning: Tuning, slope_eps: float = 1e-3
) -> tuple[float, tuple[tuple[str, str], ...]]:
    """Dead-knob fraction across all sensitivity axes.

    Each axis yields one feature vector → per-feature slope. A cell is
    dead iff ``|slope| < slope_eps``. The fraction is dead-cells over
    total-cells, in ``[0, 1]``.
    """
    dead_cells: list[tuple[str, str]] = []
    total = 0
    for axis in corpus.sensitivity_axes:
        result = sweep(
            axis,  # type: ignore[arg-type]
            setup,
            steps=corpus.sensitivity_steps,
            fixed=SensitivityFixed(),
            seed=0,
            parts=corpus.parts,
            bars=corpus.bars,
            tuning=tuning,
        )
        for key, slope in result.slope.items():
            total += 1
            if abs(slope) < slope_eps:
                dead_cells.append((axis, key))
    if total == 0:
        return 0.0, ()
    return len(dead_cells) / total, tuple(dead_cells)


def _collapse_term(
    corpus: Corpus, setup: Setup, tuning: Tuning
) -> tuple[float, float]:
    """Discriminability collapse penalty across the four sonics anchors.

    Renders each sonics anchor at its centre + ``jitter_per_anchor``
    perturbed seeds, runs :func:`discriminability_report`, and returns
    ``(1 - pass_fraction, pass_fraction)``. Higher pass fraction = more
    pairs cleanly separated.
    """
    sonics_names = [
        n for n in ("acid", "deep_techno", "psytrance", "dub_techno")
        if n in corpus.anchors
    ]
    if len(sonics_names) < 2:
        return 0.0, 1.0

    centers = {}
    jitter = {}
    for name in sonics_names:
        case = corpus.anchors[name]
        # Center sample at exact anchor coords.
        center_song = _compose_case(case, tuning)
        centers[name] = render_sample(
            center_song, setup, parts=corpus.parts, bars=corpus.bars
        )
        # Jitter: small chaos + different titles → different seeds.
        jitter_samples = []
        for k in range(corpus.jitter_per_anchor):
            jcase = CorpusCase(
                name=f"{case.name}-j{k}",
                mood=case.mood,
                texture=case.texture,
                motion=case.motion,
                fmt=case.fmt,
                chaos=corpus.jitter_chaos,
            )
            jsong = _compose_case(jcase, tuning)
            jitter_samples.append(
                render_sample(jsong, setup, parts=corpus.parts, bars=corpus.bars)
            )
        jitter[name] = jitter_samples

    report = discriminability_report(centers, jitter)
    return 1.0 - report.pass_fraction, report.pass_fraction


def _structure_term(
    corpus: Corpus, setup: Setup, tuning: Tuning
) -> tuple[float, float]:
    """Structural-integrity failure rate across the per-format cases.

    Sums per-case failed-check counts; returns
    ``(failures / total_checks, pass_fraction)``. Pass fraction is the
    aggregate over all checks across all structure cases — useful for
    the log.
    """
    total_checks = 0
    failed_checks = 0
    for case in corpus.structure_cases:
        song = _compose_case(case, tuning)
        report: StructureReport = structural_integrity(
            song, setup, bars=corpus.bars
        )
        for check in report.checks:
            total_checks += 1
            if not check.passed:
                failed_checks += 1
    if total_checks == 0:
        return 0.0, 1.0
    return failed_checks / total_checks, 1.0 - failed_checks / total_checks


def compute_reward(
    corpus: Corpus,
    tuning: Tuning,
    *,
    weights: RewardWeights | None = None,
    setup: Setup | None = None,
) -> RewardBreakdown:
    """Score *tuning* against *corpus*; return all four terms + R.

    *setup* is loaded from ``corpus.setup_path`` if not supplied — the
    driver passes a cached Setup so repeated reward evaluations don't
    re-read the same file.

    The four terms are computed independently; one failure in (e.g.)
    discriminability does not poison the others, so the breakdown
    stays readable even when R drops.
    """
    weights = weights or RewardWeights()
    setup = setup or load_setup(corpus.setup_path)

    A, scores, intent, delivery = _anchor_term(corpus, setup, tuning)
    D, dead_cells = _dead_term(corpus, setup, tuning)
    C, disc_pass = _collapse_term(corpus, setup, tuning)
    S, struct_pass = _structure_term(corpus, setup, tuning)

    R = (
        weights.anchor * A
        - weights.dead * D
        - weights.collapse * C
        - weights.struct * S
    )

    return RewardBreakdown(
        R=R,
        A=A,
        D=D,
        C=C,
        S=S,
        weights=weights,
        anchor_scores=scores,
        anchor_intent=intent,
        anchor_delivery=delivery,
        structure_pass_fraction=struct_pass,
        sensitivity_dead_keys=dead_cells,
        discriminability_pass_fraction=disc_pass,
    )


def hard_floor_violation(
    candidate: RewardBreakdown,
    best: RewardBreakdown,
    *,
    epsilon: float = 0.05,
) -> str | None:
    """Return a diagnostic string if any anchor regressed too far.

    The plan's hard floor: any anchor whose total score dropped more
    than ``epsilon`` below the running best auto-rejects regardless of
    the overall ΔR. Returns ``None`` if the candidate passes.
    """
    for name, best_score in best.anchor_scores.items():
        cand_score = candidate.anchor_total(name)
        if cand_score + epsilon < best_score:
            return (
                f"hard floor: anchor {name!r} regressed "
                f"{best_score:.3f} → {cand_score:.3f} "
                f"(Δ={cand_score - best_score:+.3f}, ε={epsilon})"
            )
    return None


__all__ = [
    "RewardBreakdown",
    "RewardWeights",
    "compute_reward",
    "hard_floor_violation",
]
