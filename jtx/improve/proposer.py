"""Tier-A numeric proposer + Tuning ↔ TOML serializer.

Tier A covers the continuous Tier-A surface named in the Phase 2 plan:

* ``voice_tau`` (one float per voice)
* ``tau_bias_magnitude``
* :class:`~jtx.composer.tuning.FilterTuning` numeric fields
* :class:`~jtx.composer.tuning.TempoTuning` numeric fields
* :class:`~jtx.composer.tuning.FeelTuning` centre coefficients +
  window widths
* ``pattern_overrides`` ``lo`` / ``hi`` / ``lo_shift`` / ``hi_shift``
  for seeded ``(voice, algorithm, knob)`` cells

The proposer holds a ``current best`` Tuning and a deterministic
:class:`random.Random`. Each :meth:`RandomWalkProposer.propose` picks
a random subset of parameters, draws a gaussian perturbation per
parameter (clipped to the parameter's valid range), and returns the
mutated Tuning. Same RNG state → identical proposal sequence, which
keeps the loop reproducible across sessions.

Tier B (algorithm shortlists) and Tier C (algorithm internals) are
out of scope for 2b; the proposer abstract base class is here so 2c
can add a categorical proposer without restructuring the loop.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import dataclass, fields, replace
from pathlib import Path

from jtx.composer.tuning import (
    _DEFAULT_FEEL_CENTRES,
    _DEFAULT_VOICE_TAU,
    FeelCentreCoefs,
    FeelTuning,
    FilterTuning,
    TempoTuning,
    Tuning,
    WindowOverride,
)

# ----------------------------------------------------------------------
# Parameter specs — describes one tunable scalar.
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    """One tunable scalar.

    *path* is a human-readable identifier the log uses (e.g.
    ``voice_tau.pad`` or ``filter.depth_scale``). *lo* / *hi* clip the
    perturbed value. *step_scale* is the stddev of the gaussian
    perturbation — kept proportional to the parameter's natural range
    so a single :meth:`RandomWalkProposer.propose` doesn't blow any
    one knob to extremes.
    """

    path: str
    lo: float
    hi: float
    step_scale: float
    is_int: bool = False


_VOICE_TAU_SCALE = 0.05
_VOICES = tuple(_DEFAULT_VOICE_TAU.keys())


def _voice_tau_specs() -> list[ParamSpec]:
    return [
        ParamSpec(f"voice_tau.{v}", lo=0.0, hi=1.0, step_scale=_VOICE_TAU_SCALE)
        for v in _VOICES
    ]


def _filter_specs() -> list[ParamSpec]:
    return [
        ParamSpec("filter.depth_scale",            lo=0.0,  hi=1.5,  step_scale=0.05),
        ParamSpec("filter.centre_cc",              lo=20,   hi=120,  step_scale=4.0, is_int=True),
        ParamSpec("filter.half_range_base",        lo=0,    hi=40,   step_scale=2.0, is_int=True),
        ParamSpec("filter.half_range_motion_scale",lo=0,    hi=80,   step_scale=4.0, is_int=True),
        ParamSpec("filter.motion_band_low",        lo=0.05, hi=0.55, step_scale=0.03),
        ParamSpec("filter.motion_band_high",       lo=0.50, hi=0.95, step_scale=0.03),
    ]


def _tempo_specs() -> list[ParamSpec]:
    return [
        ParamSpec("tempo.centre_base",        lo=40,  hi=160, step_scale=3.0, is_int=True),
        ParamSpec("tempo.centre_energy_coef", lo=0,   hi=160, step_scale=4.0, is_int=True),
        ParamSpec("tempo.spread_base",        lo=0,   hi=30,  step_scale=1.0, is_int=True),
        ParamSpec("tempo.spread_chaos_coef",  lo=0,   hi=40,  step_scale=1.0, is_int=True),
        ParamSpec("tempo.bpm_floor",          lo=40,  hi=120, step_scale=2.0, is_int=True),
        ParamSpec("tempo.bpm_ceiling",        lo=120, hi=240, step_scale=2.0, is_int=True),
    ]


def _feel_specs() -> list[ParamSpec]:
    specs: list[ParamSpec] = [
        ParamSpec("feel.window_half_base",       lo=0.0, hi=0.4, step_scale=0.02),
        ParamSpec("feel.window_half_chaos_coef", lo=0.0, hi=0.5, step_scale=0.02),
    ]
    for knob in _DEFAULT_FEEL_CENTRES:
        for coef in (
            "base", "energy", "texture", "motion",
            "valence_abs_inv", "valence_inv", "chaos",
        ):
            specs.append(
                ParamSpec(
                    f"feel.centres.{knob}.{coef}",
                    lo=-1.0, hi=1.0, step_scale=0.04,
                )
            )
    return specs


def default_param_specs() -> tuple[ParamSpec, ...]:
    """All non-pattern Tier-A tunable scalars.

    Pattern overrides are seeded explicitly by the corpus / driver
    (the optimizer doesn't enumerate every possible ``(voice,
    algorithm, knob)`` triple, which is open-ended). Use
    :func:`pattern_param_specs` to add a controlled subset when a
    session wants to tune them.
    """
    specs: list[ParamSpec] = []
    specs.extend(_voice_tau_specs())
    specs.append(ParamSpec("tau_bias_magnitude", lo=0.0, hi=0.5, step_scale=0.03))
    specs.extend(_filter_specs())
    specs.extend(_tempo_specs())
    specs.extend(_feel_specs())
    return tuple(specs)


def pattern_param_specs(
    voice: str, algorithm: str, knob: str
) -> tuple[ParamSpec, ...]:
    """Tunable scalars for one ``(voice, algorithm, knob)`` cell.

    Generates a ``lo_shift`` / ``hi_shift`` pair (the default override
    fields) at a small step scale. The replace + clip fields stay
    out of the search space — they're intended for hand-pinning.
    """
    base = f"pattern_overrides.{voice}.{algorithm}.{knob}"
    return (
        ParamSpec(f"{base}.lo_shift", lo=-0.5, hi=0.5, step_scale=0.03),
        ParamSpec(f"{base}.hi_shift", lo=-0.5, hi=0.5, step_scale=0.03),
    )


# ----------------------------------------------------------------------
# Tuning ↔ flat dict get/set
# ----------------------------------------------------------------------


def get_param(tuning: Tuning, path: str) -> float | None:
    """Read a scalar by dotted *path*. ``None`` if the path is unset."""
    parts = path.split(".")
    if parts[0] == "voice_tau" and len(parts) == 2:
        return float(tuning.voice_tau.get(parts[1], _DEFAULT_VOICE_TAU.get(parts[1], 0.0)))
    if path == "tau_bias_magnitude":
        return float(tuning.tau_bias_magnitude)
    if parts[0] == "filter" and len(parts) == 2:
        return float(getattr(tuning.filter, parts[1]))
    if parts[0] == "tempo" and len(parts) == 2:
        return float(getattr(tuning.tempo, parts[1]))
    if parts[0] == "feel":
        return _get_feel(tuning.feel, parts[1:])
    if parts[0] == "pattern_overrides" and len(parts) == 5:
        _, voice, algo, knob, attr = parts
        ov = tuning.pattern_overrides.get(voice, {}).get(algo, {}).get(knob)
        if ov is None:
            return 0.0  # absent = no shift
        val = getattr(ov, attr, None)
        if val is None:
            return 0.0
        return float(val)
    raise KeyError(f"Unknown tuning path: {path!r}")


def _get_feel(feel: FeelTuning, parts: list[str]) -> float | None:
    if not parts:
        raise KeyError("feel: missing key")
    head = parts[0]
    if head == "window_half_base":
        return float(feel.window_half_base)
    if head == "window_half_chaos_coef":
        return float(feel.window_half_chaos_coef)
    if head == "centres" and len(parts) == 3:
        knob, coef = parts[1], parts[2]
        coefs = feel.centres.get(knob)
        if coefs is None:
            return 0.0
        return float(getattr(coefs, coef))
    raise KeyError(f"Unknown feel path: feel.{'.'.join(parts)}")


def set_param(tuning: Tuning, path: str, value: float) -> Tuning:
    """Return a new :class:`Tuning` with *path* set to *value*."""
    parts = path.split(".")
    if parts[0] == "voice_tau" and len(parts) == 2:
        new_taus = dict(tuning.voice_tau)
        new_taus[parts[1]] = float(value)
        return replace(tuning, voice_tau=new_taus)
    if path == "tau_bias_magnitude":
        return replace(tuning, tau_bias_magnitude=float(value))
    if parts[0] == "filter" and len(parts) == 2:
        new_filter = replace(tuning.filter, **{parts[1]: _maybe_int(value, parts[1])})
        return replace(tuning, filter=new_filter)
    if parts[0] == "tempo" and len(parts) == 2:
        new_tempo = replace(tuning.tempo, **{parts[1]: _maybe_int(value, parts[1])})
        return replace(tuning, tempo=new_tempo)
    if parts[0] == "feel":
        return replace(tuning, feel=_set_feel(tuning.feel, parts[1:], value))
    if parts[0] == "pattern_overrides" and len(parts) == 5:
        _, voice, algo, knob, attr = parts
        return _set_pattern(tuning, voice, algo, knob, attr, float(value))
    raise KeyError(f"Unknown tuning path: {path!r}")


def _maybe_int(value: float, field_name: str) -> float | int:
    """FilterTuning + TempoTuning store some fields as int; coerce here."""
    int_fields = {
        "centre_cc",
        "half_range_base",
        "half_range_motion_scale",
        "centre_base",
        "centre_energy_coef",
        "spread_base",
        "spread_chaos_coef",
        "bpm_floor",
        "bpm_ceiling",
    }
    if field_name in int_fields:
        return int(round(value))
    return float(value)


def _set_feel(feel: FeelTuning, parts: list[str], value: float) -> FeelTuning:
    head = parts[0]
    if head == "window_half_base":
        return replace(feel, window_half_base=float(value))
    if head == "window_half_chaos_coef":
        return replace(feel, window_half_chaos_coef=float(value))
    if head == "centres" and len(parts) == 3:
        knob, coef = parts[1], parts[2]
        current = dict(feel.centres)
        coefs = current.get(knob, FeelCentreCoefs())
        current[knob] = replace(coefs, **{coef: float(value)})
        return replace(feel, centres=current)
    raise KeyError(f"Unknown feel path: feel.{'.'.join(parts)}")


def _set_pattern(
    tuning: Tuning, voice: str, algo: str, knob: str, attr: str, value: float
) -> Tuning:
    table = {
        v: {a: dict(ks) for a, ks in algos.items()}
        for v, algos in tuning.pattern_overrides.items()
    }
    table.setdefault(voice, {}).setdefault(algo, {})
    existing = table[voice][algo].get(knob, WindowOverride())
    table[voice][algo][knob] = replace(existing, **{attr: value})
    return replace(tuning, pattern_overrides=table)


# ----------------------------------------------------------------------
# Proposer
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    """One iteration's mutation — the new Tuning + a per-path diff.

    *diff* keys are dotted paths from :class:`ParamSpec.path`; values
    are ``(old, new)`` pairs. The log records this so a session can
    be re-played from the JSONL without re-running the proposer.
    """

    tuning: Tuning
    diff: dict[str, tuple[float, float]]


class RandomWalkProposer:
    """Gaussian-perturbation proposer over :class:`ParamSpec` lists.

    Each :meth:`propose` picks ``params_per_step`` random scalars,
    draws a step from ``Normal(0, spec.step_scale * temperature)``,
    clips to ``[lo, hi]``, and writes back into the Tuning. Temperature
    decays exponentially so later iterations focus on small refinements
    around an already-good point.
    """

    def __init__(
        self,
        specs: Iterable[ParamSpec],
        *,
        seed: int = 0,
        params_per_step: int = 3,
        temperature: float = 1.0,
        cooling: float = 0.97,
    ) -> None:
        self._specs = tuple(specs)
        if not self._specs:
            raise ValueError("RandomWalkProposer requires at least one ParamSpec")
        self._rng = random.Random(seed)
        self._params_per_step = max(1, params_per_step)
        self._temperature = max(1e-3, temperature)
        self._cooling = cooling

    @property
    def specs(self) -> tuple[ParamSpec, ...]:
        return self._specs

    @property
    def temperature(self) -> float:
        return self._temperature

    def propose(self, current: Tuning) -> Proposal:
        """Emit one candidate Tuning mutated by ``params_per_step`` specs.

        The proposer cools after every call so a session that runs N
        iterations explores broadly early and tightens late.
        """
        k = min(self._params_per_step, len(self._specs))
        chosen = self._rng.sample(self._specs, k)
        new_tuning = current
        diff: dict[str, tuple[float, float]] = {}
        for spec in chosen:
            old_val = get_param(new_tuning, spec.path) or 0.0
            step = self._rng.gauss(0.0, spec.step_scale * self._temperature)
            new_val = old_val + step
            new_val = max(spec.lo, min(spec.hi, new_val))
            if spec.is_int:
                new_val = float(int(round(new_val)))
            if math.isfinite(new_val) and abs(new_val - old_val) > 1e-9:
                new_tuning = set_param(new_tuning, spec.path, new_val)
                diff[spec.path] = (old_val, new_val)
        self._temperature *= self._cooling
        return Proposal(tuning=new_tuning, diff=diff)


# ----------------------------------------------------------------------
# Tuning → TOML serializer (the loop writes accepted snapshots).
# ----------------------------------------------------------------------


_HEADER = (
    "# tuning.toml — generated by jtx-improve.\n"
    "# Hand edits survive subsequent sessions IFF unknown keys are\n"
    "# absent (the loader is strict). Run `jtx-improve leaderboard`\n"
    "# to see which sessions produced this snapshot.\n"
)


def tuning_to_toml(tuning: Tuning) -> str:
    """Serialize *tuning* to a parsable + diff-friendly TOML string.

    The output round-trips through :func:`jtx.composer.tuning.load_tuning`
    losslessly when both sides agree on the schema. The optimizer only
    writes the sections it knows about; default-only fields are
    written explicitly so a hand-edited tuning.toml is also a complete
    snapshot.
    """
    lines: list[str] = [_HEADER]

    # Bare top-level keys must come before any [section] header — TOML
    # binds subsequent key=value into the most recent table. Keep them
    # first so the loader sees them as truly top-level.
    lines.append(f"\ntau_bias_magnitude = {_fmt(tuning.tau_bias_magnitude)}")

    lines.append("\n[voice_tau]")
    for voice, value in tuning.voice_tau.items():
        lines.append(f"{voice} = {_fmt(value)}")

    lines.append("\n[filter]")
    sub = tuning.filter.subdivisions
    lines.append(f'subdivisions = ["{sub[0]}", "{sub[1]}", "{sub[2]}"]')
    for f in fields(FilterTuning):
        if f.name == "subdivisions":
            continue
        lines.append(f"{f.name} = {_fmt(getattr(tuning.filter, f.name))}")

    lines.append("\n[tempo]")
    for f in fields(TempoTuning):
        lines.append(f"{f.name} = {_fmt(getattr(tuning.tempo, f.name))}")

    lines.append("\n[feel]")
    lines.append(f"window_half_base = {_fmt(tuning.feel.window_half_base)}")
    lines.append(
        f"window_half_chaos_coef = {_fmt(tuning.feel.window_half_chaos_coef)}"
    )
    for knob, coefs in tuning.feel.centres.items():
        lines.append(f"\n[feel.centres.{knob}]")
        for f in fields(FeelCentreCoefs):
            lines.append(f"{f.name} = {_fmt(getattr(coefs, f.name))}")

    if tuning.pattern_overrides:
        for voice, algos in tuning.pattern_overrides.items():
            for algo, knobs in algos.items():
                for knob, ov in knobs.items():
                    lines.append(f"\n[pattern_overrides.{voice}.{algo}.{knob}]")
                    for f in fields(WindowOverride):
                        val = getattr(ov, f.name)
                        if val is None:
                            continue
                        lines.append(f"{f.name} = {_fmt(val)}")

    return "\n".join(lines) + "\n"


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # 6 digits is enough to recover the optimizer's perturbation
        # scale; tighter would just pollute the diff with rounding noise.
        return f"{value:.6f}"
    if isinstance(value, str):
        return f'"{value}"'
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def write_tuning_toml(tuning: Tuning, path: Path) -> None:
    """Atomic write — temp file + rename so partial writes never poison the loader."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(tuning_to_toml(tuning))
    tmp.replace(path)


__all__ = [
    "ParamSpec",
    "Proposal",
    "RandomWalkProposer",
    "default_param_specs",
    "get_param",
    "pattern_param_specs",
    "set_param",
    "tuning_to_toml",
    "write_tuning_toml",
]
