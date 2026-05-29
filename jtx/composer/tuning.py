"""Tier-A override layer for Phase 2 — the closed-loop optimizer's surface.

Phase 2's optimizer (``jtx-improve``, landing in 2b) mutates one file
(``tuning.toml`` at the repo root by default) instead of editing
:mod:`jtx.composer.recipe` / :mod:`jtx.composer.compose` source on
every iteration. Those modules consume a :class:`Tuning` object whose
fields default to the constants currently inlined in their code; a
composer call with the default :class:`Tuning` emits byte-identical
:class:`~jtx.model.Song` instances to pre-Phase-2a behavior.

Scope mirrors the Tier-A surfaces named in the Phase 2 plan:

* ``_VOICE_TAU`` palette-activation thresholds + the motion-bias
  magnitude (per :data:`_DEFAULT_VOICE_TAU`).
* ``_filter_pattern`` constants in :mod:`jtx.composer.compose`
  (subdivisions, depth scale, centre CC, half-range coefficients,
  motion-band split points).
* ``_mood_blueprint`` tempo + feel-target windows (linear
  coefficients per feel knob).
* ``_voice_pattern_ranges`` outputs — a per-``(voice, algorithm,
  knob)`` :class:`WindowOverride` table that post-processes any
  emitted ``(lo, hi)`` window without rewriting the underlying
  formulas.

Tier B (algorithm shortlists) and Tier C (algorithm internals) are
deliberately out of scope for Phase 2a; they get their own phases.

The TOML loader is strict: unknown top-level sections or unknown keys
inside the typed sub-sections raise :class:`ValueError`. This lets a
typo in ``tuning.toml`` fail loudly rather than being silently
ignored by the optimizer.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

# ----------------------------------------------------------------------
# Defaults — mirror the constants inlined in recipe.py / compose.py.
#
# Duplicating these here keeps tuning.py importable without forcing a
# cycle through recipe.py. The cross-check is enforced in tests:
# ``test_tuning_defaults_match_recipe`` asserts these values match
# what recipe.py uses when no override is loaded.
# ----------------------------------------------------------------------

_DEFAULT_VOICE_TAU: dict[str, float] = {
    "drumkit": 0.00,
    "bass": 0.00,
    "stabs": 0.05,
    "lead": 0.20,
    "arp": 0.30,
    "sub": 0.40,
    "pad": 0.50,
    "chord": 0.60,
    "fx": 0.70,
}

_DEFAULT_FILTER_SUBDIVISIONS: tuple[str, str, str] = ("4", "16", "16t")


@dataclass(frozen=True)
class FilterTuning:
    """Constants used by ``_filter_pattern`` in :mod:`jtx.composer.compose`.

    ``subdivisions`` is the 3-tuple of CC LFO subdivisions picked by
    motion band (low / mid / high). ``motion_band_low`` and
    ``motion_band_high`` are the band split thresholds (motion in
    ``[0, 1]``). ``depth_scale`` multiplies motion to produce the
    final LFO depth. ``centre_cc`` is the cutoff window centre;
    ``half_range_base`` + ``half_range_motion_scale`` set the
    minimum half-range plus the motion-driven addition.
    """

    subdivisions: tuple[str, str, str] = _DEFAULT_FILTER_SUBDIVISIONS
    depth_scale: float = 0.95
    centre_cc: int = 70
    half_range_base: int = 8
    half_range_motion_scale: int = 52
    motion_band_low: float = 0.34
    motion_band_high: float = 0.67


@dataclass(frozen=True)
class TempoTuning:
    """Constants used in tempo computation in ``_mood_blueprint``.

    ``centre_base`` + ``centre_energy_coef * energy`` gives the
    tempo centre in BPM (energy normalized to ``[0, 1]``).
    ``spread_base`` + ``spread_chaos_coef * chaos`` gives the half-
    width of the tempo window. The result is clamped to
    ``[bpm_floor, bpm_ceiling]``.
    """

    centre_base: int = 80
    centre_energy_coef: int = 72
    spread_base: int = 6
    spread_chaos_coef: int = 8
    bpm_floor: int = 60
    bpm_ceiling: int = 180


@dataclass(frozen=True)
class FeelCentreCoefs:
    """Linear coefficients for one feel-knob centre formula.

    The centre is computed as a linear combination of these terms;
    unused terms default to zero. ``energy`` / ``texture`` /
    ``motion`` use the raw input values (all in ``[0, 1]``).
    ``valence_abs_inv`` multiplies ``(1.0 - abs(mood.valence))`` —
    peaks at neutral valence. ``valence_inv`` multiplies
    ``(1.0 - valence_norm)`` where valence_norm is in ``[0, 1]`` —
    higher when valence is low. ``chaos`` multiplies chaos directly.

    The final centre is clamped to ``[0, 1]`` and a window of
    ``± (window_half_base + chaos * window_half_chaos_coef)`` is
    returned around it.
    """

    base: float = 0.0
    energy: float = 0.0
    texture: float = 0.0
    motion: float = 0.0
    valence_abs_inv: float = 0.0
    valence_inv: float = 0.0
    chaos: float = 0.0


# Defaults below exactly reproduce the formulas in recipe.py's
# ``_mood_blueprint``. Don't change one without changing the other.
_DEFAULT_FEEL_CENTRES: dict[str, FeelCentreCoefs] = {
    "pump":    FeelCentreCoefs(base=0.25, energy=0.35, texture=0.20, motion=-0.20),
    "groove":  FeelCentreCoefs(base=0.20, valence_abs_inv=0.30, motion=0.10),
    "drive":   FeelCentreCoefs(base=0.20, energy=0.45, motion=0.20),
    "tension": FeelCentreCoefs(base=0.20, valence_inv=0.45, chaos=0.15),
    "wander":  FeelCentreCoefs(base=0.10, chaos=0.35, motion=0.20),
}


@dataclass(frozen=True)
class FeelTuning:
    """Coefficients used by ``_mood_blueprint`` for feel-target windows."""

    centres: dict[str, FeelCentreCoefs] = field(
        default_factory=lambda: dict(_DEFAULT_FEEL_CENTRES)
    )
    window_half_base: float = 0.05
    window_half_chaos_coef: float = 0.12


@dataclass(frozen=True)
class WindowOverride:
    """Override a ``(lo, hi)`` pattern range emitted by ``_voice_pattern_ranges``.

    Application order, per end:

    1. ``lo`` / ``hi`` (if not ``None``) *replace* the algorithm's
       value.
    2. ``lo_shift`` / ``hi_shift`` are then added.
    3. ``lo_clip`` / ``hi_clip`` (if not ``None``) clamp the result.
    4. If shifts crossed ``lo`` past ``hi`` (or vice versa), the
       pair is swapped so callers always see a normalized window.

    Integer windows from ``_voice_pattern_ranges`` are rounded after
    the float math; supply float-valued shifts even for int knobs.
    """

    lo: float | None = None
    hi: float | None = None
    lo_shift: float = 0.0
    hi_shift: float = 0.0
    lo_clip: float | None = None
    hi_clip: float | None = None


# Pattern override table: ``[voice][algorithm][knob] -> WindowOverride``.
# Keyed three levels deep so a single voice running different algorithms
# picks up different overrides without collision (and so the same
# algorithm running on two voices can be tuned independently).
PatternOverrideTable = dict[str, dict[str, dict[str, WindowOverride]]]


@dataclass(frozen=True)
class Tuning:
    """Tier-A tuning overrides consumed by recipe.py + compose.py.

    Defaults reproduce the pre-Phase-2a hardcoded behavior exactly;
    a composer call with :func:`default_tuning` emits byte-identical
    :class:`~jtx.model.Song` instances. The optimizer (Phase 2b)
    writes derived :class:`Tuning` instances to ``tuning.toml``;
    :mod:`jtx.composer.recipe` and :mod:`jtx.composer.compose` read
    them in via :func:`load_tuning`.
    """

    voice_tau: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_VOICE_TAU)
    )
    tau_bias_magnitude: float = 0.15
    filter: FilterTuning = field(default_factory=FilterTuning)
    tempo: TempoTuning = field(default_factory=TempoTuning)
    feel: FeelTuning = field(default_factory=FeelTuning)
    pattern_overrides: PatternOverrideTable = field(default_factory=dict)

    def tau_for(self, voice: str) -> float:
        """Effective τ for *voice* before motion bias."""
        return self.voice_tau.get(voice, _DEFAULT_VOICE_TAU.get(voice, 0.0))

    def pattern_overrides_for(
        self, voice: str, algorithm: str
    ) -> Mapping[str, WindowOverride]:
        """The ``WindowOverride`` map for one ``(voice, algorithm)`` cell."""
        return self.pattern_overrides.get(voice, {}).get(algorithm, {})


def default_tuning() -> Tuning:
    """The pre-Phase-2a defaults.

    Returns a fresh :class:`Tuning` so callers can mutate the
    returned mutable fields (``voice_tau`` dict, etc.) without
    polluting later constructions.
    """
    return Tuning()


# ----------------------------------------------------------------------
# TOML loader — strict schema; unknown sections / keys raise.
# ----------------------------------------------------------------------

# Repo-root relative; tests can pass an explicit path to bypass.
_DEFAULT_TOML_PATH = Path(__file__).resolve().parents[2] / "tuning.toml"


@lru_cache(maxsize=1)
def _cached_default_tuning() -> Tuning:
    """Cache the disk-loaded default so every compose() call doesn't re-read.

    The cache key is implicit (no args); call :func:`reset_default_tuning_cache`
    in tests that mutate the on-disk file.
    """
    return load_tuning()


def reset_default_tuning_cache() -> None:
    """Drop the lru-cache entry so the next default-Tuning load re-reads disk.

    Tests that write a temporary ``tuning.toml`` should call this
    before invoking :func:`compose` without an explicit ``tuning``.
    """
    _cached_default_tuning.cache_clear()


def load_tuning(path: Path | None = None) -> Tuning:
    """Load Tier-A overrides from *path*; missing keys keep defaults.

    If *path* is ``None``, defaults to ``<repo>/tuning.toml``. If the
    file doesn't exist, returns :func:`default_tuning` — production
    callers don't need to ship the override file. Unknown top-level
    sections or unknown keys inside a typed sub-section raise
    :class:`ValueError`.
    """
    actual = path or _DEFAULT_TOML_PATH
    if not actual.exists():
        return default_tuning()
    with actual.open("rb") as fh:
        data = tomllib.load(fh)
    return _from_dict(data)


_KNOWN_TOP_LEVEL = frozenset(
    {
        "voice_tau",
        "tau_bias_magnitude",
        "filter",
        "tempo",
        "feel",
        "pattern_overrides",
    }
)


def _from_dict(data: Mapping[str, Any]) -> Tuning:
    """Parse a TOML-loaded dict into a Tuning. Strict on unknown keys."""
    unknown = set(data.keys()) - _KNOWN_TOP_LEVEL
    if unknown:
        raise ValueError(
            f"tuning.toml: unknown top-level section(s): {sorted(unknown)}"
        )

    base = default_tuning()

    voice_tau = dict(base.voice_tau)
    if "voice_tau" in data:
        section = _require_mapping("voice_tau", data["voice_tau"])
        for voice, value in section.items():
            if voice not in _DEFAULT_VOICE_TAU:
                raise ValueError(f"voice_tau: unknown voice {voice!r}")
            voice_tau[voice] = float(value)

    tau_bias_magnitude = float(data.get("tau_bias_magnitude", base.tau_bias_magnitude))

    filter_t = base.filter
    if "filter" in data:
        filter_t = _replace_dataclass(
            filter_t, _require_mapping("filter", data["filter"]), label="filter"
        )

    tempo_t = base.tempo
    if "tempo" in data:
        tempo_t = _replace_dataclass(
            tempo_t, _require_mapping("tempo", data["tempo"]), label="tempo"
        )

    feel_t = base.feel
    if "feel" in data:
        feel_t = _build_feel(_require_mapping("feel", data["feel"]), base.feel)

    pattern_overrides: PatternOverrideTable = {}
    if "pattern_overrides" in data:
        pattern_overrides = _build_pattern_overrides(
            _require_mapping("pattern_overrides", data["pattern_overrides"])
        )

    return Tuning(
        voice_tau=voice_tau,
        tau_bias_magnitude=tau_bias_magnitude,
        filter=filter_t,
        tempo=tempo_t,
        feel=feel_t,
        pattern_overrides=pattern_overrides,
    )


def _require_mapping(label: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}: expected a table, got {type(value).__name__}")
    return value


_T = TypeVar("_T")


def _replace_dataclass(instance: _T, section: Mapping[str, Any], *, label: str) -> _T:
    """Build a new frozen-dataclass instance with *section* keys overriding."""
    valid = {f.name for f in fields(instance)}  # type: ignore[arg-type]
    unknown = set(section.keys()) - valid
    if unknown:
        raise ValueError(f"{label}: unknown key(s) {sorted(unknown)}")
    coerced: dict[str, Any] = {}
    for f in fields(instance):  # type: ignore[arg-type]
        if f.name not in section:
            continue
        value = section[f.name]
        if f.type in ("tuple[str, str, str]",) or f.name == "subdivisions":
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                raise ValueError(
                    f"{label}.{f.name}: expected a 3-element array, got {value!r}"
                )
            coerced[f.name] = (str(value[0]), str(value[1]), str(value[2]))
        elif f.type == "int":
            coerced[f.name] = int(value)
        elif f.type == "float":
            coerced[f.name] = float(value)
        else:
            coerced[f.name] = value
    return replace(instance, **coerced)  # type: ignore[type-var]


def _build_feel(section: Mapping[str, Any], base: FeelTuning) -> FeelTuning:
    valid_top = {"centres", "window_half_base", "window_half_chaos_coef"}
    unknown = set(section.keys()) - valid_top
    if unknown:
        raise ValueError(f"feel: unknown key(s) {sorted(unknown)}")

    window_half_base = float(section.get("window_half_base", base.window_half_base))
    window_half_chaos_coef = float(
        section.get("window_half_chaos_coef", base.window_half_chaos_coef)
    )

    centres = dict(base.centres)
    if "centres" in section:
        centres_section = _require_mapping("feel.centres", section["centres"])
        valid_coef_keys = {f.name for f in fields(FeelCentreCoefs)}
        for knob, knob_section in centres_section.items():
            if knob not in _DEFAULT_FEEL_CENTRES:
                raise ValueError(f"feel.centres: unknown feel knob {knob!r}")
            knob_map = _require_mapping(f"feel.centres.{knob}", knob_section)
            unknown_coefs = set(knob_map.keys()) - valid_coef_keys
            if unknown_coefs:
                raise ValueError(
                    f"feel.centres.{knob}: unknown coef(s) {sorted(unknown_coefs)}"
                )
            existing = centres[knob]
            replacements = {k: float(v) for k, v in knob_map.items()}
            centres[knob] = replace(existing, **replacements)

    return FeelTuning(
        centres=centres,
        window_half_base=window_half_base,
        window_half_chaos_coef=window_half_chaos_coef,
    )


def _build_pattern_overrides(section: Mapping[str, Any]) -> PatternOverrideTable:
    table: PatternOverrideTable = {}
    valid_keys = {f.name for f in fields(WindowOverride)}
    for voice, voice_section in section.items():
        voice_map = _require_mapping(f"pattern_overrides.{voice}", voice_section)
        for algorithm, algo_section in voice_map.items():
            algo_map = _require_mapping(
                f"pattern_overrides.{voice}.{algorithm}", algo_section
            )
            for knob, knob_section in algo_map.items():
                knob_map = _require_mapping(
                    f"pattern_overrides.{voice}.{algorithm}.{knob}", knob_section
                )
                unknown_keys = set(knob_map.keys()) - valid_keys
                if unknown_keys:
                    raise ValueError(
                        f"pattern_overrides.{voice}.{algorithm}.{knob}: "
                        f"unknown key(s) {sorted(unknown_keys)}"
                    )
                coerced: dict[str, Any] = {}
                for k in valid_keys:
                    if k not in knob_map:
                        continue
                    v = knob_map[k]
                    coerced[k] = float(v) if v is not None else None
                ov = WindowOverride(**coerced)
                table.setdefault(voice, {}).setdefault(algorithm, {})[knob] = ov
    return table


# ----------------------------------------------------------------------
# Window-override application (used by recipe.py)
# ----------------------------------------------------------------------


def apply_window_override(
    lo: float, hi: float, override: WindowOverride
) -> tuple[float, float]:
    """Apply *override* to ``(lo, hi)``; returns the post-override pair.

    Per the :class:`WindowOverride` docstring: replace → shift →
    clip → swap. Pure function — the recipe layer wraps integer
    handling separately.
    """
    new_lo = override.lo if override.lo is not None else lo
    new_hi = override.hi if override.hi is not None else hi
    new_lo += override.lo_shift
    new_hi += override.hi_shift
    if override.lo_clip is not None:
        new_lo = max(override.lo_clip, new_lo)
    if override.hi_clip is not None:
        new_hi = min(override.hi_clip, new_hi)
    if new_lo > new_hi:
        new_lo, new_hi = new_hi, new_lo
    return new_lo, new_hi


def apply_pattern_overrides(
    floats: dict[str, tuple[float, float]],
    ints: dict[str, tuple[int, int]],
    overrides: Mapping[str, WindowOverride],
) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[int, int]]]:
    """Apply *overrides* to the float/int range dicts in place-equivalent.

    Knobs in *overrides* that don't appear in *floats* or *ints* are
    silently skipped — the algorithm may simply not have emitted that
    knob this composition (e.g. ``cycle`` only appears for psy-rolling
    acid). The optimizer can write speculative overrides without
    being punished for them.
    """
    if not overrides:
        return floats, ints
    new_floats = dict(floats)
    new_ints = dict(ints)
    for knob, ov in overrides.items():
        if knob in new_floats:
            lo, hi = new_floats[knob]
            new_floats[knob] = apply_window_override(lo, hi, ov)
        elif knob in new_ints:
            lo_i, hi_i = new_ints[knob]
            lo_f, hi_f = apply_window_override(float(lo_i), float(hi_i), ov)
            new_ints[knob] = (int(round(lo_f)), int(round(hi_f)))
    return new_floats, new_ints


__all__ = [
    "FeelCentreCoefs",
    "FeelTuning",
    "FilterTuning",
    "PatternOverrideTable",
    "TempoTuning",
    "Tuning",
    "WindowOverride",
    "apply_pattern_overrides",
    "apply_window_override",
    "default_tuning",
    "load_tuning",
    "reset_default_tuning_cache",
]
