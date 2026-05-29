"""build_recipe coverage across all mood anchors × all formats."""

from __future__ import annotations

import pytest

from jtx.composer import (
    FIXED_PALETTE,
    FORMAT_SPECS,
    MOOD_ANCHORS,
    FormatType,
    build_recipe,
)
from jtx.composer.mood import MoodSpec


@pytest.mark.parametrize("anchor_name", sorted(MOOD_ANCHORS.keys()))
@pytest.mark.parametrize("fmt", sorted(FORMAT_SPECS.keys()))
def test_build_recipe_covers_palette(anchor_name: str, fmt: FormatType) -> None:
    mood = MOOD_ANCHORS[anchor_name]
    recipe = build_recipe(mood, fmt, chaos=0.0)

    assert set(recipe.voices.keys()) == set(FIXED_PALETTE)

    # Mood blueprint is plausible.
    lo, hi = recipe.mood.tempo_range
    assert 60 <= lo <= hi <= 180
    assert recipe.mood.scale in {"major", "minor"}
    assert recipe.mood.tonic_choices

    # Format blueprint matches the structural archetype.
    spec = FORMAT_SPECS[fmt]
    assert spec.part_count_range[0] <= recipe.format.part_count <= spec.part_count_range[1]
    assert len(recipe.format.intensity_envelope) == recipe.format.part_count
    if spec.loop_only:
        assert recipe.format.loop is True
        assert recipe.format.part_count == 1


@pytest.mark.parametrize("fmt", sorted(FORMAT_SPECS.keys()))
def test_chaos_widens_part_count(fmt: FormatType) -> None:
    """Chaos pushes part count toward the upper end of the format range."""
    mood = MOOD_ANCHORS["happy"]
    low = build_recipe(mood, fmt, chaos=0.0).format.part_count
    high = build_recipe(mood, fmt, chaos=1.0).format.part_count
    spec = FORMAT_SPECS[fmt]
    if spec.part_count_range[0] != spec.part_count_range[1]:
        assert high >= low


def test_mood_drives_tempo_and_key() -> None:
    """High-energy moods land at higher tempos; high-valence picks major."""
    angry = build_recipe(MOOD_ANCHORS["angry"], "song", chaos=0.0)
    dreamy = build_recipe(MOOD_ANCHORS["dreamy"], "song", chaos=0.0)
    assert angry.mood.tempo_range[0] > dreamy.mood.tempo_range[1]

    euphoric = build_recipe(MOOD_ANCHORS["euphoric"], "song", chaos=0.0)
    brooding = build_recipe(MOOD_ANCHORS["brooding"], "song", chaos=0.0)
    assert euphoric.mood.scale == "major"
    assert brooding.mood.scale == "minor"


def test_low_energy_voices_default_to_rest() -> None:
    """Low-energy songs run lead / arp / fx as rest by default."""
    recipe = build_recipe(MoodSpec(valence=-0.5, energy=-0.8), "sting", chaos=0.0)
    assert recipe.voices["lead"].algorithm == "rest"
    assert recipe.voices["arp"].algorithm == "rest"
    assert recipe.voices["fx"].algorithm == "rest"
    # drumkit always runs the drum_kit algorithm.
    assert recipe.voices["drumkit"].algorithm == "drum_kit"
