"""Shared literals + role tables used across the data model."""

from __future__ import annotations

from typing import Literal

VoiceType = Literal["drum", "drum_kit", "mono", "poly", "modulator", "follower"]

Role = Literal[
    "drum",
    "drum_kit",
    "bass",
    "lead",
    "pad",
    "stab",
    "chord",
    "modulator",
    "follower",
]

ROLES_BY_TYPE: dict[VoiceType, tuple[Role, ...]] = {
    "drum": ("drum",),
    "drum_kit": ("drum_kit",),
    "mono": ("bass", "lead"),
    "poly": ("pad", "stab", "chord"),
    "modulator": ("modulator",),
    "follower": ("follower",),
}

LFOShape = Literal["sine", "tri", "saw", "ramp", "square", "random", "sh"]

ClockMode = Literal["internal_master", "midi_clock_slave", "ableton_link"]
"""Setup-level default for which clock source drives playback.

The CLI / GUI can override at runtime. ``ableton_link`` is wired but
its concrete binding is deferred (see ``jtx.engine.AbletonLinkClock``);
selecting it will raise until that's resolved.
"""

SCHEMA_VERSION = 5
"""Bump when the on-disk JSON shape changes incompatibly.

* v1 → v2 (Phase A): ``VoiceSlot.cc_map: {fn: cc}`` replaced by
  ``parameter_map: {fn: ParameterTarget}``. ``persist.json_io.load_setup``
  auto-migrates v1 files at load time (cc_map entries become
  ``CCTarget``s).
* v2 → v3 (drum-kit + global feel): adds ``drum_kit`` voice type;
  ``VoiceSlot.kit_map`` now maps piece-name → ``KitPiece(note,
  channel)`` (drum_kit voices only) and a new ``VoiceSlot.note``
  carries the MIDI note for single-piece ``drum`` voices.
  ``VoiceConfig.feel`` / ``VoiceOverride.feel`` are renamed to
  ``mix`` and shrunk to mix-pass keys (sidechain / fade / evolution).
  ``Song.feel`` becomes a song-level dict with five keys
  (pump, groove, drive, tension, wander). ``Part.intensity_start``
  + ``intensity_end`` envelope each part. No migration path —
  re-generate songs from templates.
* v3 → v4 (mood + format composer): ``Song.mood`` (MoodSpec) and
  ``Song.format`` (FormatType literal) become first-class persisted
  fields, replacing the implicit style-template heritage. No
  migration path — pre-v4 ``.jtx`` files are rejected at load time;
  regenerate via :func:`jtx.composer.compose` (Composer GUI lands in
  PR 4).
* v4 → v5 (texture + motion axes): ``Song.texture`` and
  ``Song.motion`` (floats in ``[0, 1]``) become first-class
  persisted fields alongside ``mood`` and ``format``. They drive
  voice activation thresholds, algorithm shortlists, and filter LFO
  parameters in :mod:`jtx.composer`. No migration path — pre-v5
  ``.jtx`` files are rejected at load time; regenerate via
  :func:`jtx.composer.compose` (epic #134).

The MPE drop (no composer path ever produced MPE output) silently
removes ``VoiceSlot.mpe_mode`` / ``mpe_channel_count`` and the
MPE-target ParameterTarget variants. Old setup files load fine —
the loader just ignores the absent fields — so no version bump was
needed.
"""
