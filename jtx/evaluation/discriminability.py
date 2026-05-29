"""Pairwise discriminability between anchor feature vectors.

Builds a fixed-dimension feature vector per
:class:`~jtx.evaluation.scoring.CorpusSample` (averaging descriptors
across scoring bars), normalizes feature-by-feature, and computes a
euclidean distance matrix between anchors. The "baseline" is the
intra-anchor jitter — different seeds (or small chaos perturbations)
at the same coord produce slightly different output, and the
discriminability check is that distances between *different* anchors
exceed that natural jitter.

The plan note: the v1 anchor targets are deliberately loose (psy and
acid both score 1.0 on the ACID target). This module reports the
failure rather than papering over it — pytest assertions here favour
*shape* (matrix is square, baseline is finite, etc.) and informative
diagnostics over hard pass/fail thresholds.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from jtx.engine.meter import ticks_per_bar as _tpb
from jtx.evaluation import descriptors as D
from jtx.evaluation.scoring import BarEvents, CorpusSample
from jtx.model.events import AbstractEvent

_BarFeatureFn = Callable[[BarEvents, int], float]


def _voice_events(b: BarEvents, voice: str) -> list[AbstractEvent]:
    return b.get(voice, [])


def _onset_count_fn(voice: str) -> _BarFeatureFn:
    def f(b: BarEvents, _tpb: int) -> float:
        return float(D.onset_count(_voice_events(b, voice)))

    return f


def _velocity_mean_fn(voice: str) -> _BarFeatureFn:
    def f(b: BarEvents, _tpb: int) -> float:
        return float(D.velocity_mean(_voice_events(b, voice)))

    return f


def _grid_coverage_fn(voice: str) -> _BarFeatureFn:
    def f(b: BarEvents, tpb: int) -> float:
        return D.sixteenth_grid_coverage(_voice_events(b, voice), tpb)

    return f


def _voice_active_fn(voice: str) -> _BarFeatureFn:
    def f(b: BarEvents, _tpb: int) -> float:
        return 1.0 if D.voice_active(_voice_events(b, voice)) else 0.0

    return f


def _param_variance_fn(voice: str, name: str) -> _BarFeatureFn:
    def f(b: BarEvents, _tpb: int) -> float:
        return D.param_trajectory_variance(_voice_events(b, voice), name)

    return f


def _param_range_fn(voice: str, name: str) -> _BarFeatureFn:
    def f(b: BarEvents, _tpb: int) -> float:
        return D.param_trajectory_range(_voice_events(b, voice), name)

    return f


def _param_mean_fn(voice: str, name: str) -> _BarFeatureFn:
    def f(b: BarEvents, _tpb: int) -> float:
        vs = D.param_values(_voice_events(b, voice), name)
        if not vs:
            return 0.0
        return sum(vs) / len(vs)

    return f


# Fixed feature schema. Keys must stay stable so vectors compare across
# anchors. Each entry is ``(key, fn(bar_events, ticks_per_bar) -> float)``.
FEATURE_SCHEMA: tuple[tuple[str, _BarFeatureFn], ...] = (
    ("bass.onsets", _onset_count_fn("bass")),
    ("bass.velocity", _velocity_mean_fn("bass")),
    ("bass.grid", _grid_coverage_fn("bass")),
    ("lead.onsets", _onset_count_fn("lead")),
    ("lead.grid", _grid_coverage_fn("lead")),
    ("arp.onsets", _onset_count_fn("arp")),
    ("arp.grid", _grid_coverage_fn("arp")),
    ("pad.active", _voice_active_fn("pad")),
    ("pad.onsets", _onset_count_fn("pad")),
    ("sub.active", _voice_active_fn("sub")),
    ("sub.onsets", _onset_count_fn("sub")),
    ("chord.onsets", _onset_count_fn("chord")),
    ("drumkit.onsets", _onset_count_fn("drumkit")),
    ("drumkit.velocity", _velocity_mean_fn("drumkit")),
    ("filter.cutoff_var", _param_variance_fn("filter", "cutoff")),
    ("filter.cutoff_rng", _param_range_fn("filter", "cutoff")),
    ("filter.cutoff_mean", _param_mean_fn("filter", "cutoff")),
)


def feature_keys() -> tuple[str, ...]:
    """Stable feature-vector key ordering."""
    return tuple(k for k, _ in FEATURE_SCHEMA)


def feature_vector(sample: CorpusSample) -> dict[str, float]:
    """Mean-across-scoring-bars value per :data:`FEATURE_SCHEMA` key.

    Bars from *every* part in *sample* are pooled before averaging.
    For anchor-mode usage the sample typically contains only the
    ``drop`` part; structural-mode callers can pass a multi-part
    sample without code changes here.
    """
    ticks_per_bar = _tpb(sample.song.meter, 480)
    bars: list[BarEvents] = []
    for part_bars in sample.bars.values():
        bars.extend(part_bars)
    out: dict[str, float] = {}
    for key, fn in FEATURE_SCHEMA:
        if not bars:
            out[key] = 0.0
        else:
            out[key] = sum(fn(b, ticks_per_bar) for b in bars) / len(bars)
    return out


def feature_array(sample: CorpusSample) -> list[float]:
    """Same as :func:`feature_vector` but as a positional list."""
    fv = feature_vector(sample)
    return [fv[k] for k in feature_keys()]


def _normalize(vectors: list[list[float]]) -> list[list[float]]:
    """Per-dimension min-max scale to ``[0, 1]``. Dead dims map to 0.0."""
    if not vectors:
        return []
    dims = len(vectors[0])
    mins = [min(v[d] for v in vectors) for d in range(dims)]
    maxs = [max(v[d] for v in vectors) for d in range(dims)]
    out: list[list[float]] = []
    for v in vectors:
        row: list[float] = []
        for d in range(dims):
            span = maxs[d] - mins[d]
            if span < 1e-12:
                row.append(0.0)
            else:
                row.append((v[d] - mins[d]) / span)
        out.append(row)
    return out


def euclidean(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


@dataclass(frozen=True)
class DiscriminabilityReport:
    """Output of :func:`discriminability_report`.

    *distance_matrix* is symmetric with a zero diagonal. *baseline*
    is the max intra-anchor jitter distance across the population; an
    off-diagonal pair (i, j) "discriminates" iff its distance exceeds
    *baseline*. *pair_passes* keys are ordered ``(labels[i], labels[j])``
    with ``i < j``.
    """

    labels: tuple[str, ...]
    feature_keys: tuple[str, ...]
    feature_vectors: tuple[tuple[float, ...], ...]
    distance_matrix: tuple[tuple[float, ...], ...]
    intra_anchor_distances: dict[str, tuple[float, ...]]
    baseline: float
    pass_fraction: float
    pair_passes: dict[tuple[str, str], bool]


def discriminability_report(
    centers: Mapping[str, CorpusSample],
    jitter: Mapping[str, Sequence[CorpusSample]] | None = None,
) -> DiscriminabilityReport:
    """Pairwise normalized distance matrix + intra-anchor baseline.

    *centers* maps anchor label → its centre CorpusSample. *jitter*
    (optional) maps the same labels → perturbed samples (different
    seeds at the same coord, or small chaos > 0). The baseline is the
    max centre→jitter distance across the whole population; without
    jitter it is 0.0.

    Centres and jitter samples are normalized in the same pool so the
    distance scale stays comparable across both groups.
    """
    labels = tuple(centers.keys())
    keys = feature_keys()
    center_arrays = [feature_array(centers[label]) for label in labels]

    jitter_arrays: dict[str, list[list[float]]] = {}
    if jitter:
        for label in labels:
            jitter_arrays[label] = [feature_array(s) for s in jitter.get(label, [])]

    pooled: list[list[float]] = list(center_arrays)
    for arrs in jitter_arrays.values():
        pooled.extend(arrs)
    normalized = _normalize(pooled)

    n = len(labels)
    normalized_centers = normalized[:n]
    normalized_jitter: dict[str, list[list[float]]] = {}
    cursor = n
    for label in labels:
        k = len(jitter_arrays.get(label, []))
        normalized_jitter[label] = normalized[cursor : cursor + k]
        cursor += k

    distance_matrix = tuple(
        tuple(euclidean(normalized_centers[i], normalized_centers[j]) for j in range(n))
        for i in range(n)
    )

    intra: dict[str, tuple[float, ...]] = {}
    all_intra: list[float] = []
    for label, jvecs in normalized_jitter.items():
        idx = labels.index(label)
        dists = [euclidean(normalized_centers[idx], jv) for jv in jvecs]
        intra[label] = tuple(dists)
        all_intra.extend(dists)
    baseline = max(all_intra) if all_intra else 0.0

    pair_passes: dict[tuple[str, str], bool] = {}
    total = 0
    passed = 0
    for i in range(n):
        for j in range(i + 1, n):
            d = distance_matrix[i][j]
            passes = d > baseline
            pair_passes[(labels[i], labels[j])] = passes
            total += 1
            if passes:
                passed += 1
    pass_fraction = passed / total if total else 1.0

    return DiscriminabilityReport(
        labels=labels,
        feature_keys=keys,
        feature_vectors=tuple(tuple(v) for v in normalized_centers),
        distance_matrix=distance_matrix,
        intra_anchor_distances=intra,
        baseline=baseline,
        pass_fraction=pass_fraction,
        pair_passes=pair_passes,
    )


__all__ = [
    "DiscriminabilityReport",
    "FEATURE_SCHEMA",
    "discriminability_report",
    "euclidean",
    "feature_array",
    "feature_keys",
    "feature_vector",
]
