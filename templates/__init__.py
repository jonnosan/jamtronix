"""Starter-song templates.

After the mood + format composer rework, this package keeps only the
``blank`` starter — an empty song with one part. Non-trivial song
generation now lives in :mod:`jtx.composer`.
"""

from __future__ import annotations

from collections.abc import Callable

from jtx.model import Song
from templates import blank

StyleBuilder = Callable[[str, str], Song]


STYLES: dict[str, StyleBuilder] = {
    "blank": blank.build,
}


def build(style: str, title: str, setup_ref: str) -> Song:
    builder = STYLES.get(style)
    if builder is None:
        raise ValueError(f"unknown style {style!r}; expected one of {sorted(STYLES)}")
    return builder(title, setup_ref)


__all__ = ["STYLES", "StyleBuilder", "build"]
