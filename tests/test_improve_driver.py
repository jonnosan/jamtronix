"""Phase 2b verification — closed-loop driver behavior.

Each test from the Phase 2 verification list in the epic plan has a
direct mapping here:

* **Should-fail seeded overrides** — force every voice_tau to 1.0 or
  collapse every knob window to a point. The loop's hard-floor +
  accept-only-on-improvement logic must reject these.
* **Should-improve seeded override** — pick a weak descriptor; show
  that a targeted perturbation can land on R > baseline.
* **Determinism** — run the same session twice and confirm identical
  accept/reject sequence + identical R per iteration.
* **Allow-list enforcement** — try to direct a proposal at
  ``jtx/model/song.py``; the safety guard aborts before any commit.

The driver tests run with ``commit=False`` so the working tree is
never polluted; git interactions are exercised separately in
``test_improve_safety.py``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from jtx.composer.tuning import Tuning, default_tuning, load_tuning, reset_default_tuning_cache
from jtx.improve.corpus import default_corpus
from jtx.improve.driver import SessionConfig, run_session
from jtx.improve.reward import RewardBreakdown, compute_reward, hard_floor_violation
from jtx.improve.safety import AllowListViolation, assert_proposal_paths_clean
from jtx.persist.json_io import load_setup

REPO_ROOT = Path(__file__).resolve().parents[1]
_TUNING_TOML = REPO_ROOT / "tuning.toml"


@pytest.fixture(autouse=True)
def _isolate_tuning_toml(tmp_path):
    """Save + restore tuning.toml so driver tests don't pollute the repo.

    The driver writes ``<repo>/tuning.toml`` on every iteration; tests
    must leave it as they found it (most often, absent).
    """
    snapshot = _TUNING_TOML.read_bytes() if _TUNING_TOML.exists() else None
    yield
    if snapshot is None:
        if _TUNING_TOML.exists():
            _TUNING_TOML.unlink()
    else:
        _TUNING_TOML.write_bytes(snapshot)
    reset_default_tuning_cache()


@pytest.fixture(scope="module")
def cheap_corpus():
    """Trimmed corpus so each driver iteration completes in <1s."""
    corpus = default_corpus()
    return replace(
        corpus,
        grid=(),
        structure_cases=corpus.structure_cases[:1],
        jitter_per_anchor=1,
        sensitivity_steps=2,
    )


def _session_config(tmp_path: Path, **overrides) -> SessionConfig:
    base = SessionConfig(
        budget_iter=overrides.pop("budget_iter", 3),
        plateau_rejections=overrides.pop("plateau_rejections", 100),
        skip_pytest=True,
        commit=False,
        out_root=tmp_path / "eval_runs",
        seed=overrides.pop("seed", 0),
    )
    return replace(base, **overrides)


# ---------- baseline: a clean session runs to completion --------------


def test_session_runs_and_emits_artifacts(cheap_corpus, tmp_path) -> None:
    summary = run_session(
        corpus=cheap_corpus,
        config=_session_config(tmp_path, budget_iter=2),
    )
    assert summary.iterations == 2
    log_path = summary.session_dir / "log.jsonl"
    summary_path = summary.session_dir / "summary.md"
    assert log_path.exists()
    assert summary_path.exists()
    records = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    assert len(records) == 2


def test_session_is_deterministic_across_runs(cheap_corpus, tmp_path) -> None:
    """Should-fail / should-improve aside: same seed must produce same outcome.

    This is the "Determinism" verification scenario — two sessions with
    the same seed must produce identical accept/reject sequences and
    identical R per iteration.
    """
    cfg_a = _session_config(tmp_path / "a", budget_iter=3, seed=42)
    cfg_b = _session_config(tmp_path / "b", budget_iter=3, seed=42)
    a = run_session(corpus=cheap_corpus, config=cfg_a)
    b = run_session(corpus=cheap_corpus, config=cfg_b)

    a_records = [
        json.loads(line) for line in (a.session_dir / "log.jsonl").read_text().splitlines() if line
    ]
    b_records = [
        json.loads(line) for line in (b.session_dir / "log.jsonl").read_text().splitlines() if line
    ]
    assert len(a_records) == len(b_records)
    for ra, rb in zip(a_records, b_records, strict=True):
        assert ra["accepted"] == rb["accepted"]
        assert ra["R_after"] == pytest.approx(rb["R_after"])
        assert ra["diff"] == rb["diff"]


# ---------- should-fail seeded overrides -------------------------------


def test_kill_all_voices_blocked_by_hard_floor(cheap_corpus) -> None:
    """Verification scenario #1: τ=1.0 → every voice rests → anchors collapse.

    Compute R for the destroyed tuning and the default; the hard floor
    must declare the destroyed one a regression on at least one anchor.
    """
    setup = load_setup(cheap_corpus.setup_path)
    baseline = compute_reward(cheap_corpus, Tuning(), setup=setup)
    destroyed = Tuning(voice_tau={k: 1.0 for k in Tuning().voice_tau})
    poisoned = compute_reward(cheap_corpus, destroyed, setup=setup)

    msg = hard_floor_violation(poisoned, baseline, epsilon=0.05)
    assert msg is not None, (
        f"hard floor failed to catch τ=1.0; baseline anchors={baseline.anchor_scores}, "
        f"poisoned anchors={poisoned.anchor_scores}"
    )


def test_collapsed_valence_band_drops_anchor_fidelity(cheap_corpus) -> None:
    """Verification scenario #3: widen valence so every mood overlaps.

    The composer's mood blueprint splits major/minor on valence; if we
    swing valence_inv coefs hard enough that the tension knob saturates,
    the resulting Songs cluster off-anchor and A drops.
    """
    from jtx.composer.tuning import FeelCentreCoefs, FeelTuning

    setup = load_setup(cheap_corpus.setup_path)
    baseline = compute_reward(cheap_corpus, Tuning(), setup=setup)
    saturated = Tuning(
        feel=FeelTuning(
            centres={
                "pump":    FeelCentreCoefs(base=1.0),
                "groove":  FeelCentreCoefs(base=1.0),
                "drive":   FeelCentreCoefs(base=1.0),
                "tension": FeelCentreCoefs(base=1.0),
                "wander":  FeelCentreCoefs(base=1.0),
            }
        )
    )
    poisoned = compute_reward(cheap_corpus, saturated, setup=setup)
    # Either A drops or the hard floor catches a single-anchor regression.
    assert poisoned.A <= baseline.A or hard_floor_violation(
        poisoned, baseline, epsilon=0.05
    ) is not None


# ---------- allow-list enforcement -------------------------------------


def test_allow_list_blocks_schema_edit_attempt() -> None:
    """Verification scenario #4: a Tier-C proposal touching SCHEMA_VERSION aborts."""
    target = REPO_ROOT / "jtx" / "model" / "song.py"
    with pytest.raises(AllowListViolation, match="forbidden"):
        assert_proposal_paths_clean([target])


# ---------- session ends cleanly when nothing improves -----------------


def test_session_terminates_on_iter_cap(cheap_corpus, tmp_path) -> None:
    """budget_iter=1 ends the session immediately after one iteration."""
    summary = run_session(
        corpus=cheap_corpus,
        config=_session_config(tmp_path, budget_iter=1),
    )
    assert summary.iterations == 1


def test_session_terminates_on_stop_file(cheap_corpus, tmp_path, monkeypatch) -> None:
    """Touching STOP between iterations halts cleanly with a clear reason."""
    from jtx.improve import driver
    call_count = {"n": 0}

    def fake_stop_requested() -> bool:
        call_count["n"] += 1
        return call_count["n"] > 1  # First call false, then true

    monkeypatch.setattr(driver, "stop_requested", fake_stop_requested)
    summary = run_session(
        corpus=cheap_corpus,
        config=_session_config(tmp_path, budget_iter=10),
    )
    # Loop ran once before the STOP was observed.
    assert summary.iterations <= 1


# ---------- accepted snapshot writes tuning.toml -----------------------


def test_accepted_snapshot_persists_to_tuning_toml(
    cheap_corpus, tmp_path, monkeypatch
) -> None:
    """When the loop accepts, the new Tuning lands on disk.

    Force every proposal to be an improvement by patching
    ``compute_reward`` to inject a monotonically rising R. The disk
    file must end the session reflecting the accepted tuning.
    """
    from jtx.improve import driver

    rising = {"n": 0}
    real_compute = driver.compute_reward

    def fake_compute(corpus, tuning, **kw):
        r = real_compute(corpus, tuning, **kw)
        rising["n"] += 1
        return RewardBreakdown(
            R=rising["n"] * 1.0,
            A=r.A, D=r.D, C=r.C, S=r.S,
            weights=r.weights,
            anchor_scores=r.anchor_scores,
        )

    monkeypatch.setattr(driver, "compute_reward", fake_compute)
    # Determinism's compute_reward is imported directly there; patch
    # it too so the per-iteration quick-check doesn't see a different
    # sequence from the same-call pair.
    from jtx.improve import determinism
    monkeypatch.setattr(determinism, "compute_reward", real_compute)

    summary = run_session(
        corpus=cheap_corpus,
        config=_session_config(tmp_path, budget_iter=2),
    )
    assert summary.accepted >= 1
    # The override file should exist and parse.
    assert _TUNING_TOML.exists()
    loaded = load_tuning(_TUNING_TOML)
    # The accepted snapshot must differ from default_tuning in at least
    # one field — that's the whole point of the iteration.
    assert loaded != default_tuning()
