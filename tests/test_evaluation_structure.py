"""Tests for the per-format structural-integrity mode (Phase 1c).

Each ``Song.format`` archetype carries its own arrangement promise.
These tests pick a representative composition per format and assert
the check outcomes look plausible without pinning the exact pass /
fail flags — Phase 1c wants a measurement, not a regression suite for
specific arrangement bugs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.composer import compose
from jtx.composer.mood import MOOD_ANCHORS
from jtx.evaluation import StructureCheck, StructureReport, structural_integrity
from jtx.persist.json_io import load_setup

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def iac_setup():
    return load_setup(REPO_ROOT / "setups" / "iac.jtx-setup")


def _make(fmt: str, mood_label: str = "euphoric", *, chaos: float = 1.0):
    """Compose at chaos=1.0 by default so song picks 6 parts (with outro)."""
    return compose(
        f"Test-{fmt}-{mood_label}",
        "iac",
        MOOD_ANCHORS[mood_label],
        fmt,  # type: ignore[arg-type]
        chaos=chaos,
        texture=0.6,
        motion=0.6,
    )


# ---------- report shape ------------------------------------------------


@pytest.mark.parametrize("fmt", ["sting", "jingle", "loop", "ramp", "song", "anthem"])
def test_structural_integrity_returns_report(iac_setup, fmt) -> None:
    song = _make(fmt)
    report = structural_integrity(song, iac_setup)
    assert isinstance(report, StructureReport)
    assert report.fmt == fmt
    assert 0.0 <= report.score <= 1.0
    for c in report.checks:
        assert isinstance(c, StructureCheck)
        assert isinstance(c.name, str) and c.name
        assert isinstance(c.detail, str)


def test_unknown_format_raises(iac_setup) -> None:
    song = _make("song")
    # Mutate to a bogus format.
    object.__setattr__(song, "format", "garbage")
    with pytest.raises(ValueError):
        structural_integrity(song, iac_setup)


# ---------- per-format substantive checks ------------------------------


def test_song_format_emits_arc_checks(iac_setup) -> None:
    """song format with chaos=1.0 picks 6 parts → all four arc checks fire.

    The pass/fail outcome itself is the *signal* — we just verify
    every named check is present so the report is dashboardable.
    """
    song = _make("song", chaos=1.0)
    report = structural_integrity(song, iac_setup)
    names = {c.name for c in report.checks}
    assert "drop denser than intro" in names
    assert "drop cutoff peak above intro" in names
    assert "build density rises bar-over-bar" in names
    assert "outro decays from drop" in names


def test_song_drop_denser_than_intro_typically_holds(iac_setup) -> None:
    """The composer's intensity envelope makes drop > intro in onset density.

    Acid sonics + euphoric mood produces a clear arc; if this check
    starts failing across multiple random seeds the recipe has lost
    its drop dynamics.
    """
    failures = 0
    for tag in ("a", "b", "c"):
        song = compose(
            f"Arc-{tag}", "iac", MOOD_ANCHORS["euphoric"], "song",
            chaos=0.5, texture=0.6, motion=0.6,
        )
        report = structural_integrity(song, iac_setup)
        drop_check = next(c for c in report.checks if c.name == "drop denser than intro")
        if not drop_check.passed:
            failures += 1
    assert failures == 0, "drop-vs-intro density check regressed"


def test_ramp_density_rises_across_parts(iac_setup) -> None:
    song = _make("ramp", chaos=1.0)
    report = structural_integrity(song, iac_setup)
    names = {c.name for c in report.checks}
    assert "ramp density rises across parts" in names


def test_loop_variance_check_present(iac_setup) -> None:
    song = _make("loop", chaos=0.0)
    report = structural_integrity(song, iac_setup)
    assert any("per-bar density variance stays low" in c.name for c in report.checks)


def test_loop_per_bar_density_actually_stays_low(iac_setup) -> None:
    """A loop part should repeat — a regression here means the
    algorithms are producing wildly different bars for the same Part."""
    song = _make("loop", chaos=0.0)
    report = structural_integrity(song, iac_setup)
    loop_check = next(c for c in report.checks if "stays low" in c.name)
    assert loop_check.passed, f"loop bars are not stable: {loop_check.detail}"


def test_sting_total_bars_in_spec(iac_setup) -> None:
    song = _make("sting", chaos=0.0)
    report = structural_integrity(song, iac_setup)
    bar_check = next(c for c in report.checks if "total bars within" in c.name)
    assert bar_check.passed, f"sting violates bar-count spec: {bar_check.detail}"


def test_jingle_carries_both_checks(iac_setup) -> None:
    song = _make("jingle", chaos=1.0)
    report = structural_integrity(song, iac_setup)
    names = {c.name for c in report.checks}
    assert any("total bars within" in n for n in names)
    assert any("arc resolves" in n for n in names)


def test_anthem_emits_full_arc_checks(iac_setup) -> None:
    song = _make("anthem", chaos=1.0)
    report = structural_integrity(song, iac_setup)
    names = {c.name for c in report.checks}
    # Anthem reuses the song-arc check set.
    assert "drop denser than intro" in names
    assert "build density rises bar-over-bar" in names
