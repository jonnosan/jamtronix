"""``ParameterTarget`` sum type — where an abstract knob ends up.

A voice's :attr:`VoiceSlot.parameter_map` maps abstract function names
(e.g. ``"cutoff"``, ``"resonance"``, ``"bend"``) to a ``ParameterTarget``.
The sink-side
:class:`jtx.engine.parameter_router.ParameterRouter` rewrites each
function-tagged event according to the resolved target:

* :class:`CCTarget` — emit MIDI CC on the voice's channel, possibly
  with an overridden CC number.
* :class:`MPEPitchBendTarget` — emit per-note pitch bend on the
  MPE-allocated channel (instead of CC).
* :class:`MPEPressureTarget` — emit channel pressure on the
  MPE-allocated channel.
* :class:`MPETimbreTarget` — emit CC 74 on the MPE-allocated channel
  (the MPE-standard timbre slot).

Phase B (#102) will add an ``OscTarget(address: str)`` to this union.

On disk the targets serialise as ``{"kind": "...", ...}`` so adding
a new variant (with new fields) doesn't require a schema bump.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CCTarget:
    """MIDI Control Change. ``cc`` is 0..127."""

    cc: int


@dataclass(frozen=True)
class MPEPitchBendTarget:
    """Per-note pitch bend on the MPE-allocated note channel."""


@dataclass(frozen=True)
class MPEPressureTarget:
    """Per-note channel pressure on the MPE-allocated note channel."""


@dataclass(frozen=True)
class MPETimbreTarget:
    """CC 74 on the MPE-allocated note channel (MPE timbre slot)."""


ParameterTarget = CCTarget | MPEPitchBendTarget | MPEPressureTarget | MPETimbreTarget
"""Discriminated union of all v1 parameter targets."""


def parameter_target_to_dict(target: ParameterTarget) -> dict[str, Any]:
    """Serialise a target to its on-disk dict form."""
    if isinstance(target, CCTarget):
        return {"kind": "cc", "cc": int(target.cc)}
    if isinstance(target, MPEPitchBendTarget):
        return {"kind": "mpe_pitch_bend"}
    if isinstance(target, MPEPressureTarget):
        return {"kind": "mpe_pressure"}
    if isinstance(target, MPETimbreTarget):
        return {"kind": "mpe_timbre"}
    raise TypeError(f"unsupported parameter target: {type(target).__name__}")


def parameter_target_from_dict(d: dict[str, Any]) -> ParameterTarget:
    """Parse a target from its on-disk dict form.

    Raises ``ValueError`` for unknown kinds — that's the signal to the
    user that they're trying to load a setup written by a newer JTX
    (e.g. a Phase B setup with an ``"osc"`` target on a Phase A build).
    """
    kind = d.get("kind")
    if kind == "cc":
        return CCTarget(cc=int(d["cc"]))
    if kind == "mpe_pitch_bend":
        return MPEPitchBendTarget()
    if kind == "mpe_pressure":
        return MPEPressureTarget()
    if kind == "mpe_timbre":
        return MPETimbreTarget()
    raise ValueError(f"unknown parameter target kind: {kind!r}")
