"""JSON load/save for ``.jtx`` (song) and ``.jtx-setup`` files.

Songs are validated at load time; structurally invalid files raise
:class:`jtx.model.ValidationError`. Setups validate their per-slot
fields the same way.

Construction from dict is hand-rolled rather than relying on a
serialisation library so the on-disk shape stays explicit and the
schema-version migration path remains under our control.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from jtx.model.lfo import LFO, LFOApplication
from jtx.model.setup import Setup, VoiceSlot
from jtx.model.song import (
    ChordProgression,
    Key,
    Part,
    Song,
    VoiceConfig,
    VoiceOverride,
)
from jtx.model.types import ClockMode, LFOShape, Role, VoiceType
from jtx.model.validate import ValidationError, validate_song

# ---------------------------------------------------------------- setup


def _voice_slot_from_dict(d: dict[str, Any]) -> VoiceSlot:
    return VoiceSlot(
        name=d["name"],
        type=cast(VoiceType, d["type"]),
        default_role=cast(Role, d["default_role"]),
        midi_channel=d["midi_channel"],
        midi_port=d.get("midi_port"),
        kit_map=dict(d.get("kit_map", {})),
        cc_map={k: int(v) for k, v in d.get("cc_map", {}).items()},
    )


def setup_from_dict(d: dict[str, Any]) -> Setup:
    setup = Setup(
        id=d["id"],
        name=d["name"],
        default_midi_port=d["default_midi_port"],
        daw_template_path=d.get("daw_template_path"),
        voices=[_voice_slot_from_dict(v) for v in d.get("voices", [])],
        clock_mode=cast(ClockMode, d.get("clock_mode", "internal_master")),
        midi_clock_in_port=d.get("midi_clock_in_port"),
        schema_version=d.get("schema_version", 1),
    )
    errors = setup.validate()
    if errors:
        raise ValidationError(errors)
    return setup


def load_setup(path: Path | str) -> Setup:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return setup_from_dict(data)


def save_setup(setup: Setup, path: Path | str) -> None:
    errors = setup.validate()
    if errors:
        raise ValidationError(errors)
    Path(path).write_text(
        json.dumps(asdict(setup), indent=2, sort_keys=False) + "\n",
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
    )


def _lfo_application_from_dict(d: dict[str, Any]) -> LFOApplication:
    return LFOApplication(part=d["part"], target=d["target"])


def _lfo_from_dict(d: dict[str, Any]) -> LFO:
    return LFO(
        name=d["name"],
        shape=cast(LFOShape, d["shape"]),
        period_bars=d["period_bars"],
        phase=d.get("phase", 0.0),
        depth=d.get("depth", 1.0),
        applications=[_lfo_application_from_dict(a) for a in d.get("applications", [])],
    )


def song_from_dict(d: dict[str, Any]) -> Song:
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
        schema_version=d.get("schema_version", 1),
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
