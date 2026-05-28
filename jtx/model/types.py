"""Shared literals + role tables used across the data model."""

from __future__ import annotations

from typing import Literal

VoiceType = Literal["drum", "mono", "poly", "modulator", "follower"]

Role = Literal[
    "drum",
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

SCHEMA_VERSION = 2
"""Bump when the on-disk JSON shape changes incompatibly.

* v1 → v2 (Phase A): ``VoiceSlot.cc_map: {fn: cc}`` replaced by
  ``parameter_map: {fn: ParameterTarget}``; added ``mpe_mode`` +
  ``mpe_channel_count``. ``persist.json_io.load_setup`` auto-migrates
  v1 files at load time (cc_map entries become ``CCTarget``s).
"""
