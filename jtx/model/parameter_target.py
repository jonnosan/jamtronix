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
* :class:`OscTarget` — send an OSC message at the given address
  instead of MIDI. The router calls the configured OSC client
  out-of-band and produces no MIDI event for this source.

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


@dataclass(frozen=True)
class OscTarget:
    """Send the parameter as an OSC message at ``address``.

    The router consults the active OSC client (configured via
    :attr:`Setup.osc_host` / :attr:`Setup.osc_port` and passed into the
    :class:`ParameterRouter`) and emits no MIDI event for sources
    bound to this target. The value is normalised to a float — CC-style
    sources land in ``[0, 1]``; PitchBend-style sources (``"bend"``)
    land in ``[-1, 1]``.
    """

    address: str


ParameterTarget = CCTarget | MPEPitchBendTarget | MPEPressureTarget | MPETimbreTarget | OscTarget
"""Discriminated union of all parameter targets (Phases A + B)."""


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
    if isinstance(target, OscTarget):
        return {"kind": "osc", "address": target.address}
    raise TypeError(f"unsupported parameter target: {type(target).__name__}")


def parameter_target_from_dict(d: dict[str, Any]) -> ParameterTarget:
    """Parse a target from its on-disk dict form.

    Raises ``ValueError`` for unknown kinds — that's the signal to the
    user that they're trying to load a setup written by a newer JTX.
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
    if kind == "osc":
        return OscTarget(address=str(d["address"]))
    raise ValueError(f"unknown parameter target kind: {kind!r}")
