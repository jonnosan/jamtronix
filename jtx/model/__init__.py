"""Persistence-shaped dataclasses for songs, setups, and LFOs.

This package is pure data — no Qt, no MIDI, no scheduler. The engine and
GUI both read from these dataclasses; persistence (JSON load/save) lives
in :mod:`jtx.persist`.
"""

from jtx.model.lfo import LFO, LFOApplication
from jtx.model.setup import Setup, VoiceSlot
from jtx.model.song import (
    ChordProgression,
    Key,
    KnobDict,
    KnobValue,
    Part,
    Song,
    VoiceConfig,
    VoiceOverride,
)
from jtx.model.types import (
    ROLES_BY_TYPE,
    SCHEMA_VERSION,
    LFOShape,
    Role,
    VoiceType,
)
from jtx.model.validate import ValidationError, cross_validate, validate_song

__all__ = [
    "ChordProgression",
    "Key",
    "KnobDict",
    "KnobValue",
    "LFO",
    "LFOApplication",
    "LFOShape",
    "Part",
    "ROLES_BY_TYPE",
    "Role",
    "SCHEMA_VERSION",
    "Setup",
    "Song",
    "ValidationError",
    "VoiceConfig",
    "VoiceOverride",
    "VoiceSlot",
    "VoiceType",
    "cross_validate",
    "validate_song",
]
