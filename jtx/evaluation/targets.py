"""Declarative anchor Targets — what "acid" / "happy" / etc. mean.

A :class:`Target` is a named bundle of :class:`IntentCheck` callables
(read the Song's chosen algorithms and knobs) plus
:class:`DeliveryCheck` callables (read the rendered abstract events).

Each predicate returns a continuous ``[0, 1]`` score so the scoring
math composes cleanly — booleans collapse to 0.0 / 1.0, soft checks
return graded values, and the scorer takes the per-category mean.

v1 ships seven anchors: four sonics regions (acid, deep_techno,
psytrance, dub_techno — from :data:`jtx.composer.sonics.SONICS_REGIONS`)
and three mood anchors (happy, sad, brooding — from
:data:`jtx.composer.mood.MOOD_ANCHORS`). Threshold tuning is
deliberately loose; Phase 1c's discriminability + sensitivity modes
will pressure-test how tight the targets can usefully be.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jtx.evaluation import descriptors as D
from jtx.model.events import AbstractEvent
from jtx.model.song import Song

if TYPE_CHECKING:
    from jtx.evaluation.scoring import BarEvents, CorpusSample


@dataclass(frozen=True)
class IntentCheck:
    """One Song-level predicate the composer should satisfy for this anchor."""

    label: str
    check: Callable[[Song], float]


@dataclass(frozen=True)
class DeliveryCheck:
    """One rendered-events check the algorithms should satisfy for this anchor."""

    label: str
    check: Callable[["CorpusSample"], float]


@dataclass(frozen=True)
class Target:
    """Named anchor — a bundle of intent + delivery checks."""

    name: str
    intent_predicates: tuple[IntentCheck, ...]
    delivery_descriptors: tuple[DeliveryCheck, ...]


# ----------------------------------------------------------------------
# Intent helpers (Song-level)
# ----------------------------------------------------------------------


def _voice_algorithm(song: Song, voice: str) -> str:
    vc = song.voices.get(voice)
    return vc.algorithm if vc is not None else "rest"


def _voice_pattern(song: Song, voice: str, key: str, default: float = 0.0) -> float:
    vc = song.voices.get(voice)
    if vc is None:
        return default
    value = vc.pattern.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _voice_pattern_str(song: Song, voice: str, key: str, default: str = "") -> str:
    vc = song.voices.get(voice)
    if vc is None:
        return default
    value = vc.pattern.get(key, default)
    return str(value)


def _algorithm_eq(voice: str, expected: str) -> Callable[[Song], float]:
    def check(song: Song) -> float:
        return 1.0 if _voice_algorithm(song, voice) == expected else 0.0

    return check


def _algorithm_not_rest(voice: str) -> Callable[[Song], float]:
    def check(song: Song) -> float:
        return 0.0 if _voice_algorithm(song, voice) == "rest" else 1.0

    return check


def _algorithm_is_rest(voice: str) -> Callable[[Song], float]:
    def check(song: Song) -> float:
        return 1.0 if _voice_algorithm(song, voice) == "rest" else 0.0

    return check


def _pattern_min(voice: str, key: str, threshold: float) -> Callable[[Song], float]:
    """Soft check: maps ``value/threshold`` clipped to ``[0, 1]``."""

    def check(song: Song) -> float:
        value = _voice_pattern(song, voice, key)
        if threshold <= 0:
            return 1.0 if value > 0 else 0.0
        return max(0.0, min(1.0, value / threshold))

    return check


def _pattern_max(voice: str, key: str, threshold: float) -> Callable[[Song], float]:
    """Soft check: 1.0 if value ≤ threshold, ramps to 0 as value rises above."""

    def check(song: Song) -> float:
        value = _voice_pattern(song, voice, key)
        if value <= threshold:
            return 1.0
        # Linear ramp: at 2× threshold, score = 0.
        return max(0.0, 1.0 - (value - threshold) / max(threshold, 1e-6))

    return check


def _pattern_in(voice: str, key: str, allowed: tuple[str, ...]) -> Callable[[Song], float]:
    def check(song: Song) -> float:
        return 1.0 if _voice_pattern_str(song, voice, key) in allowed else 0.0

    return check


def _scale_eq(scale: str) -> Callable[[Song], float]:
    def check(song: Song) -> float:
        return 1.0 if song.key.scale == scale else 0.0

    return check


def _tempo_in(lo: int, hi: int) -> Callable[[Song], float]:
    def check(song: Song) -> float:
        return 1.0 if lo <= song.tempo <= hi else 0.0

    return check


# ----------------------------------------------------------------------
# Delivery helpers (rendered-events level)
# ----------------------------------------------------------------------


def _per_bar(
    sample: "CorpusSample", part: str, fn: Callable[["BarEvents"], float]
) -> list[float]:
    bars = sample.bars.get(part, [])
    return [fn(b) for b in bars]


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _voice_has_notes(voice: str, *, part: str = "drop", min_per_bar: float = 1.0) -> Callable[["CorpusSample"], float]:
    def check(sample: "CorpusSample") -> float:
        counts = _per_bar(sample, part, lambda b: float(D.note_count(b.get(voice, []))))
        mean = _mean(counts)
        if min_per_bar <= 0:
            return 1.0 if mean > 0 else 0.0
        return max(0.0, min(1.0, mean / min_per_bar))

    return check


def _voice_has_hits(voice: str, *, part: str = "drop", min_per_bar: float = 1.0) -> Callable[["CorpusSample"], float]:
    def check(sample: "CorpusSample") -> float:
        counts = _per_bar(sample, part, lambda b: float(D.hit_count(b.get(voice, []))))
        mean = _mean(counts)
        if min_per_bar <= 0:
            return 1.0 if mean > 0 else 0.0
        return max(0.0, min(1.0, mean / min_per_bar))

    return check


def _voice_grid_min(voice: str, threshold: float, *, part: str = "drop") -> Callable[["CorpusSample"], float]:
    """Mean 16th-grid coverage on *voice* over scoring bars must reach threshold."""

    def check(sample: "CorpusSample") -> float:
        # ticks_per_bar varies per song. We can compute it from a bar's
        # events… or just assume 1920 (4/4 @ 480 ppq, the player default).
        # Pull from sample.song instead for correctness.
        from jtx.engine.meter import ticks_per_bar as _tpb

        meter = sample.song.meter
        # SongPlayer uses ppq=480 by default in render_sample.
        ticks_per_bar = _tpb(meter, 480)
        coverage = _per_bar(
            sample,
            part,
            lambda b: D.sixteenth_grid_coverage(b.get(voice, []), ticks_per_bar),
        )
        mean = _mean(coverage)
        if threshold <= 0:
            return 1.0 if mean > 0 else 0.0
        return max(0.0, min(1.0, mean / threshold))

    return check


def _param_variance_min(
    voice: str, name: str, threshold: float, *, part: str = "drop"
) -> Callable[["CorpusSample"], float]:
    """Mean Param-trajectory variance on *voice* / *name* must reach threshold."""

    def check(sample: "CorpusSample") -> float:
        variances = _per_bar(
            sample,
            part,
            lambda b: D.param_trajectory_variance(b.get(voice, []), name),
        )
        mean = _mean(variances)
        if threshold <= 0:
            return 1.0 if mean > 0 else 0.0
        return max(0.0, min(1.0, mean / threshold))

    return check


def _param_variance_max(
    voice: str, name: str, ceiling: float, *, part: str = "drop"
) -> Callable[["CorpusSample"], float]:
    """Param-trajectory variance must STAY BELOW ceiling (low-motion anchors)."""

    def check(sample: "CorpusSample") -> float:
        variances = _per_bar(
            sample,
            part,
            lambda b: D.param_trajectory_variance(b.get(voice, []), name),
        )
        mean = _mean(variances)
        if mean <= ceiling:
            return 1.0
        return max(0.0, 1.0 - (mean - ceiling) / max(ceiling, 1e-6))

    return check


def _voice_emits_anything(voice: str, *, part: str = "drop") -> Callable[["CorpusSample"], float]:
    def check(sample: "CorpusSample") -> float:
        present = _per_bar(
            sample,
            part,
            lambda b: 1.0 if D.voice_active(b.get(voice, [])) else 0.0,
        )
        return _mean(present)

    return check


# ----------------------------------------------------------------------
# Anchor definitions
# ----------------------------------------------------------------------


ACID = Target(
    name="acid",
    intent_predicates=(
        IntentCheck("bass uses acid_bass", _algorithm_eq("bass", "acid_bass")),
        IntentCheck("lead is active", _algorithm_not_rest("lead")),
        IntentCheck("filter depth ≥ 0.6", _pattern_min("filter", "depth", 0.6)),
    ),
    delivery_descriptors=(
        DeliveryCheck("bass emits notes", _voice_has_notes("bass", min_per_bar=8.0)),
        DeliveryCheck(
            "bass covers 16th grid",
            _voice_grid_min("bass", 0.4),
        ),
        DeliveryCheck(
            "filter cutoff trajectory has variance",
            _param_variance_min("filter", "cutoff", 0.02),
        ),
    ),
)


DEEP_TECHNO = Target(
    name="deep_techno",
    intent_predicates=(
        IntentCheck("sub uses sub_drone", _algorithm_eq("sub", "sub_drone")),
        IntentCheck("pad uses sustained_chord", _algorithm_eq("pad", "sustained_chord")),
        IntentCheck("filter depth ≤ 0.4", _pattern_max("filter", "depth", 0.4)),
    ),
    delivery_descriptors=(
        DeliveryCheck("sub emits notes", _voice_has_notes("sub", min_per_bar=1.0)),
        DeliveryCheck("pad emits notes", _voice_has_notes("pad", min_per_bar=1.0)),
        DeliveryCheck(
            "filter cutoff trajectory stays calm",
            _param_variance_max("filter", "cutoff", 0.03),
        ),
    ),
)


PSYTRANCE = Target(
    name="psytrance",
    intent_predicates=(
        IntentCheck("bass uses acid_bass", _algorithm_eq("bass", "acid_bass")),
        IntentCheck("bass cycle ≥ 3 (rolling)", _pattern_min("bass", "cycle", 3.0)),
        IntentCheck("arp is active", _algorithm_eq("arp", "arp")),
        IntentCheck(
            "arp subdivision is fast",
            _pattern_in("arp", "subdivision", ("16", "16t")),
        ),
        IntentCheck("filter depth ≥ 0.6", _pattern_min("filter", "depth", 0.6)),
    ),
    delivery_descriptors=(
        DeliveryCheck("bass emits notes", _voice_has_notes("bass", min_per_bar=8.0)),
        DeliveryCheck("arp emits notes", _voice_has_notes("arp", min_per_bar=4.0)),
        DeliveryCheck(
            "filter cutoff trajectory has variance",
            _param_variance_min("filter", "cutoff", 0.02),
        ),
    ),
)


DUB_TECHNO = Target(
    name="dub_techno",
    intent_predicates=(
        IntentCheck("filter depth ≥ 0.5 (high motion)", _pattern_min("filter", "depth", 0.5)),
        IntentCheck("sub is rest (low texture)", _algorithm_is_rest("sub")),
        IntentCheck("pad is rest (low texture)", _algorithm_is_rest("pad")),
    ),
    delivery_descriptors=(
        DeliveryCheck("bass emits notes", _voice_has_notes("bass", min_per_bar=4.0)),
        DeliveryCheck(
            "filter cutoff trajectory has variance",
            _param_variance_min("filter", "cutoff", 0.02),
        ),
    ),
)


# ---------- mood anchors ----------------------------------------------


HAPPY = Target(
    name="happy",
    intent_predicates=(
        IntentCheck("major scale", _scale_eq("major")),
        IntentCheck("tempo ≥ 110", _tempo_in(110, 200)),
    ),
    delivery_descriptors=(
        DeliveryCheck("drumkit emits hits", _voice_has_hits("drumkit", min_per_bar=4.0)),
    ),
)


SAD = Target(
    name="sad",
    intent_predicates=(
        IntentCheck("minor scale", _scale_eq("minor")),
        IntentCheck("tempo ≤ 110", _tempo_in(0, 110)),
    ),
    delivery_descriptors=(
        DeliveryCheck("drumkit emits hits (any density)", _voice_has_hits("drumkit", min_per_bar=1.0)),
    ),
)


BROODING = Target(
    name="brooding",
    intent_predicates=(
        IntentCheck("minor scale", _scale_eq("minor")),
        IntentCheck("tempo ≤ 120", _tempo_in(0, 120)),
    ),
    delivery_descriptors=(
        DeliveryCheck("drumkit emits hits", _voice_has_hits("drumkit", min_per_bar=2.0)),
        DeliveryCheck("bass emits notes", _voice_has_notes("bass", min_per_bar=1.0)),
    ),
)


ANCHORS: dict[str, Target] = {
    "acid": ACID,
    "deep_techno": DEEP_TECHNO,
    "psytrance": PSYTRANCE,
    "dub_techno": DUB_TECHNO,
    "happy": HAPPY,
    "sad": SAD,
    "brooding": BROODING,
}
"""All named anchors v1 ships. Phase 1c may add more after the
discriminability + sensitivity modes show which targets are
load-bearing for separating styles."""


__all__ = [
    "ACID",
    "ANCHORS",
    "BROODING",
    "DEEP_TECHNO",
    "DUB_TECHNO",
    "DeliveryCheck",
    "HAPPY",
    "IntentCheck",
    "PSYTRANCE",
    "SAD",
    "Target",
]
