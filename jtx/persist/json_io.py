"""JSON load/save for ``.jtx`` (song) and ``.jtx-setup`` files.

Songs are validated at load time; structurally invalid files raise
:class:`jtx.model.ValidationError`. Setups validate their per-slot
fields the same way.

Construction from dict is hand-rolled rather than relying on a
serialisation library so the on-disk shape stays explicit and the
schema-version migration path remains under our control.

Schema v1 → v2 (Phase A) migration: ``VoiceSlot.cc_map: {fn: cc}`` is
auto-rewritten to ``parameter_map: {fn: CCTarget(cc)}`` at load time;
the in-memory ``Setup.schema_version`` is bumped to 2 so the next save
writes the new shape silently.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from jtx.model.lfo import LFO, LFOApplication
from jtx.model.parameter_target import (
    CCTarget,
    ParameterTarget,
    parameter_target_from_dict,
    parameter_target_to_dict,
)
from jtx.model.setup import Setup, VoiceSlot
from jtx.model.song import (
    ChordProgression,
    Key,
    Part,
    Song,
    VoiceConfig,
    VoiceOverride,
)
from jtx.model.types import SCHEMA_VERSION, ClockMode, LFOShape, Role, VoiceType
from jtx.model.validate import ValidationError, validate_song

# ---------------------------------------------------------------- setup


def _parameter_map_from_dict(
    d: dict[str, Any], *, schema_version: int
) -> dict[str, ParameterTarget]:
    """Parse ``parameter_map`` (v2) or migrate from ``cc_map`` (v1).

    The two field names are mutually exclusive in practice; if both
    appear, ``parameter_map`` wins (treat the file as v2 with a
    leftover ``cc_map`` field).
    """
    if "parameter_map" in d:
        raw = d.get("parameter_map") or {}
        return {fn: parameter_target_from_dict(entry) for fn, entry in raw.items()}
    if schema_version == 1 and "cc_map" in d:
        raw_cc = d.get("cc_map") or {}
        return {fn: CCTarget(cc=int(cc)) for fn, cc in raw_cc.items()}
    return {}


def _voice_slot_from_dict(d: dict[str, Any], *, schema_version: int) -> VoiceSlot:
    return VoiceSlot(
        name=d["name"],
        type=cast("VoiceType", d["type"]),
        default_role=cast("Role", d["default_role"]),
        midi_channel=d["midi_channel"],
        midi_port=d.get("midi_port"),
        kit_map=dict(d.get("kit_map", {})),
        parameter_map=_parameter_map_from_dict(d, schema_version=schema_version),
        mpe_mode=bool(d.get("mpe_mode", False)),
        mpe_channel_count=int(d.get("mpe_channel_count", 8)),
    )


def setup_from_dict(d: dict[str, Any]) -> Setup:
    file_schema_version = int(d.get("schema_version", SCHEMA_VERSION))
    setup = Setup(
        id=d["id"],
        name=d["name"],
        default_midi_port=d["default_midi_port"],
        daw_template_path=d.get("daw_template_path"),
        voices=[
            _voice_slot_from_dict(v, schema_version=file_schema_version)
            for v in d.get("voices", [])
        ],
        clock_mode=cast("ClockMode", d.get("clock_mode", "internal_master")),
        midi_clock_in_port=d.get("midi_clock_in_port"),
        schema_version=SCHEMA_VERSION,  # post-migration the in-memory copy is v2
    )
    errors = setup.validate()
    if errors:
        raise ValidationError(errors)
    return setup


def load_setup(path: Path | str) -> Setup:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return setup_from_dict(data)


def _voice_slot_to_dict(slot: VoiceSlot) -> dict[str, Any]:
    return {
        "name": slot.name,
        "type": slot.type,
        "default_role": slot.default_role,
        "midi_channel": slot.midi_channel,
        "midi_port": slot.midi_port,
        "kit_map": dict(slot.kit_map),
        "parameter_map": {
            fn: parameter_target_to_dict(target) for fn, target in slot.parameter_map.items()
        },
        "mpe_mode": slot.mpe_mode,
        "mpe_channel_count": slot.mpe_channel_count,
    }


def setup_to_dict(setup: Setup) -> dict[str, Any]:
    """Serialise a setup to its on-disk dict form.

    Hand-rolled (rather than ``asdict``) because ``ParameterTarget``
    is a discriminated sum type — ``asdict`` would lose the
    ``"kind"`` tag.
    """
    return {
        "id": setup.id,
        "name": setup.name,
        "default_midi_port": setup.default_midi_port,
        "daw_template_path": setup.daw_template_path,
        "voices": [_voice_slot_to_dict(v) for v in setup.voices],
        "clock_mode": setup.clock_mode,
        "midi_clock_in_port": setup.midi_clock_in_port,
        "schema_version": setup.schema_version,
    }


def save_setup(setup: Setup, path: Path | str) -> None:
    errors = setup.validate()
    if errors:
        raise ValidationError(errors)
    Path(path).write_text(
        json.dumps(setup_to_dict(setup), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


# ----------------------------------------------------------------- song


def _key_from_dict(d: dict[str, Any]) -> Key:
    return Key(tonic=d["tonic"], scale=d.get("scale", "minor"))


def _progression_from_dict(d: dict[str, Any] | None) -> ChordProgression | None:
    if d is None:
        return None
    return ChordProgression(
        degrees=list(d.get("degrees", [])),
        bars_per_chord=d.get("bars_per_chord", 4),
    )


def _voice_config_from_dict(d: dict[str, Any]) -> VoiceConfig:
    return VoiceConfig(
        algorithm=d["algorithm"],
        pattern=dict(d.get("pattern", {})),
        feel=dict(d.get("feel", {})),
    )


def _voice_override_from_dict(d: dict[str, Any]) -> VoiceOverride:
    return VoiceOverride(
        algorithm=d.get("algorithm"),
        key=_key_from_dict(d["key"]) if d.get("key") else None,
        meter=d.get("meter"),
        pattern=dict(d.get("pattern", {})),
        feel=dict(d.get("feel", {})),
    )


def _part_from_dict(d: dict[str, Any]) -> Part:
    return Part(
        bars=d["bars"],
        voice_overrides={
            name: _voice_override_from_dict(ov) for name, ov in d.get("voice_overrides", {}).items()
        },
        loop=bool(d.get("loop", False)),
        tempo=int(d["tempo"]) if d.get("tempo") is not None else None,
        meter=d.get("meter"),
    )


def _lfo_application_from_dict(d: dict[str, Any]) -> LFOApplication:
    return LFOApplication(part=d["part"], target=d["target"])


def _lfo_from_dict(d: dict[str, Any]) -> LFO:
    return LFO(
        name=d["name"],
        shape=cast("LFOShape", d["shape"]),
        period_bars=d["period_bars"],
        phase=d.get("phase", 0.0),
        depth=d.get("depth", 1.0),
        applications=[_lfo_application_from_dict(a) for a in d.get("applications", [])],
    )


def song_from_dict(d: dict[str, Any]) -> Song:
    # Song shape didn't change between v1 and v2 (only Setup did), so
    # we silently bump the in-memory copy to current SCHEMA_VERSION.
    # Save then re-writes with the current version.
    song = Song(
        title=d["title"],
        setup_ref=d["setup_ref"],
        key=_key_from_dict(d["key"]),
        seed_override=d.get("seed_override"),
        meter=d.get("meter", "4/4"),
        tempo=d.get("tempo", 120),
        chord_progression=_progression_from_dict(d.get("chord_progression")),
        voices={name: _voice_config_from_dict(v) for name, v in d.get("voices", {}).items()},
        parts={name: _part_from_dict(p) for name, p in d.get("parts", {}).items()},
        arrangement=list(d.get("arrangement", [])),
        lfos=[_lfo_from_dict(lfo) for lfo in d.get("lfos", [])],
        schema_version=SCHEMA_VERSION,
    )
    errors = validate_song(song)
    if errors:
        raise ValidationError(errors)
    return song


def load_song(path: Path | str) -> Song:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return song_from_dict(data)


def save_song(song: Song, path: Path | str) -> None:
    errors = validate_song(song)
    if errors:
        raise ValidationError(errors)
    Path(path).write_text(
        json.dumps(asdict(song), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
