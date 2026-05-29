"""Knob-sensitivity sweep — does moving one input actually move output?

Sweeps a single composer input axis (``texture``, ``motion``,
``valence``, ``energy``) across N evenly-spaced steps holding the
others fixed; for each step composes a song at that coord, renders a
short sample, and extracts the standard
:data:`jtx.evaluation.discriminability.FEATURE_SCHEMA` vector. Then
runs a per-feature linear regression of feature value against axis
value to surface dead knobs (slope ≈ 0).

The output is a (knob × descriptor) sensitivity row; flat rows are
the bugs to chase per the epic plan.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from jtx.composer import compose
from jtx.composer.mood import MoodSpec
from jtx.evaluation.discriminability import (
    FEATURE_SCHEMA,
    feature_keys,
    feature_vector,
)
from jtx.evaluation.scoring import render_sample
from jtx.model.setup import Setup

Axis = Literal["texture", "motion", "valence", "energy"]

# Axes the GUI exposes. Texture/motion are [0, 1]; valence/energy are
# [-1, 1] (see MoodSpec). Sweeps respect these natural ranges.
_AXIS_RANGE: dict[str, tuple[float, float]] = {
    "texture": (0.0, 1.0),
    "motion": (0.0, 1.0),
    "valence": (-1.0, 1.0),
    "energy": (-1.0, 1.0),
}


@dataclass(frozen=True)
class SensitivityFixed:
    """Values held constant while one axis is swept.

    Defaults sit at the centre of each axis. Override individually
    when probing how sensitivity changes elsewhere in the input space.
    """

    texture: float = 0.5
    motion: float = 0.5
    valence: float = 0.0
    energy: float = 0.0
    chaos: float = 0.0
    fmt: str = "song"
    title_prefix: str = "Sweep"


@dataclass(frozen=True)
class SensitivityPoint:
    """One step of a sweep — axis value + the full feature vector."""

    axis_value: float
    features: dict[str, float]


@dataclass(frozen=True)
class SensitivityResult:
    """Sweep output: per-step features + per-feature regression stats."""

    axis: str
    steps: int
    feature_keys: tuple[str, ...]
    points: tuple[SensitivityPoint, ...]
    slope: dict[str, float]
    intercept: dict[str, float]
    r2: dict[str, float]

    def dead_keys(self, slope_eps: float = 1e-3) -> tuple[str, ...]:
        """Feature keys whose absolute slope falls below *slope_eps*.

        Useful for asserting that *some* descriptor in a known-active
        category responds to the axis without pinning the test to a
        single feature.
        """
        return tuple(k for k, s in self.slope.items() if abs(s) < slope_eps)


def _axis_values(axis: Axis, steps: int) -> list[float]:
    if steps < 2:
        raise ValueError("steps must be >= 2")
    lo, hi = _AXIS_RANGE[axis]
    span = hi - lo
    return [lo + span * i / (steps - 1) for i in range(steps)]


def _linreg(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float]:
    """Return ``(slope, intercept, r_squared)`` for a least-squares fit.

    Constant *ys* return slope=intercept=0 and R²=0 (a flat input maps
    to a flat output, by convention here — distinguishes dead-knob
    cases from degenerate ones in downstream reporting).
    """
    n = len(xs)
    if n < 2:
        return 0.0, 0.0, 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    if sxx < 1e-12:
        return 0.0, mean_y, 0.0
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot < 1e-12:
        return 0.0, mean_y, 0.0
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys, strict=True))
    r2 = max(0.0, 1.0 - ss_res / ss_tot)
    return slope, intercept, r2


def sweep(
    axis: Axis,
    setup: Setup,
    steps: int = 11,
    *,
    fixed: SensitivityFixed | None = None,
    seed: int = 0,
    parts: tuple[str, ...] = ("drop",),
    bars: int = 4,
) -> SensitivityResult:
    """Sweep *axis* across *steps* values; regress each feature on input.

    *fixed* freezes the non-swept axes at known values. *seed* is mixed
    into the song title so different runs of the same sweep can be
    averaged or compared without all picking identical RNG streams.
    *parts* / *bars* are forwarded to :func:`render_sample`; the
    ``drop`` part is the default because that's where style lives per
    the plan.
    """
    fx = fixed or SensitivityFixed()
    values = _axis_values(axis, steps)
    keys = feature_keys()

    points: list[SensitivityPoint] = []
    for i, v in enumerate(values):
        texture = fx.texture
        motion = fx.motion
        valence = fx.valence
        energy = fx.energy
        if axis == "texture":
            texture = v
        elif axis == "motion":
            motion = v
        elif axis == "valence":
            valence = v
        elif axis == "energy":
            energy = v

        title = f"{fx.title_prefix}-{axis}-{seed}-{i}"
        song = compose(
            title,
            "iac",
            MoodSpec(valence=valence, energy=energy, chaos=fx.chaos),
            fx.fmt,  # type: ignore[arg-type]
            chaos=fx.chaos,
            texture=texture,
            motion=motion,
        )
        # Some formats (sting/loop) only produce "intro"; the caller
        # passes a parts tuple that lines up. Missing parts skip
        # silently inside render_sample, so the resulting CorpusSample
        # may have empty bars for some axes — feature_vector handles
        # that by returning zeros.
        sample = render_sample(song, setup, parts=parts, bars=bars)
        features = feature_vector(sample)
        points.append(SensitivityPoint(axis_value=v, features=features))

    slope: dict[str, float] = {}
    intercept: dict[str, float] = {}
    r2: dict[str, float] = {}
    xs = [p.axis_value for p in points]
    for k, _ in FEATURE_SCHEMA:
        ys = [p.features[k] for p in points]
        s, b, r = _linreg(xs, ys)
        slope[k] = s
        intercept[k] = b
        r2[k] = r

    return SensitivityResult(
        axis=axis,
        steps=steps,
        feature_keys=keys,
        points=tuple(points),
        slope=slope,
        intercept=intercept,
        r2=r2,
    )


__all__ = [
    "Axis",
    "SensitivityFixed",
    "SensitivityPoint",
    "SensitivityResult",
    "sweep",
]
