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

SCHEMA_VERSION = 1
"""Bump when the on-disk JSON shape changes incompatibly."""
