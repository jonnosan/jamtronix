"""Fixed 9-voice palette + palette validator.

Every Composer-built song uses the same nine musical voice names. This
gives the GUI a stable mental model (the knob layout doesn't shuffle
between songs) and lets users build muscle memory. Voices with nothing
useful to contribute in a given song run the ``rest`` algorithm.

Utility voices (``filter`` modulator, ``root_ref`` and ``chord_ref``
followers) are wired by every composer song but live outside the
palette — they're routing furniture, not musical voices.
"""

from __future__ import annotations

from jtx.model import Song, validate_fixed_palette
from jtx.model.composer_types import FIXED_PALETTE, UTILITY_VOICES


def validate_palette(song: Song) -> list[str]:
    """Composer-facing alias of :func:`jtx.model.validate_fixed_palette`."""
    return validate_fixed_palette(song)


__all__ = ["FIXED_PALETTE", "UTILITY_VOICES", "validate_palette"]
