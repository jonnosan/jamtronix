"""Generator-algorithm evaluation harness.

Phase 1b of the evaluation epic (#158). Provides anchor-fidelity
scoring against named musical targets — does the generator deliver
on the composer's declared mood/sonics intent?

Tap point: :meth:`jtx.player.SongPlayer.abstract_events_for_bar`,
exposed in Phase 1a. Algorithms emit semantic instrument names
(``Hit.instrument="kick"``) and parameter functions
(``Param.name="cutoff"``) per voice, before mix/feel/voicing/router
translate them to MIDI. The scorer reads them directly.

This phase ships only the anchor scoring mode. The other three modes
(discriminability, knob sensitivity, structural integrity) land in
Phase 1c.
"""

from __future__ import annotations

from jtx.evaluation.scoring import CorpusSample, ScoreReport, render_sample, score_anchor
from jtx.evaluation.targets import (
    ANCHORS,
    DeliveryCheck,
    IntentCheck,
    Target,
)

__all__ = [
    "ANCHORS",
    "CorpusSample",
    "DeliveryCheck",
    "IntentCheck",
    "ScoreReport",
    "Target",
    "render_sample",
    "score_anchor",
]
