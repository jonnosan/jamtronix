"""Song-format archetypes: bar ranges + part archetypes per format.

Format is the structural axis (vs mood's emotional axis). Six options
ship with v1:

* **sting**  — 4-8 bars, 1 part, a single moment (logo / SFX).
* **jingle** — 8-16 bars, 2-3 parts, hook + tag.
* **loop**   — 16-32 bars, 1 part, ``Part.loop=True`` (jam-friendly).
* **ramp**   — 16-32 bars, 2-3 parts, monotonic intensity build.
* **song**   — 48-80 bars, 5-6 parts, intro/build/drop/break/drop/outro.
* **anthem** — 96-160 bars, 7-8 parts, extended-arc club track.

Each :class:`FormatSpec` exposes ranges the recipe picker samples from;
intensity envelopes are picked per archetype.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jtx.model.composer_types import FormatType

# Re-exported from :mod:`jtx.model.composer_types`; lives there so
# :class:`jtx.model.Song.format` can be typed without cycling back
# through :mod:`jtx.composer`.


@dataclass(frozen=True)
class FormatSpec:
    """Structural archetype for one format.

    ``bars_per_part_range`` is the per-part bar count window the recipe
    sampler picks from; total bars roughly equals
    ``part_count * mid_of_range``. ``intensity_archetype`` names which
    envelope shape the part list follows (single / build / arc).
    ``loop_only`` flags formats where the single part loops in place.
    """

    bar_range: tuple[int, int]
    part_count_range: tuple[int, int]
    bars_per_part_range: tuple[int, int]
    intensity_archetype: Literal["single", "build", "arc", "extended_arc"]
    loop_only: bool = False
    """If True, the (single) part is generated with ``Part.loop=True``."""


FORMAT_SPECS: dict[FormatType, FormatSpec] = {
    "sting": FormatSpec(
        bar_range=(4, 8),
        part_count_range=(1, 1),
        bars_per_part_range=(4, 8),
        intensity_archetype="single",
    ),
    "jingle": FormatSpec(
        bar_range=(8, 16),
        part_count_range=(2, 3),
        bars_per_part_range=(4, 8),
        intensity_archetype="build",
    ),
    "loop": FormatSpec(
        bar_range=(16, 32),
        part_count_range=(1, 1),
        bars_per_part_range=(16, 32),
        intensity_archetype="single",
        loop_only=True,
    ),
    "ramp": FormatSpec(
        bar_range=(16, 32),
        part_count_range=(2, 3),
        bars_per_part_range=(8, 16),
        intensity_archetype="build",
    ),
    "song": FormatSpec(
        bar_range=(48, 80),
        part_count_range=(5, 6),
        bars_per_part_range=(8, 16),
        intensity_archetype="arc",
    ),
    "anthem": FormatSpec(
        bar_range=(96, 160),
        part_count_range=(7, 8),
        bars_per_part_range=(12, 20),
        intensity_archetype="extended_arc",
    ),
}


__all__ = ["FORMAT_SPECS", "FormatSpec", "FormatType"]
