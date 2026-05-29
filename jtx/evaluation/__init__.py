"""Generator-algorithm evaluation harness.

Phases 1b + 1c of the evaluation epic (#158). The four evaluation
modes the plan calls for:

* **Anchor fidelity** (1b) — :func:`score_anchor` against a named
  :class:`Target` from :data:`ANCHORS`.
* **Discriminability** (1c) — :func:`discriminability_report` builds
  a pairwise distance matrix between anchor feature vectors with an
  intra-anchor jitter baseline.
* **Knob sensitivity** (1c) — :func:`sweep` regresses each descriptor
  against a composer input axis to surface dead knobs.
* **Structural integrity** (1c) — :func:`structural_integrity` runs
  per-:attr:`Song.format` arrangement checks (drop > intro density,
  build rises, loop stays self-similar, etc.).

Tap point: :meth:`jtx.player.SongPlayer.abstract_events_for_bar`,
exposed in Phase 1a. Algorithms emit semantic instrument names
(``Hit.instrument="kick"``) and parameter functions
(``Param.name="cutoff"``) per voice, before mix/feel/voicing/router
translate them to MIDI. The scorer reads them directly.

The sensitivity sweep also has a CLI entry::

    python -m jtx.evaluation sweep --axis motion --steps 11 [--seed N] [--out FILE.csv]
"""

from __future__ import annotations

from jtx.evaluation.discriminability import (
    FEATURE_SCHEMA,
    DiscriminabilityReport,
    discriminability_report,
    feature_array,
    feature_keys,
    feature_vector,
)
from jtx.evaluation.scoring import CorpusSample, ScoreReport, render_sample, score_anchor
from jtx.evaluation.sensitivity import (
    SensitivityFixed,
    SensitivityPoint,
    SensitivityResult,
    sweep,
)
from jtx.evaluation.structure import (
    StructureCheck,
    StructureReport,
    structural_integrity,
)
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
    "DiscriminabilityReport",
    "FEATURE_SCHEMA",
    "IntentCheck",
    "ScoreReport",
    "SensitivityFixed",
    "SensitivityPoint",
    "SensitivityResult",
    "StructureCheck",
    "StructureReport",
    "Target",
    "discriminability_report",
    "feature_array",
    "feature_keys",
    "feature_vector",
    "render_sample",
    "score_anchor",
    "structural_integrity",
    "sweep",
]
