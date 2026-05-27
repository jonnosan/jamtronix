"""Song dataclasses — the persisted ``.jtx`` shape.

See ``docs/SPEC.md`` §Persistence Format for the JSON example this model
mirrors. Validation lives in :mod:`jtx.model.validate`; that module knows
about cross-references (follower cycles, arrangement parts, etc.) that
individual dataclasses can't see in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jtx.model.lfo import LFO
from jtx.model.types import SCHEMA_VERSION

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
    """Song-level configuration for one voice slot."""

    algorithm: str
    pattern: KnobDict = field(default_factory=dict)
    feel: KnobDict = field(default_factory=dict)


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
    feel: KnobDict = field(default_factory=dict)


@dataclass
class Part:
    bars: int
    voice_overrides: dict[str, VoiceOverride] = field(default_factory=dict)


@dataclass
class Song:
    title: str
    setup_ref: str
    key: Key
    seed_override: int | None = None
    meter: str = "4/4"
    tempo: int = 120
    chord_progression: ChordProgression | None = None
    voices: dict[str, VoiceConfig] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    arrangement: list[str] = field(default_factory=list)
    lfos: list[LFO] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
