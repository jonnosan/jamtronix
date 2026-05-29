"""Mood + format composer.

Generates a :class:`jtx.model.Song` from a high-level (mood, format,
chaos) brief instead of a hardcoded style template. The output always
populates the fixed 9-voice palette plus the utility cluster
(``filter``, ``root_ref``, ``chord_ref``); voices that have nothing
useful to contribute to a given song run the ``rest`` algorithm.

See ``~/.claude/plans/i-want-you-to-sleepy-wilkinson.md`` for the
overall design and ``docs/SPEC.md`` for the resulting song shape.
"""

from __future__ import annotations

from jtx.composer.compose import compose
from jtx.composer.format import FORMAT_SPECS, FormatSpec, FormatType
from jtx.composer.mood import MOOD_ANCHORS, MoodSpec
from jtx.composer.recipe import (
    FormatBlueprint,
    MoodBlueprint,
    Recipe,
    VoiceRecipe,
    build_recipe,
)
from jtx.composer.sonics import SONICS_REGIONS
from jtx.composer.titles import format_suffix, random_title
from jtx.composer.tuning import (
    FeelCentreCoefs,
    FeelTuning,
    FilterTuning,
    TempoTuning,
    Tuning,
    WindowOverride,
    default_tuning,
    load_tuning,
    reset_default_tuning_cache,
)
from jtx.composer.voices import FIXED_PALETTE, validate_palette

__all__ = [
    "FIXED_PALETTE",
    "FORMAT_SPECS",
    "FeelCentreCoefs",
    "FeelTuning",
    "FilterTuning",
    "FormatBlueprint",
    "FormatSpec",
    "FormatType",
    "MOOD_ANCHORS",
    "MoodBlueprint",
    "MoodSpec",
    "Recipe",
    "SONICS_REGIONS",
    "TempoTuning",
    "Tuning",
    "VoiceRecipe",
    "WindowOverride",
    "build_recipe",
    "compose",
    "default_tuning",
    "format_suffix",
    "load_tuning",
    "random_title",
    "reset_default_tuning_cache",
    "validate_palette",
]
