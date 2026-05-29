"""Anchor scoring — turn a (song, target) into a ScoreReport.

Renders a small bar window of each named part via
:meth:`jtx.player.SongPlayer.abstract_events_for_bar`, then evaluates
the target's intent predicates (over the Song) and delivery
descriptors (over the rendered bars). Total score is intent × delivery
so that intending the right thing but emitting nothing is still a
failure, per the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jtx.model.events import AbstractEvent
from jtx.model.setup import Setup
from jtx.model.song import Song
from jtx.player import SongPlayer

if TYPE_CHECKING:
    from jtx.evaluation.targets import Target

# A single rendered bar is a per-voice abstract-events dict (the shape
# SongPlayer.abstract_events_for_bar returns).
BarEvents = dict[str, list[AbstractEvent]]


@dataclass(frozen=True)
class CorpusSample:
    """Bars rendered for scoring, grouped by part.

    ``bars[part_name]`` is the list of *scoring* bars (bar 0 of each
    part is rendered but excluded — the algorithms' fade-in artifacts
    can skew density descriptors otherwise).
    """

    song: Song
    bars: dict[str, list[BarEvents]]


@dataclass(frozen=True)
class ScoreReport:
    """Anchor-fidelity score for one (song, target) pair.

    Intent × Delivery composition (not average): a song that picks
    the right algorithms but emits nothing musical fails just like
    one that emits a lot but picked wrong.
    """

    target_name: str
    intent_score: float
    delivery_score: float
    total_score: float
    intent_breakdown: dict[str, float] = field(default_factory=dict)
    delivery_breakdown: dict[str, float] = field(default_factory=dict)


def render_sample(
    song: Song,
    setup: Setup,
    parts: tuple[str, ...] = ("drop",),
    bars: int = 4,
) -> CorpusSample:
    """Render ``bars`` bars of each requested part; drop bar 0 from each.

    Parts that don't exist in *song* are silently skipped (composer
    formats vary on which named parts they produce). If a part has
    fewer than ``bars`` distinct bars, the player wraps modulo
    ``part.bars``; the scorer treats the wrap as part of the sample.
    """
    rendered: dict[str, list[BarEvents]] = {}
    for part_name in parts:
        if part_name not in song.parts:
            continue
        player = SongPlayer(song, setup, part_name)
        try:
            per_part: list[BarEvents] = []
            for bar_idx in range(bars):
                per_part.append(player.abstract_events_for_bar(bar_idx))
            rendered[part_name] = per_part[1:]  # skip bar 0 (fade-in)
        finally:
            player.close()
    return CorpusSample(song=song, bars=rendered)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def score_anchor(
    song: Song,
    setup: Setup,
    target: "Target",
    parts: tuple[str, ...] = ("drop",),
    bars: int = 4,
) -> ScoreReport:
    """Score *song* against *target*; returns a structured breakdown.

    Each intent predicate returns ``[0, 1]`` against the Song; each
    delivery descriptor returns ``[0, 1]`` against the rendered
    CorpusSample. The per-category mean is then multiplied for the
    total. Predicates and descriptors are deterministic.
    """
    sample = render_sample(song, setup, parts=parts, bars=bars)

    intent_breakdown: dict[str, float] = {}
    for ic in target.intent_predicates:
        intent_breakdown[ic.label] = _clip01(ic.check(song))
    intent_score = _mean(list(intent_breakdown.values()))

    delivery_breakdown: dict[str, float] = {}
    for dc in target.delivery_descriptors:
        delivery_breakdown[dc.label] = _clip01(dc.check(sample))
    delivery_score = _mean(list(delivery_breakdown.values()))

    return ScoreReport(
        target_name=target.name,
        intent_score=intent_score,
        delivery_score=delivery_score,
        total_score=intent_score * delivery_score,
        intent_breakdown=intent_breakdown,
        delivery_breakdown=delivery_breakdown,
    )


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


__all__ = [
    "BarEvents",
    "CorpusSample",
    "ScoreReport",
    "render_sample",
    "score_anchor",
]
