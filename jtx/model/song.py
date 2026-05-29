"""Song dataclasses — the persisted ``.jtx`` shape.

See ``docs/SPEC.md`` §Persistence Format for the JSON example this model
mirrors. Validation lives in :mod:`jtx.model.validate`; that module knows
about cross-references (follower cycles, arrangement parts, etc.) that
individual dataclasses can't see in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jtx.model.composer_types import FormatType, MoodSpec
from jtx.model.lfo import LFO
from jtx.model.types import SCHEMA_VERSION

_DEFAULT_MOOD = MoodSpec(valence=0.0, energy=0.0, chaos=0.0)

# Knob payloads are JSON-shaped: numbers / strings / bools / lists / nested
# dicts. We don't try to type them at this layer — the algorithm registry
# will validate against per-algorithm schemas in a later milestone.
KnobValue = Any
KnobDict = dict[str, KnobValue]


@dataclass
class Key:
    """A musical key — tonic letter (with optional accidental) + scale name."""

    tonic: str
    scale: str = "minor"


@dataclass
class ChordProgression:
    """Roman-numeral degrees + bars-per-chord, evaluated against the song key."""

    degrees: list[str] = field(default_factory=list)
    bars_per_chord: int = 4


@dataclass
class VoiceConfig:
    """Song-level configuration for one voice slot.

    ``mix`` carries per-voice mix-pass knobs (sidechain, fade,
    evolution). Per-voice "feel" knobs are gone — feel is now song-wide
    in :class:`Song.feel`.
    """

    algorithm: str
    pattern: KnobDict = field(default_factory=dict)
    mix: KnobDict = field(default_factory=dict)


@dataclass
class VoiceOverride:
    """Per-part override for one voice.

    Every field is optional. Unset fields inherit from the song-level
    :class:`VoiceConfig`. The knob dicts are *partial* — only the
    overridden keys are listed.
    """

    algorithm: str | None = None
    key: Key | None = None
    meter: str | None = None
    pattern: KnobDict = field(default_factory=dict)
    mix: KnobDict = field(default_factory=dict)


@dataclass
class Part:
    bars: int
    intensity_start: float = 0.5
    """Normalized 0..1 intensity at the part's first bar. Algorithms
    that read ``BarContext.part_intensity`` shape their density / fill
    behaviour from this. Combine with :attr:`intensity_end` to define
    an envelope across the part (e.g. 0.35 → 0.95 in a build-up)."""
    intensity_end: float = 0.5
    """Normalized 0..1 intensity at the part's last bar (linear interp
    from :attr:`intensity_start`)."""
    voice_overrides: dict[str, VoiceOverride] = field(default_factory=dict)
    loop: bool = False
    """When the part's last bar finishes, ``loop`` decides what plays next.

    * ``True`` — the part replays from bar 0 (jam-friendly: hold here).
    * ``False`` — the transport advances to the next part in
      ``song.parts`` dict order, wrapping at the end.
    """
    tempo: int | None = None
    """Part-level tempo override in BPM. ``None`` = use the song tempo."""
    meter: str | None = None
    """Part-level meter override (e.g. ``"3/4"``). ``None`` = song meter."""


def _default_global_feel() -> dict[str, float]:
    """Five song-wide feel knobs, all default zero (no effect)."""
    return {"pump": 0.0, "groove": 0.0, "drive": 0.0, "tension": 0.0, "wander": 0.0}


@dataclass
class Song:
    title: str
    setup_ref: str
    key: Key
    seed_override: int | None = None
    meter: str = "4/4"
    mood: MoodSpec = _DEFAULT_MOOD
    """Composer-time mood the song was generated from
    (valence × energy + chaos). Persisted so re-rolling can start from
    the same pad position and so the GUI can reflect it when loading."""
    format: FormatType = "song"
    """Structural archetype the song was generated from (sting / jingle
    / loop / ramp / song / anthem). Persisted alongside :attr:`mood`."""
    tempo: int = 120
    chord_progression: ChordProgression | None = None
    voices: dict[str, VoiceConfig] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    arrangement: list[str] = field(default_factory=list)
    lfos: list[LFO] = field(default_factory=list)
    feel: dict[str, float] = field(default_factory=_default_global_feel)
    """Song-wide feel knobs: ``pump``, ``groove``, ``drive``,
    ``tension``, ``wander``. Each in ``[0, 1]``. See
    :mod:`jtx.engine.feel` and :mod:`jtx.engine.global_feel` for the
    technical translations to mix-pass + feel-pass behaviours."""
    schema_version: int = SCHEMA_VERSION
