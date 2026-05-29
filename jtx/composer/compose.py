"""Turn a (title, mood, format, chaos) brief into a :class:`Song`.

This is the entry point the Composer view (PR 4) calls. Deterministic:
the same inputs always produce a byte-identical Song. The seed mixes
title + mood + format + chaos so changing any axis re-rolls without
having to also change the title.

The output always populates :data:`FIXED_PALETTE` plus the utility
cluster (``filter``, ``root_ref``, ``chord_ref``). Voices without a
useful contribution to the song run the ``rest`` algorithm.
"""

from __future__ import annotations

import random

from jtx.composer.format import FormatType
from jtx.composer.mood import MoodSpec
from jtx.composer.recipe import Recipe, VoiceRecipe, build_recipe
from jtx.composer.voices import FIXED_PALETTE
from jtx.model import (
    Key,
    Part,
    Song,
    VoiceConfig,
)
from jtx.seed import seed_from_title

_UTILITY_FEEL_KEYS = ("pump", "groove", "drive", "tension", "wander")

_PART_NAMES = (
    "intro",
    "build",
    "drop",
    "break",
    "drop2",
    "outro",
    "outro2",
    "outro3",
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _seed_for(title: str, mood: MoodSpec, fmt: FormatType, chaos: float) -> int:
    """Mix the four inputs into a single deterministic seed."""
    key = (
        f"{title}|v={mood.valence:.4f}|e={mood.energy:.4f}"
        f"|c={chaos:.4f}|f={fmt}"
    )
    return seed_from_title(key)


def _sample_pattern(
    rng: random.Random, recipe: VoiceRecipe
) -> dict[str, object]:
    """Draw one concrete pattern dict from a recipe's ranges."""
    out: dict[str, object] = {}
    for knob, (lo, hi) in recipe.pattern_ranges.items():
        out[knob] = round(rng.uniform(lo, hi), 3)
    for knob, (lo, hi) in recipe.pattern_int_ranges.items():
        out[knob] = rng.randint(lo, hi)
    for knob, value in recipe.pattern_fixed.items():
        out[knob] = value
    return out


def _build_voices(
    rng: random.Random, recipe: Recipe
) -> dict[str, VoiceConfig]:
    """Walk the recipe's per-voice plans and emit concrete VoiceConfigs.

    Always returns the 9 palette voices plus the utility cluster
    (filter / root_ref / chord_ref) so every composer song carries the
    same voice set.
    """
    voices: dict[str, VoiceConfig] = {}
    for voice_name in FIXED_PALETTE:
        plan = recipe.voices[voice_name]
        voices[voice_name] = VoiceConfig(
            algorithm=plan.algorithm,
            pattern=_sample_pattern(rng, plan),
        )

    # Utility cluster — wired identically across every composer song.
    voices["filter"] = VoiceConfig(
        algorithm="step_cc",
        pattern={
            "function": "cutoff",
            "subdivision": "16",
            "value_curve": "arc",
            "value_min": 30,
            "value_max": 110,
        },
    )
    voices["root_ref"] = VoiceConfig(
        algorithm="voice_follower",
        pattern={
            "source": "bass",
            "latch": "first_per_bar",
        },
    )
    voices["chord_ref"] = VoiceConfig(
        algorithm="voice_follower",
        pattern={
            "source": "chord",
            "latch": "first_per_bar",
        },
    )
    return voices


def _build_parts(
    rng: random.Random, recipe: Recipe
) -> tuple[dict[str, Part], list[str]]:
    """Sample concrete parts + an arrangement list from the recipe."""
    fmt_bp = recipe.format
    bars_lo, bars_hi = fmt_bp.bars_per_part
    parts: dict[str, Part] = {}
    arrangement: list[str] = []
    for i in range(fmt_bp.part_count):
        name = _PART_NAMES[i] if i < len(_PART_NAMES) else f"part{i + 1}"
        bars = rng.randint(bars_lo, bars_hi)
        start, end = fmt_bp.intensity_envelope[i]
        parts[name] = Part(
            bars=bars,
            intensity_start=round(_clamp(start, 0.0, 1.0), 3),
            intensity_end=round(_clamp(end, 0.0, 1.0), 3),
            loop=fmt_bp.loop and fmt_bp.part_count == 1,
        )
        arrangement.append(name)
    return parts, arrangement


def _sample_feel(
    rng: random.Random, recipe: Recipe
) -> dict[str, float]:
    """Pick concrete global feel-knob values from the recipe windows."""
    feel: dict[str, float] = {}
    for key in _UTILITY_FEEL_KEYS:
        lo, hi = recipe.mood.feel_targets[key]
        feel[key] = round(rng.uniform(lo, hi), 3)
    return feel


def compose(
    title: str,
    setup_ref: str,
    mood: MoodSpec,
    fmt: FormatType,
    chaos: float = 0.0,
) -> Song:
    """Generate a :class:`Song` for ``(title, mood, fmt, chaos)``.

    The seed mixes all four inputs so changing any axis re-rolls the
    song without forcing the user to also change the title. ``chaos``
    is clamped to ``[0, 1]``.
    """
    chaos = _clamp(chaos, 0.0, 1.0)
    rng = random.Random(_seed_for(title, mood, fmt, chaos))
    recipe = build_recipe(mood, fmt, chaos)

    tempo = rng.randint(*recipe.mood.tempo_range)
    tonic = rng.choice(recipe.mood.tonic_choices)
    voices = _build_voices(rng, recipe)
    parts, arrangement = _build_parts(rng, recipe)
    feel = _sample_feel(rng, recipe)

    return Song(
        title=title,
        setup_ref=setup_ref,
        key=Key(tonic=tonic, scale=recipe.mood.scale),
        meter="4/4",
        tempo=tempo,
        voices=voices,
        parts=parts,
        arrangement=arrangement,
        feel=feel,
    )


__all__ = ["compose"]
