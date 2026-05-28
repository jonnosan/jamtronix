"""Setup + VoiceSlot — the rig description persisted as ``.jtx-setup``.

A Setup describes the MIDI rig a song talks to: the default output port, an
optional DAW template path, and a list of named voice slots (each pinned to
a MIDI channel and a voice type). Songs reference a setup by id.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jtx.model.parameter_target import CCTarget, ParameterTarget
from jtx.model.types import ROLES_BY_TYPE, SCHEMA_VERSION, ClockMode, Role, VoiceType

_GM_DRUM_KICK_NOTE = 36


@dataclass(frozen=True)
class KitPiece:
    """One piece within a drum_kit voice's kit_map.

    Each piece carries its own ``(channel, note)`` so a kit can spread
    across multiple MIDI channels — e.g. kick on ch9, percussion on
    ch11.
    """

    note: int  # 0..127
    channel: int  # 1..16


@dataclass
class VoiceSlot:
    """One named voice in the rig."""

    name: str
    type: VoiceType
    default_role: Role
    midi_channel: int  # 1..16
    midi_port: str | None = None  # None = inherit setup default
    note: int = _GM_DRUM_KICK_NOTE
    """For single-piece ``drum`` voices: the MIDI note this voice
    triggers. Ignored for ``drum_kit`` (which uses per-piece notes
    in ``kit_map``) and for non-drum voice types."""
    kit_map: dict[str, "KitPiece"] = field(default_factory=dict)
    """For ``drum_kit`` voices: piece name → :class:`KitPiece`
    ``(note, channel)``. Each piece can live on its own MIDI channel.
    Empty / ignored for other voice types."""
    parameter_map: dict[str, ParameterTarget] = field(default_factory=dict)
    """Function-name → :class:`ParameterTarget` override.

    Algorithms emit function-tagged events (``ControlChange`` /
    ``PitchBend`` / ``ChannelPressure`` with
    ``function="cutoff"``/``"resonance"``/etc.); the sink-side
    :class:`jtx.engine.parameter_router.ParameterRouter` rewrites each
    event per this map (CC remap, MPE channel allocation, etc.). Lookup
    falls back to the algorithm's ``DEFAULT_PARAM_MAP`` if a function
    is unset here.
    """
    mpe_mode: bool = False
    """If True, the voice spans an MPE channel block starting at
    ``midi_channel``. NoteOns round-robin through the block; tagged
    pitch-bend / pressure / timbre events ride per-note channels."""
    mpe_channel_count: int = 8
    """How many channels the MPE block spans starting at ``midi_channel``.

    Only honoured when ``mpe_mode`` is True. Default 8 matches typical
    MPE-aware instruments (Ableton Sampler, Wavetable, Drift, Meld).
    """

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not (1 <= self.midi_channel <= 16):
            errors.append(f"voice {self.name!r}: midi_channel {self.midi_channel} not in 1..16")
        if not (0 <= self.note <= 127):
            errors.append(f"voice {self.name!r}: note {self.note} not in 0..127")
        valid_roles = ROLES_BY_TYPE[self.type]
        if self.default_role not in valid_roles:
            errors.append(
                f"voice {self.name!r}: role {self.default_role!r} not valid for "
                f"type {self.type!r} (allowed: {', '.join(valid_roles)})"
            )
        if self.type != "drum_kit" and self.kit_map:
            errors.append(
                f"voice {self.name!r}: kit_map is only meaningful for drum_kit voices "
                f"(single-piece drum voices use the `note` field)"
            )
        if self.type == "drum_kit":
            if not self.kit_map:
                errors.append(
                    f"voice {self.name!r}: drum_kit voice requires at least one kit_map entry"
                )
            seen: dict[tuple[int, int], str] = {}
            for piece_name, piece in self.kit_map.items():
                if not (1 <= piece.channel <= 16):
                    errors.append(
                        f"voice {self.name!r}: kit_map[{piece_name!r}].channel "
                        f"{piece.channel} not in 1..16"
                    )
                if not (0 <= piece.note <= 127):
                    errors.append(
                        f"voice {self.name!r}: kit_map[{piece_name!r}].note "
                        f"{piece.note} not in 0..127"
                    )
                key = (piece.channel, piece.note)
                if key in seen:
                    errors.append(
                        f"voice {self.name!r}: kit_map[{piece_name!r}] and "
                        f"kit_map[{seen[key]!r}] share (channel={piece.channel}, "
                        f"note={piece.note}); piece identity must be unique"
                    )
                else:
                    seen[key] = piece_name
        for func, target in self.parameter_map.items():
            if isinstance(target, CCTarget) and not (0 <= int(target.cc) <= 127):
                errors.append(
                    f"voice {self.name!r}: parameter_map[{func!r}].cc = {target.cc} not in 0..127"
                )
        if self.mpe_mode:
            if self.midi_channel == 1:
                errors.append(
                    f"voice {self.name!r}: mpe_mode collides with reserved MPE master "
                    f"channel 1; pick midi_channel in 2..16"
                )
            if self.mpe_channel_count < 1:
                errors.append(
                    f"voice {self.name!r}: mpe_channel_count {self.mpe_channel_count} < 1"
                )
            block_end = self.midi_channel + self.mpe_channel_count - 1
            if block_end > 16:
                errors.append(
                    f"voice {self.name!r}: MPE block ends at channel {block_end} (> 16); "
                    f"reduce mpe_channel_count or midi_channel"
                )
        return errors


@dataclass
class Setup:
    """The persisted ``.jtx-setup`` file."""

    id: str
    name: str
    default_midi_port: str
    daw_template_path: str | None = None
    voices: list[VoiceSlot] = field(default_factory=list)
    clock_mode: ClockMode = "internal_master"
    """Default clock source the GUI/CLI selects unless overridden."""
    midi_clock_in_port: str | None = None
    """MIDI-in port name to listen on when ``clock_mode == midi_clock_slave``."""
    osc_host: str = "127.0.0.1"
    """Host the sink-side parameter router sends OSC messages to.

    Used only by voices with an :class:`OscTarget` in their
    ``parameter_map``. Defaults to localhost; users with an OSC
    consumer on the same machine (custom Max patch, TouchDesigner,
    hardware OSC bridge) don't need to change this.
    """
    osc_port: int = 11000
    """UDP port the OSC client targets. The user's OSC consumer must
    listen on the same port."""
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.schema_version != SCHEMA_VERSION:
            errors.append(
                f"setup {self.id!r}: schema_version {self.schema_version} != "
                f"supported {SCHEMA_VERSION}"
            )
        if self.clock_mode == "midi_clock_slave" and not self.midi_clock_in_port:
            errors.append(
                f"setup {self.id!r}: clock_mode 'midi_clock_slave' requires midi_clock_in_port"
            )
        if not (1 <= self.osc_port <= 65535):
            errors.append(f"setup {self.id!r}: osc_port {self.osc_port} not in 1..65535")
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
