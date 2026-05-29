"""The test corpus the ``jtx-improve`` loop scores against.

A :class:`Corpus` declares:

* The 7 named anchors (4 sonics + 3 mood). Each carries the
  ``(mood, texture, motion, format)`` coordinates needed to drive
  :func:`jtx.composer.compose`.
* A small ``(texture, motion)`` grid for sensitivity sampling and
  extra discriminability data.
* A few format-coverage cases the structural-integrity check renders.
* How many jitter seeds to render per anchor for the discriminability
  baseline.
* Render plumbing — ``setup_path``, ``parts``, ``bars``.

Defaults reproduce the coordinates the Phase 1b/1c tests already use
so the optimizer measures the same surface the harness was validated
against. A TOML loader (:func:`load_corpus`) lets future sessions pin
or extend the corpus without code edits.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from jtx.composer.format import FORMAT_SPECS, FormatType
from jtx.composer.mood import MOOD_ANCHORS, MoodSpec
from jtx.composer.sonics import SONICS_REGIONS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SETUP = _REPO_ROOT / "setups" / "iac.jtx-setup"


# Sonics anchors carry only (texture, motion). Pair each with a sensible
# mood — these mirror the Phase 1b fixtures so the optimizer measures
# the same surface those tests pin down. Keep them in sync if
# tests/test_evaluation_scoring.py:_SONICS_MOOD changes.
_DEFAULT_SONICS_MOOD: dict[str, MoodSpec] = {
    "acid":        MoodSpec(valence=-0.15, energy=0.55),
    "deep_techno": MoodSpec(valence=-0.35, energy=0.40),
    "psytrance":   MoodSpec(valence=-0.25, energy=0.90),
    "dub_techno":  MoodSpec(valence=0.00,  energy=0.20),
}


@dataclass(frozen=True)
class CorpusCase:
    """One composer invocation — the inputs to :func:`jtx.composer.compose`."""

    name: str
    mood: MoodSpec
    texture: float
    motion: float
    fmt: FormatType
    chaos: float = 0.0

    @property
    def title(self) -> str:
        """A stable, deterministic title for the case."""
        # The composer hashes the title into the RNG seed; stable name →
        # stable seed → identical Song each session.
        return f"improve-{self.name}"


@dataclass(frozen=True)
class Corpus:
    """All cases the loop scores against per iteration.

    *anchors* is the headline set used for the anchor-fidelity term
    and as the centre set for the discriminability check. *grid* and
    *structure_cases* extend coverage to non-anchor regions of the
    input space (so structural failures off the named anchors still
    show up in S) without forcing the full eval to be huge.
    """

    setup_path: Path
    anchors: dict[str, CorpusCase]
    grid: tuple[CorpusCase, ...]
    structure_cases: tuple[CorpusCase, ...]
    jitter_per_anchor: int = 3
    jitter_chaos: float = 0.05
    parts: tuple[str, ...] = ("drop",)
    bars: int = 4
    sensitivity_axes: tuple[str, ...] = ("texture", "motion", "valence", "energy")
    sensitivity_steps: int = 5

    def all_anchor_names(self) -> tuple[str, ...]:
        return tuple(self.anchors.keys())


# ----------------------------------------------------------------------
# Default corpus — used when no eval_corpus.toml is supplied.
# ----------------------------------------------------------------------


def _sonics_case(name: str) -> CorpusCase:
    texture, motion = SONICS_REGIONS[name]
    return CorpusCase(
        name=name,
        mood=_DEFAULT_SONICS_MOOD[name],
        texture=texture,
        motion=motion,
        fmt="song",
    )


def _mood_case(name: str) -> CorpusCase:
    return CorpusCase(
        name=name,
        mood=MOOD_ANCHORS[name],
        texture=0.5,
        motion=0.5,
        fmt="song",
    )


def default_corpus() -> Corpus:
    """The pre-shipped corpus: 7 anchors + small grid + format coverage."""
    anchors = {
        "acid": _sonics_case("acid"),
        "deep_techno": _sonics_case("deep_techno"),
        "psytrance": _sonics_case("psytrance"),
        "dub_techno": _sonics_case("dub_techno"),
        "happy": _mood_case("happy"),
        "sad": _mood_case("sad"),
        "brooding": _mood_case("brooding"),
    }

    # 3×3 (texture, motion) grid at neutral mood. Lightweight extra
    # discriminability coverage; small enough not to balloon scoring
    # time. Anchors are not duplicated here.
    grid_points: list[CorpusCase] = []
    for i, t in enumerate((0.25, 0.5, 0.75)):
        for j, m in enumerate((0.25, 0.5, 0.75)):
            grid_points.append(
                CorpusCase(
                    name=f"grid_{i}{j}",
                    mood=MoodSpec(valence=0.0, energy=0.0),
                    texture=t,
                    motion=m,
                    fmt="song",
                )
            )

    # One case per format archetype for structural-integrity coverage —
    # the headline S term wants the per-format checks to actually run.
    structure_cases: list[CorpusCase] = []
    for fmt in FORMAT_SPECS:  # 6 formats
        structure_cases.append(
            CorpusCase(
                name=f"struct_{fmt}",
                mood=MoodSpec(valence=0.1, energy=0.3),
                texture=0.5,
                motion=0.5,
                fmt=fmt,  # type: ignore[arg-type]
            )
        )

    return Corpus(
        setup_path=_DEFAULT_SETUP,
        anchors=anchors,
        grid=tuple(grid_points),
        structure_cases=tuple(structure_cases),
    )


# ----------------------------------------------------------------------
# TOML loader — strict on unknown keys (matches tuning.py's contract).
# ----------------------------------------------------------------------


_TOP_LEVEL_KEYS = frozenset(
    {"settings", "anchors", "grid", "structure_cases"}
)
_CASE_KEYS = frozenset(
    {"mood_valence", "mood_energy", "texture", "motion", "fmt", "chaos"}
)
_SETTINGS_KEYS = frozenset(
    {
        "setup_path",
        "parts",
        "bars",
        "jitter_per_anchor",
        "jitter_chaos",
        "sensitivity_axes",
        "sensitivity_steps",
    }
)


def load_corpus(path: Path) -> Corpus:
    """Load a corpus from TOML; missing keys keep defaults.

    Schema (all sections optional)::

        [settings]
        setup_path = "setups/iac.jtx-setup"
        parts = ["drop"]
        bars = 4
        jitter_per_anchor = 3
        jitter_chaos = 0.05

        [anchors.acid]
        mood_valence = -0.15
        mood_energy = 0.55
        texture = 0.475
        motion = 0.725
        fmt = "song"

        # ... more anchors

        [[grid]]
        # one CorpusCase per [[grid]] entry, same keys as above.

        [[structure_cases]]
        # same shape.

    Unknown sections / keys raise :class:`ValueError`.
    """
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    unknown = set(data.keys()) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(
            f"eval_corpus.toml: unknown top-level section(s): {sorted(unknown)}"
        )

    base = default_corpus()

    settings = data.get("settings", {})
    _require_mapping_keys("settings", settings, _SETTINGS_KEYS)

    setup_path = base.setup_path
    if "setup_path" in settings:
        candidate = Path(str(settings["setup_path"]))
        if not candidate.is_absolute():
            candidate = _REPO_ROOT / candidate
        setup_path = candidate

    parts = tuple(settings.get("parts", base.parts))
    bars = int(settings.get("bars", base.bars))
    jitter_per_anchor = int(
        settings.get("jitter_per_anchor", base.jitter_per_anchor)
    )
    jitter_chaos = float(settings.get("jitter_chaos", base.jitter_chaos))
    sensitivity_axes = tuple(
        settings.get("sensitivity_axes", base.sensitivity_axes)
    )
    sensitivity_steps = int(
        settings.get("sensitivity_steps", base.sensitivity_steps)
    )

    anchors = dict(base.anchors)
    if "anchors" in data:
        anchor_section = _require_mapping("anchors", data["anchors"])
        for name, case_data in anchor_section.items():
            anchors[name] = _build_case(name, case_data, default=base.anchors.get(name))

    grid_cases: list[CorpusCase] = list(base.grid)
    if "grid" in data:
        grid_list = data["grid"]
        if not isinstance(grid_list, list):
            raise ValueError("grid: expected an array of tables")
        grid_cases = [
            _build_case(f"grid_{i}", entry, default=None)
            for i, entry in enumerate(grid_list)
        ]

    structure_cases: list[CorpusCase] = list(base.structure_cases)
    if "structure_cases" in data:
        sc_list = data["structure_cases"]
        if not isinstance(sc_list, list):
            raise ValueError("structure_cases: expected an array of tables")
        structure_cases = [
            _build_case(f"struct_{i}", entry, default=None)
            for i, entry in enumerate(sc_list)
        ]

    return Corpus(
        setup_path=setup_path,
        anchors=anchors,
        grid=tuple(grid_cases),
        structure_cases=tuple(structure_cases),
        jitter_per_anchor=jitter_per_anchor,
        jitter_chaos=jitter_chaos,
        parts=parts,
        bars=bars,
        sensitivity_axes=sensitivity_axes,
        sensitivity_steps=sensitivity_steps,
    )


def _build_case(
    name: str, data: Any, *, default: CorpusCase | None
) -> CorpusCase:
    section = _require_mapping(name, data)
    unknown = set(section.keys()) - _CASE_KEYS - {"name"}
    if unknown:
        raise ValueError(f"{name}: unknown case key(s) {sorted(unknown)}")
    if default is None:
        # Minimal required: enough to compose. Fail loudly if missing.
        required = {"mood_valence", "mood_energy", "texture", "motion", "fmt"}
        missing = required - set(section.keys())
        if missing:
            raise ValueError(f"{name}: missing required key(s) {sorted(missing)}")
        case = CorpusCase(
            name=str(section.get("name", name)),
            mood=MoodSpec(
                valence=float(section["mood_valence"]),
                energy=float(section["mood_energy"]),
            ),
            texture=float(section["texture"]),
            motion=float(section["motion"]),
            fmt=str(section["fmt"]),  # type: ignore[arg-type]
            chaos=float(section.get("chaos", 0.0)),
        )
        return case

    # Patch the default.
    mood = default.mood
    if "mood_valence" in section or "mood_energy" in section:
        mood = MoodSpec(
            valence=float(section.get("mood_valence", mood.valence)),
            energy=float(section.get("mood_energy", mood.energy)),
        )
    return replace(
        default,
        name=str(section.get("name", default.name)),
        mood=mood,
        texture=float(section.get("texture", default.texture)),
        motion=float(section.get("motion", default.motion)),
        fmt=str(section.get("fmt", default.fmt)),  # type: ignore[arg-type]
        chaos=float(section.get("chaos", default.chaos)),
    )


def _require_mapping(label: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}: expected a table, got {type(value).__name__}")
    return value


def _require_mapping_keys(
    label: str, section: Any, allowed: frozenset[str]
) -> None:
    if not section:
        return
    section_map = _require_mapping(label, section)
    unknown = set(section_map.keys()) - allowed
    if unknown:
        raise ValueError(f"{label}: unknown key(s) {sorted(unknown)}")


__all__ = [
    "Corpus",
    "CorpusCase",
    "default_corpus",
    "load_corpus",
]
