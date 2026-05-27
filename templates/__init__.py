"""Hardcoded style templates used by the new-song wizard.

Each style module exposes ``build(title: str, setup_ref: str) -> Song``
returning a fully populated :class:`jtx.model.Song` ready to save.

The style is *not* stored on the song — it only seeds the initial
arrangement. Once created, a song is just a song: any algorithm,
voice, or knob can be changed in the Song / Parts / Live views.
"""

from __future__ import annotations

from collections.abc import Callable

from jtx.model import Song
from templates import acid, blank, deep_techno, psytrance, wildcard

StyleBuilder = Callable[[str, str], Song]


STYLES: dict[str, StyleBuilder] = {
    "blank": blank.build,
    "acid": acid.build,
    "deep_techno": deep_techno.build,
    "psytrance": psytrance.build,
    "wildcard": wildcard.build,
}


def build(style: str, title: str, setup_ref: str) -> Song:
    builder = STYLES.get(style)
    if builder is None:
        raise ValueError(f"unknown style {style!r}; expected one of {sorted(STYLES)}")
    return builder(title, setup_ref)


__all__ = ["STYLES", "build", "StyleBuilder"]
