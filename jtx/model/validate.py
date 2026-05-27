"""Cross-reference validation for Song / Setup pairs.

Per-dataclass field checks live on the dataclass itself (e.g.
:meth:`jtx.model.setup.Setup.validate`). This module covers the
relationships that span dataclasses: follower cycles, arrangement
parts, LFO application targets, song↔setup voice agreement.
"""

from __future__ import annotations

from jtx.model.setup import Setup
from jtx.model.song import Song
from jtx.model.types import SCHEMA_VERSION


class ValidationError(ValueError):
    """Raised when a Song / Setup fails validation at load time."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_song(song: Song) -> list[str]:
    """Return a list of structural problems with *song*.

    "Structural" means anything checkable without a Setup: schema
    version, arrangement-vs-parts, follower source existence + cycles,
    LFO application parts.
    """
    errors: list[str] = []

    if song.schema_version != SCHEMA_VERSION:
        errors.append(
            f"song {song.title!r}: schema_version {song.schema_version} != "
            f"supported {SCHEMA_VERSION}"
        )

    # Arrangement parts must exist.
    for name in song.arrangement:
        if name not in song.parts:
            errors.append(f"arrangement references unknown part {name!r}")

    # Voice override references must point at known song voices.
    for pname, part in song.parts.items():
        for vname in part.voice_overrides:
            if vname not in song.voices:
                errors.append(f"part {pname!r} overrides unknown voice {vname!r}")

    # Follower sources must exist and not form cycles.
    follower_source: dict[str, str] = {}
    for vname, cfg in song.voices.items():
        if cfg.algorithm != "voice_follower":
            continue
        source = cfg.pattern.get("source")
        if not isinstance(source, str) or not source:
            errors.append(f"follower {vname!r}: missing 'source' in pattern knobs")
            continue
        if source not in song.voices:
            errors.append(f"follower {vname!r}: source {source!r} not in song voices")
            continue
        if source == vname:
            errors.append(f"follower {vname!r}: source cannot be self")
            continue
        follower_source[vname] = source

    for start in follower_source:
        seen: set[str] = set()
        cur: str | None = start
        while cur is not None and cur in follower_source:
            if cur in seen:
                errors.append(f"follower cycle detected involving {start!r}")
                break
            seen.add(cur)
            cur = follower_source.get(cur)

    # LFO application targets reference known parts.
    for lfo in song.lfos:
        errors.extend(lfo.validate())
        for app in lfo.applications:
            if app.part not in song.parts:
                errors.append(f"lfo {lfo.name!r}: application in unknown part {app.part!r}")

    return errors


def cross_validate(song: Song, setup: Setup) -> list[str]:
    """Return problems specific to the (song, setup) pairing.

    Catches voices in the song that don't have a corresponding slot in
    the setup. Also re-runs :func:`validate_song` so callers only need
    one entry point when both objects are available.
    """
    errors: list[str] = list(validate_song(song))
    errors.extend(setup.validate())

    slot_names = {slot.name for slot in setup.voices}
    for vname in song.voices:
        if vname not in slot_names:
            errors.append(f"voice {vname!r} not found in setup {setup.id!r}")
    return errors
