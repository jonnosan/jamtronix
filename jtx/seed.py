"""Deterministic seed derivation for songs, parts, voices, and bars.

Python's built-in ``hash()`` is randomised per process for strings, so we
use SHA-256 truncated to 63 bits (positive ``random.Random`` seed). The
same inputs always produce the same outputs regardless of run, machine,
or Python version.

Hierarchy (see ``docs/SPEC.md`` §Seed Model):

* :func:`seed_from_title` — song title → song seed.
* :func:`derive_part_voice_seed` — song seed + part name + voice name.
* :func:`derive_bar_seed` — per-(part, voice) seed + bar index.

All functions are pure; identical inputs return identical 63-bit ints.
"""

from __future__ import annotations

import hashlib

_NUL = b"\x00"
_MASK_63 = (1 << 63) - 1


def _digest63(parts: list[bytes]) -> int:
    """SHA-256 over NUL-separated parts → first 8 bytes → 63-bit int."""
    h = hashlib.sha256()
    for i, p in enumerate(parts):
        if i > 0:
            h.update(_NUL)
        h.update(p)
    return int.from_bytes(h.digest()[:8], "big") & _MASK_63


def seed_from_title(title: str) -> int:
    """Default song seed: SHA-256 of the title, truncated to 63 bits.

    Songs may override this with an explicit ``seed_override`` integer.
    """
    return _digest63([title.encode("utf-8")])


def derive_part_voice_seed(song_seed: int, part_name: str, voice_name: str) -> int:
    """Per-(part, voice) seed for one voice's stream within a part."""
    return _digest63(
        [
            str(song_seed).encode("utf-8"),
            part_name.encode("utf-8"),
            voice_name.encode("utf-8"),
        ]
    )


def derive_bar_seed(part_voice_seed: int, bar_index: int) -> int:
    """Per-bar seed for one voice's slice of one bar inside a part."""
    return _digest63(
        [
            str(part_voice_seed).encode("utf-8"),
            str(bar_index).encode("utf-8"),
        ]
    )
