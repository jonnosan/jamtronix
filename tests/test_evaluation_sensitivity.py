"""Tests for the knob-sensitivity sweep (Phase 1c).

Each composer axis is meant to actually *move* some descriptor;
dead-knob detection is the whole point of this mode. Tests pin a
handful of axis/descriptor pairs that should respond and surface
the sweep's regression stats so failures are immediately diagnosable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.evaluation import SensitivityResult, sweep
from jtx.evaluation.sensitivity import SensitivityFixed, _linreg
from jtx.persist.json_io import load_setup

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def iac_setup():
    return load_setup(REPO_ROOT / "setups" / "iac.jtx-setup")


# ---------- _linreg unit tests -----------------------------------------


def test_linreg_perfect_line() -> None:
    slope, intercept, r2 = _linreg([0, 1, 2, 3], [1, 3, 5, 7])  # y = 2x + 1
    assert slope == pytest.approx(2.0)
    assert intercept == pytest.approx(1.0)
    assert r2 == pytest.approx(1.0)


def test_linreg_flat_input() -> None:
    """Constant ys → zero slope, R² = 0 (flat input cannot explain variance)."""
    slope, _intercept, r2 = _linreg([0, 0.5, 1.0], [5.0, 5.0, 5.0])
    assert slope == pytest.approx(0.0)
    assert r2 == pytest.approx(0.0)


def test_linreg_handles_short_input() -> None:
    slope, intercept, r2 = _linreg([0.0], [1.0])
    assert (slope, intercept, r2) == (0.0, 0.0, 0.0)


# ---------- sweep: shape -----------------------------------------------


def test_sweep_returns_per_step_points(iac_setup) -> None:
    result = sweep("motion", iac_setup, steps=5)
    assert isinstance(result, SensitivityResult)
    assert result.steps == 5
    assert len(result.points) == 5
    # Axis values span the natural range linearly.
    assert result.points[0].axis_value == pytest.approx(0.0)
    assert result.points[-1].axis_value == pytest.approx(1.0)
    # Every point carries the full feature vector.
    keys = set(result.feature_keys)
    for p in result.points:
        assert set(p.features.keys()) == keys


def test_sweep_valence_uses_signed_range(iac_setup) -> None:
    result = sweep("valence", iac_setup, steps=3)
    assert result.points[0].axis_value == pytest.approx(-1.0)
    assert result.points[-1].axis_value == pytest.approx(1.0)


def test_sweep_rejects_one_step(iac_setup) -> None:
    with pytest.raises(ValueError):
        sweep("motion", iac_setup, steps=1)


# ---------- sweep: knob responsiveness ---------------------------------


def test_motion_drives_filter_cutoff_variance(iac_setup) -> None:
    """Motion is supposed to swing the filter cutoff harder.

    The composer's _filter_pattern scales depth + window with motion;
    cutoff_var should rise approximately monotonically. We assert a
    positive slope with an R² floor — the per-step renders include
    accent jitter so a perfect line isn't expected.
    """
    result = sweep("motion", iac_setup, steps=7)
    slope = result.slope["filter.cutoff_var"]
    r2 = result.r2["filter.cutoff_var"]
    assert slope > 0.0, (
        f"motion did not increase filter.cutoff_var; slope={slope}, r2={r2}"
    )
    assert r2 > 0.5, (
        f"motion vs filter.cutoff_var has weak monotonicity: r2={r2:.3f}, slope={slope}"
    )


def test_motion_drives_filter_cutoff_range(iac_setup) -> None:
    """A wider cutoff window is the most visible motion effect."""
    result = sweep("motion", iac_setup, steps=7)
    assert result.slope["filter.cutoff_rng"] > 0.0
    assert result.r2["filter.cutoff_rng"] > 0.7


def test_texture_drives_voice_activation(iac_setup) -> None:
    """Texture gates palette voices on via _VOICE_TAU thresholds.

    Pad activation (τ=0.5) should rise from 0 → 1 as texture sweeps
    from 0 → 1. The exact slope depends on the τ curve; we just
    assert the trend is upward.
    """
    result = sweep("texture", iac_setup, steps=7)
    assert result.slope["pad.active"] > 0.0, (
        f"texture did not activate pad voice; slope={result.slope['pad.active']}"
    )


# ---------- sweep: dead-knob detection ---------------------------------


def test_sweep_surfaces_some_active_knobs(iac_setup) -> None:
    """Every axis must move *at least one* descriptor."""
    for axis in ("texture", "motion", "valence", "energy"):
        result = sweep(axis, iac_setup, steps=5)  # type: ignore[arg-type]
        active = [k for k, s in result.slope.items() if abs(s) > 1e-3]
        assert active, f"{axis}: every descriptor is dead (slope ≈ 0): {result.slope}"


def test_sweep_is_deterministic_given_same_seed(iac_setup) -> None:
    a = sweep("motion", iac_setup, steps=3, seed=42)
    b = sweep("motion", iac_setup, steps=3, seed=42)
    assert a.slope == b.slope
    assert a.r2 == b.r2


def test_sweep_with_custom_fixed_inputs(iac_setup) -> None:
    """SensitivityFixed lets the caller pin the non-swept axes."""
    fixed = SensitivityFixed(texture=0.9, motion=0.5, valence=0.5, energy=0.5)
    result = sweep("valence", iac_setup, steps=3, fixed=fixed)
    # Just shape — we trust the regression once we know it ran.
    assert len(result.points) == 3
