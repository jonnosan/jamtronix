"""End-to-end tests for score_anchor — compose at anchor, score, expect high."""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.composer import compose
from jtx.composer.mood import MOOD_ANCHORS, MoodSpec
from jtx.composer.sonics import SONICS_REGIONS
from jtx.evaluation import ANCHORS, ScoreReport, render_sample, score_anchor
from jtx.persist.json_io import load_setup

REPO_ROOT = Path(__file__).resolve().parents[1]

# Sonics anchors carry only (texture, motion); pair each with a sensible
# mood (matches the existing composer test fixtures where defined).
_SONICS_MOOD: dict[str, MoodSpec] = {
    "acid": MoodSpec(valence=-0.15, energy=0.55),
    "deep_techno": MoodSpec(valence=-0.35, energy=0.4),
    "psytrance": MoodSpec(valence=-0.25, energy=0.9),
    "dub_techno": MoodSpec(valence=0.0, energy=0.2),
}


@pytest.fixture(scope="module")
def iac_setup():
    return load_setup(REPO_ROOT / "setups" / "iac.jtx-setup")


def _sonics_song(label: str):
    texture, motion = SONICS_REGIONS[label]
    return compose(
        label.title(), "iac", _SONICS_MOOD[label], "song",
        chaos=0.0, texture=texture, motion=motion,
    )


def _mood_song(label: str):
    return compose(
        label.title(), "iac", MOOD_ANCHORS[label], "song",
        chaos=0.0, texture=0.5, motion=0.5,
    )


# ---------- render_sample ----------------------------------------------


def test_render_sample_skips_bar_zero(iac_setup) -> None:
    song = _sonics_song("acid")
    sample = render_sample(song, iac_setup, parts=("drop",), bars=4)
    # 4 bars rendered, bar 0 skipped → 3 scoring bars.
    assert len(sample.bars["drop"]) == 3


def test_render_sample_skips_missing_parts(iac_setup) -> None:
    song = _sonics_song("acid")
    sample = render_sample(
        song, iac_setup, parts=("drop", "no_such_part"), bars=4,
    )
    assert "drop" in sample.bars
    assert "no_such_part" not in sample.bars


def test_render_sample_is_deterministic(iac_setup) -> None:
    """Same (song, setup, parts, bars) → identical CorpusSample."""
    song = _sonics_song("acid")
    a = render_sample(song, iac_setup, parts=("drop",), bars=4)
    b = render_sample(song, iac_setup, parts=("drop",), bars=4)
    assert a.bars == b.bars


# ---------- score_anchor: shape ----------------------------------------


def test_score_report_shape(iac_setup) -> None:
    song = _sonics_song("acid")
    report = score_anchor(song, iac_setup, ANCHORS["acid"])
    assert isinstance(report, ScoreReport)
    assert report.target_name == "acid"
    assert 0.0 <= report.intent_score <= 1.0
    assert 0.0 <= report.delivery_score <= 1.0
    # Total is the product, by design.
    assert abs(report.total_score - report.intent_score * report.delivery_score) < 1e-9
    assert set(report.intent_breakdown.keys()) == {
        ic.label for ic in ANCHORS["acid"].intent_predicates
    }
    assert set(report.delivery_breakdown.keys()) == {
        dc.label for dc in ANCHORS["acid"].delivery_descriptors
    }


# ---------- score_anchor: anchor diagonal ------------------------------


@pytest.mark.parametrize("label", list(SONICS_REGIONS.keys()))
def test_sonics_anchor_scores_high_at_anchor_coords(iac_setup, label) -> None:
    """At an anchor's own coords, that anchor's target should land high.

    v1 threshold is intentionally loose (>= 0.5). Phase 1c's
    discriminability mode will pressure-test whether targets are tight
    enough to separate styles.
    """
    song = _sonics_song(label)
    report = score_anchor(song, iac_setup, ANCHORS[label])
    assert report.total_score >= 0.5, (
        f"{label} song scored only {report.total_score:.3f} against {label} target; "
        f"intent={report.intent_breakdown} delivery={report.delivery_breakdown}"
    )


@pytest.mark.parametrize("label", ["happy", "sad", "brooding"])
def test_mood_anchor_scores_high_at_anchor_coords(iac_setup, label) -> None:
    song = _mood_song(label)
    report = score_anchor(song, iac_setup, ANCHORS[label])
    assert report.total_score >= 0.5, (
        f"{label} song scored only {report.total_score:.3f}; "
        f"intent={report.intent_breakdown} delivery={report.delivery_breakdown}"
    )


# ---------- score_anchor: opposing pair --------------------------------


def test_acid_vs_deep_techno_each_prefers_its_own_target(iac_setup) -> None:
    """Acid song scores higher on ACID than on DEEP_TECHNO and vice versa.

    This is the one cross-target invariant Phase 1b can safely assert:
    these two anchors sit on opposite sides of the motion axis
    (acid motion=0.725, deep_techno motion=0.250) so the filter-depth
    intent predicates and the cutoff-variance delivery descriptors
    pull in opposite directions. Other pairs (psy vs acid, dub vs acid)
    overlap on motion and are Phase 1c's job.
    """
    acid_song = _sonics_song("acid")
    deep_song = _sonics_song("deep_techno")

    acid_score_acid = score_anchor(acid_song, iac_setup, ANCHORS["acid"]).total_score
    acid_score_deep = score_anchor(acid_song, iac_setup, ANCHORS["deep_techno"]).total_score
    assert acid_score_acid > acid_score_deep

    deep_score_acid = score_anchor(deep_song, iac_setup, ANCHORS["acid"]).total_score
    deep_score_deep = score_anchor(deep_song, iac_setup, ANCHORS["deep_techno"]).total_score
    assert deep_score_deep > deep_score_acid


def test_happy_vs_sad_each_prefers_its_own_target(iac_setup) -> None:
    """Happy song scores higher on HAPPY than on SAD (major↔minor flip)."""
    happy_song = _mood_song("happy")
    sad_song = _mood_song("sad")

    assert (
        score_anchor(happy_song, iac_setup, ANCHORS["happy"]).total_score
        > score_anchor(happy_song, iac_setup, ANCHORS["sad"]).total_score
    )
    assert (
        score_anchor(sad_song, iac_setup, ANCHORS["sad"]).total_score
        > score_anchor(sad_song, iac_setup, ANCHORS["happy"]).total_score
    )


# ---------- score_anchor: intent × delivery composition ----------------


def test_total_is_product_not_average(iac_setup) -> None:
    """Compose by multiplication: high intent + zero delivery = zero total."""
    from jtx.evaluation.targets import DeliveryCheck, IntentCheck, Target

    # Synthetic target: intent always 1.0, delivery always 0.0.
    silent_target = Target(
        name="silent",
        intent_predicates=(IntentCheck("trivially true", lambda song: 1.0),),
        delivery_descriptors=(DeliveryCheck("trivially false", lambda sample: 0.0),),
    )
    song = _sonics_song("acid")
    report = score_anchor(song, iac_setup, silent_target)
    assert report.intent_score == 1.0
    assert report.delivery_score == 0.0
    assert report.total_score == 0.0  # 1.0 × 0.0, not (1.0 + 0.0) / 2
