"""Tests for the discriminability mode (Phase 1c).

The four sonics anchors live at distinct (texture, motion) coords; if
the algorithms differentiate them at all, the resulting feature
vectors should sit further apart than the per-anchor jitter.

The v1 anchor targets are deliberately loose (per the epic plan —
"psy and acid both score 1.0 on the ACID target" is a known finding).
These tests assert *shape* (matrix is square, baseline is finite) and
the headline coverage number, not strict per-pair separation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.composer import compose
from jtx.composer.mood import MoodSpec
from jtx.composer.sonics import SONICS_REGIONS
from jtx.evaluation import (
    DiscriminabilityReport,
    discriminability_report,
    feature_array,
    feature_keys,
    feature_vector,
    render_sample,
)
from jtx.persist.json_io import load_setup

REPO_ROOT = Path(__file__).resolve().parents[1]

_SONICS_MOOD: dict[str, MoodSpec] = {
    "acid": MoodSpec(valence=-0.15, energy=0.55),
    "deep_techno": MoodSpec(valence=-0.35, energy=0.4),
    "psytrance": MoodSpec(valence=-0.25, energy=0.9),
    "dub_techno": MoodSpec(valence=0.0, energy=0.2),
}


@pytest.fixture(scope="module")
def iac_setup():
    return load_setup(REPO_ROOT / "setups" / "iac.jtx-setup")


def _sonics_sample(label: str, setup, *, seed_tag: str = "", chaos: float = 0.0):
    texture, motion = SONICS_REGIONS[label]
    title = f"{label}{seed_tag}".title()
    song = compose(
        title, "iac", _SONICS_MOOD[label], "song",
        chaos=chaos, texture=texture, motion=motion,
    )
    return render_sample(song, setup, parts=("drop",), bars=4)


@pytest.fixture(scope="module")
def sonics_anchor_samples(iac_setup):
    return {label: _sonics_sample(label, iac_setup) for label in SONICS_REGIONS}


@pytest.fixture(scope="module")
def sonics_jitter_samples(iac_setup):
    """Three jittered renders per anchor (different seeds, small chaos)."""
    return {
        label: [
            _sonics_sample(label, iac_setup, seed_tag=f"-j{k}", chaos=0.05)
            for k in range(3)
        ]
        for label in SONICS_REGIONS
    }


# ---------- feature_vector ---------------------------------------------


def test_feature_keys_are_stable_and_ordered() -> None:
    keys = feature_keys()
    assert isinstance(keys, tuple)
    assert keys == tuple(sorted(keys, key=keys.index))  # tautology, just shape
    assert "bass.onsets" in keys
    assert "filter.cutoff_var" in keys
    assert "drumkit.onsets" in keys


def test_feature_vector_returns_one_float_per_key(iac_setup) -> None:
    sample = _sonics_sample("acid", iac_setup)
    fv = feature_vector(sample)
    assert set(fv.keys()) == set(feature_keys())
    for v in fv.values():
        assert isinstance(v, float)


def test_feature_array_matches_key_order(iac_setup) -> None:
    sample = _sonics_sample("acid", iac_setup)
    fv = feature_vector(sample)
    arr = feature_array(sample)
    assert arr == [fv[k] for k in feature_keys()]


def test_empty_sample_yields_all_zero_vector(iac_setup) -> None:
    """A CorpusSample with no rendered bars should not blow up."""
    from jtx.evaluation.scoring import CorpusSample

    song = compose("Empty", "iac", _SONICS_MOOD["acid"], "song", chaos=0.0, texture=0.5, motion=0.5)
    sample = CorpusSample(song=song, bars={})
    fv = feature_vector(sample)
    assert all(v == 0.0 for v in fv.values())


# ---------- discriminability_report shape ------------------------------


def test_report_shape_no_jitter(sonics_anchor_samples) -> None:
    report = discriminability_report(sonics_anchor_samples)
    assert isinstance(report, DiscriminabilityReport)
    n = len(report.labels)
    assert n == 4
    assert all(len(row) == n for row in report.distance_matrix)
    # Zero diagonal.
    for i in range(n):
        assert report.distance_matrix[i][i] == pytest.approx(0.0)
    # Symmetric.
    for i in range(n):
        for j in range(n):
            assert report.distance_matrix[i][j] == pytest.approx(
                report.distance_matrix[j][i]
            )
    # Without jitter, baseline is zero and every off-diagonal pair
    # trivially exceeds it (unless two anchors happen to collide).
    assert report.baseline == pytest.approx(0.0)


def test_report_with_jitter_carries_baseline(
    sonics_anchor_samples, sonics_jitter_samples
) -> None:
    report = discriminability_report(sonics_anchor_samples, sonics_jitter_samples)
    assert report.baseline > 0.0
    # Each anchor contributed its jitter distances.
    for label in sonics_anchor_samples:
        assert len(report.intra_anchor_distances[label]) == 3


def test_normalized_vectors_in_unit_range(sonics_anchor_samples, sonics_jitter_samples) -> None:
    report = discriminability_report(sonics_anchor_samples, sonics_jitter_samples)
    for vec in report.feature_vectors:
        for v in vec:
            assert 0.0 <= v <= 1.0 + 1e-9


# ---------- discriminability: substantive coverage ---------------------


def test_majority_of_anchor_pairs_discriminate(
    sonics_anchor_samples, sonics_jitter_samples
) -> None:
    """At least 2/3 of off-diagonal sonics pairs exceed the jitter baseline.

    This is loose on purpose — v1 anchor targets are known to leave
    some pairs (e.g. psytrance vs dub_techno) inside the jitter
    cluster. The point of this test is to catch regressions where the
    generator collapses *most* anchors together, not to pin down a
    specific pair.
    """
    report = discriminability_report(sonics_anchor_samples, sonics_jitter_samples)
    assert report.pass_fraction >= 2 / 3, (
        f"only {report.pass_fraction:.2f} of pairs discriminated; "
        f"matrix={report.distance_matrix} baseline={report.baseline:.3f} "
        f"passes={report.pair_passes}"
    )


def test_acid_and_deep_techno_discriminate(
    sonics_anchor_samples, sonics_jitter_samples
) -> None:
    """The opposing-motion pair always exceeds the jitter baseline.

    Acid sits at motion=0.725, deep_techno at motion=0.250 — the
    filter trajectory + bass density features pull them apart even
    under the loose v1 targets. If this regresses, discriminability
    has fundamentally collapsed.
    """
    report = discriminability_report(sonics_anchor_samples, sonics_jitter_samples)
    assert report.pair_passes[("acid", "deep_techno")] is True
