"""Tests for the Phase 2a Tier-A override layer.

Two contracts to pin:

1. **Default tuning is byte-identical to pre-Phase-2a.** A composer
   call with no ``tuning`` argument (and no ``tuning.toml`` on disk)
   must produce the same :class:`Song` instance as one with an
   explicit :func:`default_tuning`.
2. **Overrides actually apply.** Each surface — voice_tau, feel,
   filter, pattern_overrides, tempo — has a test that mutates one
   field and asserts the corresponding field of the resulting Song /
   Recipe reflects the change.

The TOML loader is exercised against a temporary file so the
production ``<repo>/tuning.toml`` (which doesn't exist for Phase 2a)
isn't touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.composer import (
    FeelCentreCoefs,
    FeelTuning,
    FilterTuning,
    TempoTuning,
    Tuning,
    WindowOverride,
    build_recipe,
    compose,
    default_tuning,
    load_tuning,
)
from jtx.composer.mood import MoodSpec
from jtx.composer.tuning import (
    _DEFAULT_FEEL_CENTRES,
    _DEFAULT_VOICE_TAU,
    apply_pattern_overrides,
    apply_window_override,
)

_MOOD = MoodSpec(valence=-0.1, energy=0.4)
_COMPOSE_ARGS = ("Tuning Test", "iac", _MOOD, "song")

# Repo-root tuning.toml — present when jtx-improve has accepted a Tier-A
# override. The two byte-identical canaries below pin "no-arg == default"
# behavior; that contract only holds with no override file on disk, so we
# skip those specific tests rather than fight the override layer.
_REPO_TUNING_TOML = Path(__file__).resolve().parents[1] / "tuning.toml"
_skip_if_override = pytest.mark.skipif(
    _REPO_TUNING_TOML.exists(),
    reason="tuning.toml override active — no-arg compose intentionally uses it",
)


# ---------- default ====== byte-identical ----------------------------


@_skip_if_override
def test_compose_without_tuning_arg_matches_explicit_default() -> None:
    """compose() with no tuning kwarg == compose() with default_tuning().

    The "no kwarg" path resolves a cached default; the "explicit" path
    constructs one fresh. Both must produce the same Song. Skipped when
    a non-default ``tuning.toml`` is present — the no-arg path is then
    correctly picking up the override instead of the default.
    """
    a = compose(*_COMPOSE_ARGS, chaos=0.3, texture=0.6, motion=0.7)
    b = compose(
        *_COMPOSE_ARGS, chaos=0.3, texture=0.6, motion=0.7, tuning=default_tuning()
    )
    assert a == b


@_skip_if_override
@pytest.mark.parametrize(
    "fmt", ["sting", "jingle", "loop", "ramp", "song", "anthem"]
)
def test_default_tuning_byte_identical_across_formats(fmt: str) -> None:
    a = compose("Default", "iac", _MOOD, fmt, chaos=0.5, texture=0.5, motion=0.5)
    b = compose(
        "Default", "iac", _MOOD, fmt,
        chaos=0.5, texture=0.5, motion=0.5, tuning=default_tuning(),
    )
    assert a == b


# ---------- load_tuning: file IO --------------------------------------


def test_load_tuning_missing_file_returns_default(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-file.toml"
    assert load_tuning(missing) == default_tuning()


def test_load_tuning_empty_file_returns_default(tmp_path: Path) -> None:
    empty = tmp_path / "tuning.toml"
    empty.write_text("")
    assert load_tuning(empty) == default_tuning()


def test_load_tuning_unknown_top_level_raises(tmp_path: Path) -> None:
    bad = tmp_path / "tuning.toml"
    bad.write_text("[mystery_section]\nfoo = 1\n")
    with pytest.raises(ValueError, match="unknown top-level"):
        load_tuning(bad)


def test_load_tuning_unknown_voice_raises(tmp_path: Path) -> None:
    bad = tmp_path / "tuning.toml"
    bad.write_text("[voice_tau]\nbogus = 0.5\n")
    with pytest.raises(ValueError, match="unknown voice"):
        load_tuning(bad)


def test_load_tuning_unknown_filter_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "tuning.toml"
    bad.write_text("[filter]\nmystery_coef = 0.5\n")
    with pytest.raises(ValueError, match="unknown key"):
        load_tuning(bad)


def test_load_tuning_unknown_feel_coef_raises(tmp_path: Path) -> None:
    bad = tmp_path / "tuning.toml"
    bad.write_text(
        "[feel.centres.pump]\nmystery_term = 0.5\n"
    )
    with pytest.raises(ValueError, match="unknown coef"):
        load_tuning(bad)


def test_load_tuning_partial_overrides_preserve_defaults(tmp_path: Path) -> None:
    """Only specified keys move; everything else mirrors default_tuning."""
    file = tmp_path / "tuning.toml"
    file.write_text(
        "tau_bias_magnitude = 0.30\n"
        "[voice_tau]\n"
        "pad = 0.10\n"
        "[filter]\n"
        "depth_scale = 0.5\n"
    )
    t = load_tuning(file)
    assert t.tau_bias_magnitude == 0.30
    assert t.voice_tau["pad"] == 0.10
    # Other voices kept default τ.
    assert t.voice_tau["bass"] == _DEFAULT_VOICE_TAU["bass"]
    # Filter centre_cc kept default; only depth_scale moved.
    assert t.filter.depth_scale == 0.5
    assert t.filter.centre_cc == 70


def test_load_tuning_pattern_overrides_roundtrip(tmp_path: Path) -> None:
    file = tmp_path / "tuning.toml"
    file.write_text(
        "[pattern_overrides.bass.acid_bass.slide_prob]\n"
        "lo_shift = 0.05\n"
        "hi = 0.8\n"
        "lo_clip = 0.0\n"
        "hi_clip = 1.0\n"
    )
    t = load_tuning(file)
    ov = t.pattern_overrides["bass"]["acid_bass"]["slide_prob"]
    assert ov.lo_shift == 0.05
    assert ov.hi == 0.8
    assert ov.lo_clip == 0.0
    assert ov.hi_clip == 1.0
    assert ov.lo is None
    assert ov.hi_shift == 0.0


def test_load_tuning_filter_subdivisions(tmp_path: Path) -> None:
    file = tmp_path / "tuning.toml"
    file.write_text('[filter]\nsubdivisions = ["8", "16", "32"]\n')
    t = load_tuning(file)
    assert t.filter.subdivisions == ("8", "16", "32")


# ---------- apply_window_override unit tests --------------------------


def test_apply_window_override_replace_then_shift_then_clip() -> None:
    ov = WindowOverride(lo=0.2, hi=0.8, lo_shift=-0.1, hi_shift=0.3, lo_clip=0.0, hi_clip=1.0)
    lo, hi = apply_window_override(0.0, 0.0, ov)
    assert lo == pytest.approx(0.1)
    assert hi == pytest.approx(1.0)  # clipped from 1.1


def test_apply_window_override_swaps_inverted() -> None:
    """If a shift inverts the pair, the helper normalizes it."""
    ov = WindowOverride(lo_shift=0.9)
    lo, hi = apply_window_override(0.1, 0.5, ov)
    assert lo == 0.5
    assert hi == 1.0


def test_apply_pattern_overrides_handles_int_ranges() -> None:
    ints = {"base_vel": (80, 110)}
    overrides = {"base_vel": WindowOverride(lo_shift=-5.0, hi_shift=10.0)}
    _, new_ints = apply_pattern_overrides({}, ints, overrides)
    assert new_ints["base_vel"] == (75, 120)


def test_apply_pattern_overrides_skips_unknown_knob() -> None:
    """Speculative overrides on knobs the algorithm didn't emit are no-ops."""
    floats = {"gate": (0.4, 0.8)}
    overrides = {"slide_prob": WindowOverride(lo_shift=0.1)}
    new_floats, _ = apply_pattern_overrides(floats, {}, overrides)
    assert new_floats == floats


# ---------- end-to-end override effects -------------------------------


def test_voice_tau_override_affects_voice_activation() -> None:
    """Bumping pad τ above texture forces pad → rest."""
    base = build_recipe(_MOOD, "song", chaos=0.0, texture=0.55, motion=0.5)
    assert base.voices["pad"].algorithm == "sustained_chord"

    high_tau = Tuning(voice_tau={**_DEFAULT_VOICE_TAU, "pad": 0.99})
    bumped = build_recipe(_MOOD, "song", chaos=0.0, texture=0.55, motion=0.5, tuning=high_tau)
    assert bumped.voices["pad"].algorithm == "rest"


def test_feel_centre_override_shifts_pump_window() -> None:
    """Dropping pump's base pulls the whole pump window down."""
    base = build_recipe(_MOOD, "song", chaos=0.0, texture=0.5, motion=0.5)
    base_pump_lo, base_pump_hi = base.mood.feel_targets["pump"]

    quiet_pump = Tuning(
        feel=FeelTuning(
            centres={
                **_DEFAULT_FEEL_CENTRES,
                "pump": FeelCentreCoefs(base=0.05),
            }
        )
    )
    shifted = build_recipe(
        _MOOD, "song", chaos=0.0, texture=0.5, motion=0.5, tuning=quiet_pump
    )
    shifted_lo, shifted_hi = shifted.mood.feel_targets["pump"]
    assert shifted_hi < base_pump_hi
    assert shifted_lo < base_pump_lo


def test_filter_depth_scale_override_affects_song_filter_voice() -> None:
    base = compose(*_COMPOSE_ARGS, chaos=0.0, texture=0.5, motion=0.8)
    base_depth = base.voices["filter"].pattern["depth"]

    half_depth = Tuning(filter=FilterTuning(depth_scale=0.4))
    shifted = compose(
        *_COMPOSE_ARGS, chaos=0.0, texture=0.5, motion=0.8, tuning=half_depth
    )
    shifted_depth = shifted.voices["filter"].pattern["depth"]
    assert shifted_depth < base_depth
    assert shifted_depth == pytest.approx(round(0.8 * 0.4, 3))


def test_pattern_override_clamps_acid_bass_gate() -> None:
    """Forcing acid_bass gate to a narrow window shows up in the sampled value."""
    # Use psytrance-ish coords so bass picks acid_bass.
    mood = MoodSpec(valence=-0.25, energy=0.9)
    pinned_gate = Tuning(
        pattern_overrides={
            "bass": {
                "acid_bass": {
                    "gate": WindowOverride(lo=0.42, hi=0.42),
                }
            }
        }
    )
    song = compose(
        "Pinned Gate", "iac", mood, "song",
        chaos=0.0, texture=0.5, motion=0.85, tuning=pinned_gate,
    )
    assert song.voices["bass"].algorithm == "acid_bass"
    # gate is float-sampled; round(0.42, 3) = 0.42 either way.
    assert song.voices["bass"].pattern["gate"] == pytest.approx(0.42)


def test_tempo_override_shifts_song_bpm() -> None:
    """Lowering tempo_centre_base pulls the resulting tempo down."""
    base = compose(*_COMPOSE_ARGS, chaos=0.0, texture=0.5, motion=0.5)
    slow_tuning = Tuning(tempo=TempoTuning(centre_base=60, centre_energy_coef=20))
    slow = compose(
        *_COMPOSE_ARGS, chaos=0.0, texture=0.5, motion=0.5, tuning=slow_tuning
    )
    assert slow.tempo < base.tempo


def test_tau_bias_magnitude_override_changes_pad_activation() -> None:
    """Bigger bias magnitude shifts pad's effective τ further at high motion."""
    # At motion=1.0, pad direction=+1 so bias=+bias_mag*0.5.
    # Default bias_mag=0.15 → bias=+0.075 → τ_eff = 0.5 + 0.075 = 0.575.
    # At texture=0.60, default pad activates.
    default_song = compose(
        *_COMPOSE_ARGS, chaos=0.0, texture=0.60, motion=1.0
    )
    assert default_song.voices["pad"].algorithm == "sustained_chord"

    # bias_mag=0.30 → bias=+0.15 → τ_eff=0.65 > 0.60 → rest.
    bigger_bias = Tuning(tau_bias_magnitude=0.30)
    biased_song = compose(
        *_COMPOSE_ARGS, chaos=0.0, texture=0.60, motion=1.0, tuning=bigger_bias
    )
    assert biased_song.voices["pad"].algorithm == "rest"
