"""Per-format structural integrity checks.

Each format archetype carries an arrangement promise:

* ``song`` / ``anthem`` — tension into drops; build sections build;
  outros decay.
* ``ramp`` — monotone rising intensity across the arrangement.
* ``loop`` — per-bar character stays stable (the part is designed to
  loop in place).
* ``sting`` / ``jingle`` — total length within the format spec; the
  arc resolves rather than ending at peak.

This module renders multiple parts via :func:`render_sample` and runs
the format-appropriate checks against the per-bar abstract events.
The output is a :class:`StructureReport` listing each check's pass /
fail with a short detail string so dashboards can surface the failing
ones without recomputing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from jtx.composer.format import FORMAT_SPECS
from jtx.engine.meter import ticks_per_bar as _tpb
from jtx.evaluation import descriptors as D
from jtx.evaluation.scoring import BarEvents, CorpusSample, render_sample
from jtx.model.setup import Setup
from jtx.model.song import Song

# Voices whose per-bar onset count dominates "density" for arrangement
# checks. Drum + bass + chord/arp carry most of the rhythmic energy;
# pads and subs add weight but rarely drive density. The list is fixed
# so structure checks score consistently across songs.
_DENSITY_VOICES: tuple[str, ...] = ("drumkit", "bass", "chord", "arp", "lead", "stabs")


@dataclass(frozen=True)
class StructureCheck:
    """One pass / fail observation about a song's structure."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class StructureReport:
    """All structure checks for a song + a summary pass-fraction score."""

    fmt: str
    checks: tuple[StructureCheck, ...]
    score: float
    """Fraction of checks that passed (``1.0`` = all pass)."""


# ---------- per-bar metrics --------------------------------------------


def _bar_onsets(bar: BarEvents, voices: Sequence[str] = _DENSITY_VOICES) -> int:
    return sum(D.onset_count(bar.get(v, [])) for v in voices)


def _bar_filter_peak(bar: BarEvents) -> float:
    """Max cutoff value emitted on the ``filter`` voice over the bar."""
    vs = D.param_values(bar.get("filter", []), "cutoff")
    return max(vs) if vs else 0.0


def _bar_filter_variance(bar: BarEvents) -> float:
    return D.param_trajectory_variance(bar.get("filter", []), "cutoff")


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _is_monotone_rising(values: Sequence[float], *, eps: float = 0.0) -> bool:
    """True iff each successive value rises by at least ``-eps``.

    A small negative tolerance survives the natural per-bar noise from
    accent variation while still catching clearly-not-rising envelopes.
    """
    return all(b - a >= -eps for a, b in zip(values, values[1:], strict=False))


# ---------- per-format check functions ---------------------------------


def _render_parts(song: Song, setup: Setup, parts: tuple[str, ...], bars: int) -> CorpusSample:
    """Render *parts* that exist in *song*; skips missing parts silently."""
    available = tuple(p for p in parts if p in song.parts)
    return render_sample(song, setup, parts=available, bars=bars)


def _check_song_arc(song: Song, setup: Setup, bars: int) -> tuple[StructureCheck, ...]:
    """song / anthem: drop denser than intro, build rises, outro decays."""
    parts = ("intro", "build", "drop", "outro")
    sample = _render_parts(song, setup, parts, bars)

    checks: list[StructureCheck] = []

    def _density(part: str) -> float:
        return _mean([float(_bar_onsets(b)) for b in sample.bars.get(part, [])])

    def _filter_peak(part: str) -> float:
        return _mean([_bar_filter_peak(b) for b in sample.bars.get(part, [])])

    intro_density = _density("intro")
    drop_density = _density("drop")
    if "intro" in sample.bars and "drop" in sample.bars:
        checks.append(
            StructureCheck(
                name="drop denser than intro",
                passed=drop_density > intro_density,
                detail=f"intro={intro_density:.1f} drop={drop_density:.1f}",
            )
        )

    intro_peak = _filter_peak("intro")
    drop_peak = _filter_peak("drop")
    if "intro" in sample.bars and "drop" in sample.bars:
        checks.append(
            StructureCheck(
                name="drop cutoff peak above intro",
                passed=drop_peak >= intro_peak,
                detail=f"intro_peak={intro_peak:.3f} drop_peak={drop_peak:.3f}",
            )
        )

    if "build" in sample.bars and len(sample.bars["build"]) >= 2:
        per_bar = [float(_bar_onsets(b)) for b in sample.bars["build"]]
        # Bar-over-bar density should generally rise; allow a small
        # epsilon to absorb accent jitter.
        rising = _is_monotone_rising(per_bar, eps=2.0)
        checks.append(
            StructureCheck(
                name="build density rises bar-over-bar",
                passed=rising,
                detail=f"densities={[round(x, 1) for x in per_bar]}",
            )
        )

    if "drop" in sample.bars and "outro" in sample.bars:
        outro_density = _density("outro")
        checks.append(
            StructureCheck(
                name="outro decays from drop",
                passed=outro_density < drop_density,
                detail=f"drop={drop_density:.1f} outro={outro_density:.1f}",
            )
        )

    return tuple(checks)


def _check_ramp(song: Song, setup: Setup, bars: int) -> tuple[StructureCheck, ...]:
    """ramp: arrangement-level density monotone rising part-by-part."""
    sample = _render_parts(song, setup, tuple(song.arrangement), bars)
    per_part_density: list[tuple[str, float]] = []
    for part in song.arrangement:
        bars_for_part = sample.bars.get(part, [])
        per_part_density.append(
            (part, _mean([float(_bar_onsets(b)) for b in bars_for_part]))
        )
    densities = [d for _, d in per_part_density]
    rising = _is_monotone_rising(densities, eps=2.0) if len(densities) >= 2 else False
    return (
        StructureCheck(
            name="ramp density rises across parts",
            passed=rising,
            detail=", ".join(f"{n}={d:.1f}" for n, d in per_part_density),
        ),
    )


def _check_loop(song: Song, setup: Setup, bars: int) -> tuple[StructureCheck, ...]:
    """loop: per-bar density variance stays low (the part repeats cleanly)."""
    sample = _render_parts(song, setup, tuple(song.arrangement), bars)
    # Loop format has a single part. Pull whichever part rendered.
    if not sample.bars:
        return (
            StructureCheck(
                name="loop part rendered",
                passed=False,
                detail="no parts rendered",
            ),
        )
    part_name, bar_events = next(iter(sample.bars.items()))
    per_bar = [float(_bar_onsets(b)) for b in bar_events]
    mean = _mean(per_bar)
    if mean <= 0:
        variance_norm = 0.0
    else:
        var = sum((v - mean) ** 2 for v in per_bar) / len(per_bar)
        variance_norm = var / (mean * mean)
    # Loose threshold — loop is meant to repeat, not be literally
    # identical bar-to-bar (accents + drops still allowed).
    passed = variance_norm < 0.5
    return (
        StructureCheck(
            name=f"loop ({part_name}) per-bar density variance stays low",
            passed=passed,
            detail=f"variance_norm={variance_norm:.3f} densities={[round(x, 1) for x in per_bar]}",
        ),
    )


def _check_short(song: Song, setup: Setup, bars: int) -> tuple[StructureCheck, ...]:
    """sting / jingle: total length in spec; the arc resolves."""
    spec = FORMAT_SPECS[song.format]
    lo, hi = spec.bar_range
    total_bars = sum(p.bars for p in song.parts.values())
    checks: list[StructureCheck] = [
        StructureCheck(
            name=f"{song.format} total bars within [{lo}, {hi}]",
            passed=lo <= total_bars <= hi,
            detail=f"total_bars={total_bars}",
        ),
    ]

    if len(song.arrangement) >= 2:
        sample = _render_parts(song, setup, tuple(song.arrangement), bars)
        per_part = [
            (p, _mean([float(_bar_onsets(b)) for b in sample.bars.get(p, [])]))
            for p in song.arrangement
        ]
        peak = max((d for _, d in per_part), default=0.0)
        last_density = per_part[-1][1] if per_part else 0.0
        resolves = last_density <= peak * 0.95
        checks.append(
            StructureCheck(
                name=f"{song.format} arc resolves (last part below peak)",
                passed=resolves,
                detail=f"peak={peak:.1f} last={last_density:.1f}",
            )
        )

    return tuple(checks)


# ---------- entry point ------------------------------------------------


def structural_integrity(song: Song, setup: Setup, *, bars: int = 4) -> StructureReport:
    """Run the format-appropriate checks; return a structured report.

    Renders the relevant parts via :func:`render_sample`. Songs whose
    declared :attr:`Song.format` is unknown raise ``ValueError`` —
    that's a model-validation problem, not a structure problem.
    """
    fmt = song.format
    if fmt in ("song", "anthem"):
        checks = _check_song_arc(song, setup, bars)
    elif fmt == "ramp":
        checks = _check_ramp(song, setup, bars)
    elif fmt == "loop":
        checks = _check_loop(song, setup, bars)
    elif fmt in ("sting", "jingle"):
        checks = _check_short(song, setup, bars)
    else:
        raise ValueError(f"unknown song.format: {fmt!r}")

    if not checks:
        score = 1.0
    else:
        score = sum(1 for c in checks if c.passed) / len(checks)
    return StructureReport(fmt=fmt, checks=checks, score=score)


__all__ = [
    "StructureCheck",
    "StructureReport",
    "structural_integrity",
]
