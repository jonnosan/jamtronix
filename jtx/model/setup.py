"""Setup + VoiceSlot — the rig description persisted as ``.jtx-setup``.

A Setup describes the MIDI rig a song talks to: the default output port, an
optional DAW template path, and a list of named voice slots (each pinned to
a MIDI channel and a voice type). Songs reference a setup by id.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jtx.model.types import ROLES_BY_TYPE, SCHEMA_VERSION, Role, VoiceType


@dataclass
class VoiceSlot:
    """One named voice in the rig."""

    name: str
    type: VoiceType
    default_role: Role
    midi_channel: int  # 1..16
    midi_port: str | None = None  # None = inherit setup default
    kit_map: dict[str, int] = field(default_factory=dict)
    """For drum voices: piece name → MIDI note. Ignored for other types."""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not (1 <= self.midi_channel <= 16):
            errors.append(f"voice {self.name!r}: midi_channel {self.midi_channel} not in 1..16")
        valid_roles = ROLES_BY_TYPE[self.type]
        if self.default_role not in valid_roles:
            errors.append(
                f"voice {self.name!r}: role {self.default_role!r} not valid for "
                f"type {self.type!r} (allowed: {', '.join(valid_roles)})"
            )
        if self.type != "drum" and self.kit_map:
            errors.append(f"voice {self.name!r}: kit_map is only meaningful for drum voices")
        return errors


@dataclass
class Setup:
    """The persisted ``.jtx-setup`` file."""

    id: str
    name: str
    default_midi_port: str
    daw_template_path: str | None = None
    voices: list[VoiceSlot] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.schema_version != SCHEMA_VERSION:
            errors.append(
                f"setup {self.id!r}: schema_version {self.schema_version} != "
                f"supported {SCHEMA_VERSION}"
            )
        names: set[str] = set()
        for slot in self.voices:
            if slot.name in names:
                errors.append(f"setup {self.id!r}: duplicate voice name {slot.name!r}")
            names.add(slot.name)
            errors.extend(slot.validate())
        return errors

    def voice(self, name: str) -> VoiceSlot | None:
        for slot in self.voices:
            if slot.name == name:
                return slot
        return None
