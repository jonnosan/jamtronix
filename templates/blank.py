"""Blank style — empty starter song with one default part.

Useful when the user wants to compose from scratch in the Song / Parts
views rather than start from a hardcoded arrangement.
"""

from __future__ import annotations

from jtx.model import Key, Part, Song


def build(title: str, setup_ref: str) -> Song:
    return Song(
        title=title,
        setup_ref=setup_ref,
        key=Key(tonic="A", scale="minor"),
        meter="4/4",
        tempo=120,
        voices={},
        parts={"intro": Part(bars=8)},
        arrangement=["intro"],
    )
