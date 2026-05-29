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

from jtx.model import Song

FIXED_PALETTE: tuple[str, ...] = (
    "drumkit",
    "bass",
    "sub",
    "lead",
    "pad",
    "chord",
    "arp",
    "stabs",
    "fx",
)
"""The 9 musical voices every composer song carries.

Note ``chord`` is singular (matches the ``Role`` literal in
:mod:`jtx.model.types`); ``stabs`` is plural to disambiguate from the
existing ``stab`` role.
"""

UTILITY_VOICES: tuple[str, ...] = ("filter", "root_ref", "chord_ref")
"""Modulator + follower voices wired by every composer song.

* ``filter`` — modulator broadcasting CC74-style cutoff sweeps.
* ``root_ref`` — follower mirroring the bass voice's root pitch so
  downstream MIDI devices can latch to the song's harmonic state.
* ``chord_ref`` — follower mirroring the chord voice for the same.
"""


def validate_palette(song: Song) -> list[str]:
    """Return errors if ``song`` doesn't conform to :data:`FIXED_PALETTE`.

    Every name in the palette must appear in ``song.voices`` (utility
    voices may or may not be present; PR 7 makes them mandatory). Extra
    voice names beyond palette + utility cluster are flagged so the
    composer doesn't silently leak experimental voices.
    """
    errors: list[str] = []
    palette_set = set(FIXED_PALETTE)
    voice_names = set(song.voices.keys())

    missing = palette_set - voice_names
    if missing:
        errors.append(
            f"song {song.title!r}: fixed palette missing voices "
            f"{sorted(missing)!r}"
        )

    allowed = palette_set | set(UTILITY_VOICES)
    extra = voice_names - allowed
    if extra:
        errors.append(
            f"song {song.title!r}: unexpected voice names {sorted(extra)!r} "
            f"(allowed: {sorted(allowed)!r})"
        )
    return errors


__all__ = ["FIXED_PALETTE", "UTILITY_VOICES", "validate_palette"]
