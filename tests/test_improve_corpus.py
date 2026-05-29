"""Tests for the Phase 2b corpus loader + default corpus."""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.composer.format import FORMAT_SPECS
from jtx.improve.corpus import (
    default_corpus,
    load_corpus,
)


def test_default_corpus_has_seven_anchors() -> None:
    corpus = default_corpus()
    expected = {"acid", "deep_techno", "psytrance", "dub_techno", "happy", "sad", "brooding"}
    assert set(corpus.anchors.keys()) == expected


def test_default_corpus_anchor_titles_are_stable() -> None:
    """Titles drive the composer RNG seed — sessions must hash to the same Song."""
    corpus = default_corpus()
    assert corpus.anchors["acid"].title == "improve-acid"
    assert corpus.anchors["sad"].title == "improve-sad"


def test_default_corpus_covers_all_formats_structurally() -> None:
    corpus = default_corpus()
    covered = {case.fmt for case in corpus.structure_cases}
    assert covered == set(FORMAT_SPECS.keys())


def test_default_corpus_grid_is_nine_neutral_cases() -> None:
    corpus = default_corpus()
    assert len(corpus.grid) == 9
    for case in corpus.grid:
        assert case.mood.valence == 0.0
        assert case.mood.energy == 0.0


def test_load_corpus_empty_settings_uses_defaults(tmp_path: Path) -> None:
    file = tmp_path / "eval_corpus.toml"
    file.write_text("[settings]\nbars = 3\n")
    corpus = load_corpus(file)
    assert corpus.bars == 3
    # Other settings keep defaults.
    assert corpus.parts == ("drop",)


def test_load_corpus_rejects_unknown_top_level(tmp_path: Path) -> None:
    file = tmp_path / "eval_corpus.toml"
    file.write_text("[mystery]\nfoo = 1\n")
    with pytest.raises(ValueError, match="unknown top-level"):
        load_corpus(file)


def test_load_corpus_rejects_unknown_settings_key(tmp_path: Path) -> None:
    file = tmp_path / "eval_corpus.toml"
    file.write_text("[settings]\nmystery_key = 1\n")
    with pytest.raises(ValueError, match="unknown key"):
        load_corpus(file)


def test_load_corpus_anchor_patch_overrides_default(tmp_path: Path) -> None:
    file = tmp_path / "eval_corpus.toml"
    file.write_text(
        "[anchors.acid]\n"
        "texture = 0.9\n"
        "motion = 0.1\n"
    )
    corpus = load_corpus(file)
    acid = corpus.anchors["acid"]
    assert acid.texture == 0.9
    assert acid.motion == 0.1
    # Mood untouched.
    assert acid.mood.valence == default_corpus().anchors["acid"].mood.valence
