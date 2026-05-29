"""Sonics = (texture, motion) on the [0, 1] plane.

Texture runs sparse↔thick on the X axis; motion runs still↔animated
on the Y axis. Both axes are independent of mood. The four named
:data:`SONICS_REGIONS` are visual reference centres on the Composer
view's sonics pad — analogous to :data:`jtx.composer.mood.MOOD_ANCHORS`
on the mood pad, but visual-only (no snap).

Region centres are the midpoints of the epic #134 (texture, motion)
ranges per style; promoted here from the test fixtures in
``tests/test_composer_texture_motion.py``.
"""

from __future__ import annotations

SONICS_REGIONS: dict[str, tuple[float, float]] = {
    "acid":        (0.150, 0.725),
    "deep_techno": (0.775, 0.250),
    "psytrance":   (0.425, 0.850),
    "dub_techno":  (0.300, 0.800),
}
"""Four canonical (texture, motion) region centres on [0, 1]².

Acid sits just below the lead voice's motion-biased activation
threshold (τ≈0.15 at motion=0.725 — the raw τ=0.20 from
:data:`jtx.composer.tuning._DEFAULT_VOICE_TAU` minus half the
:attr:`Tuning.tau_bias_magnitude`). At this coord the recipe produces
drums + bass + stabs ("pure" acid, the bass and filter sweep doing
the heavy lifting); a tick of texture brings lead in for melodic
variants. Higher texture moves toward arp / sub / pad territory and
out of acid character entirely.
"""


__all__ = ["SONICS_REGIONS"]
