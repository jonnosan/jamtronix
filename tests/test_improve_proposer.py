"""Tests for the Tier-A proposer + Tuning ↔ TOML serializer."""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.composer.tuning import (
    Tuning,
    WindowOverride,
    default_tuning,
    load_tuning,
)
from jtx.improve.proposer import (
    ParamSpec,
    RandomWalkProposer,
    default_param_specs,
    get_param,
    pattern_param_specs,
    set_param,
    tuning_to_toml,
    write_tuning_toml,
)

# ---------- ParamSpec / get_param / set_param --------------------------


def test_default_param_specs_covers_all_categories() -> None:
    specs = default_param_specs()
    paths = {s.path for s in specs}
    assert "voice_tau.bass" in paths
    assert "tau_bias_magnitude" in paths
    assert "filter.depth_scale" in paths
    assert "tempo.centre_base" in paths
    assert "feel.window_half_base" in paths
    assert "feel.centres.pump.energy" in paths


def test_get_param_reads_voice_tau() -> None:
    t = Tuning()
    assert get_param(t, "voice_tau.bass") == 0.0


def test_set_param_returns_new_tuning() -> None:
    t = Tuning()
    new_t = set_param(t, "filter.depth_scale", 0.5)
    assert t.filter.depth_scale == 0.95  # unchanged
    assert new_t.filter.depth_scale == 0.5


def test_set_param_int_coerces() -> None:
    t = Tuning()
    new_t = set_param(t, "filter.centre_cc", 71.7)
    assert new_t.filter.centre_cc == 72


def test_set_param_feel_centres() -> None:
    t = Tuning()
    new_t = set_param(t, "feel.centres.pump.energy", 0.5)
    assert new_t.feel.centres["pump"].energy == 0.5
    # Other coefs untouched.
    assert new_t.feel.centres["pump"].base == 0.25


def test_set_param_pattern_overrides_creates_table_entry() -> None:
    t = Tuning()
    new_t = set_param(t, "pattern_overrides.bass.acid_bass.gate.lo_shift", 0.1)
    ov = new_t.pattern_overrides["bass"]["acid_bass"]["gate"]
    assert ov.lo_shift == pytest.approx(0.1)


def test_pattern_param_specs_emits_lo_hi_shift_pair() -> None:
    specs = pattern_param_specs("bass", "acid_bass", "gate")
    paths = {s.path for s in specs}
    assert paths == {
        "pattern_overrides.bass.acid_bass.gate.lo_shift",
        "pattern_overrides.bass.acid_bass.gate.hi_shift",
    }


# ---------- RandomWalkProposer ----------------------------------------


def test_proposer_is_deterministic_for_same_seed() -> None:
    a = RandomWalkProposer(default_param_specs(), seed=7)
    b = RandomWalkProposer(default_param_specs(), seed=7)
    pa = a.propose(Tuning())
    pb = b.propose(Tuning())
    assert pa.diff == pb.diff


def test_proposer_diverges_for_different_seeds() -> None:
    a = RandomWalkProposer(default_param_specs(), seed=7)
    b = RandomWalkProposer(default_param_specs(), seed=8)
    pa = a.propose(Tuning())
    pb = b.propose(Tuning())
    assert pa.diff != pb.diff


def test_proposer_respects_params_per_step() -> None:
    p = RandomWalkProposer(default_param_specs(), seed=7, params_per_step=2)
    diffs = []
    current = Tuning()
    for _ in range(5):
        prop = p.propose(current)
        diffs.append(len(prop.diff))
        current = prop.tuning
    # Each proposal touches at most 2 distinct params (sometimes one
    # is clipped or already at the bound → effective no-op → < 2).
    assert max(diffs) <= 2


def test_proposer_cools_over_iterations() -> None:
    p = RandomWalkProposer(default_param_specs(), seed=0, temperature=1.0, cooling=0.5)
    t_initial = p.temperature
    p.propose(Tuning())
    assert p.temperature < t_initial


def test_proposer_clips_to_param_range() -> None:
    """Forcing a huge perturbation must clip to [lo, hi]."""
    tight_specs = [ParamSpec("voice_tau.bass", lo=0.0, hi=0.1, step_scale=10.0)]
    p = RandomWalkProposer(tight_specs, seed=0, params_per_step=1)
    prop = p.propose(Tuning())
    new_val = prop.tuning.voice_tau["bass"]
    assert 0.0 <= new_val <= 0.1


# ---------- TOML round-trip --------------------------------------------


def test_default_tuning_round_trip(tmp_path: Path) -> None:
    """Serializing + reloading the default Tuning yields an identical object."""
    path = tmp_path / "tuning.toml"
    write_tuning_toml(default_tuning(), path)
    loaded = load_tuning(path)
    assert loaded == default_tuning()


def test_round_trip_preserves_perturbed_values_to_six_digits(tmp_path: Path) -> None:
    """Round-trip precision: every scalar agrees to 6 decimal places."""
    p = RandomWalkProposer(default_param_specs(), seed=11)
    prop = p.propose(Tuning())
    path = tmp_path / "tuning.toml"
    write_tuning_toml(prop.tuning, path)
    loaded = load_tuning(path)
    for path_key in prop.diff:
        orig = get_param(prop.tuning, path_key)
        new = get_param(loaded, path_key)
        assert orig is not None and new is not None
        assert abs(orig - new) < 1e-5


def test_round_trip_preserves_pattern_overrides(tmp_path: Path) -> None:
    pinned = Tuning(
        pattern_overrides={
            "bass": {"acid_bass": {"gate": WindowOverride(lo=0.4, hi=0.5, lo_shift=0.05)}}
        }
    )
    path = tmp_path / "tuning.toml"
    write_tuning_toml(pinned, path)
    loaded = load_tuning(path)
    ov = loaded.pattern_overrides["bass"]["acid_bass"]["gate"]
    assert ov.lo == pytest.approx(0.4)
    assert ov.hi == pytest.approx(0.5)
    assert ov.lo_shift == pytest.approx(0.05)
    # Unset fields stay None — the serializer omits them.
    assert ov.lo_clip is None


def test_serializer_emits_top_level_keys_before_tables() -> None:
    """``tau_bias_magnitude`` must precede any table header so it stays top-level."""
    text = tuning_to_toml(Tuning())
    bias_pos = text.index("tau_bias_magnitude")
    table_pos = text.index("[voice_tau]")
    assert bias_pos < table_pos
