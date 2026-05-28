"""MIDI event types produced by algorithms.

Each event carries an *absolute tick* offset measured from the start of
playback. The scheduler computes the wall-clock dispatch time from the
tick using the active :class:`ClockSource`.

Events are intentionally thin — they map 1:1 to MIDI messages. Higher-
level structures (e.g. a note with both on + off) decompose into two
events at the algorithm boundary. This keeps the sort + dispatch path
trivial.

``ControlChange`` / ``PitchBend`` / ``ChannelPressure`` carry an optional
``function`` tag identifying which abstract knob produced the event
(e.g. ``"cutoff"``, ``"resonance"``, ``"bend"``). The sink-side
:class:`jtx.engine.parameter_router.ParameterRouter` consumes that tag
to rewrite the event according to the voice's parameter map (CC# remap,
MPE channel allocation, etc.). Untagged events pass through the router
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NoteOn:
    tick: int
    channel: int  # 1..16
    note: int  # 0..127
    velocity: int  # 1..127 (0 is treated as NoteOff by some hosts)


@dataclass(frozen=True)
class NoteOff:
    tick: int
    channel: int  # 1..16
    note: int  # 0..127
    velocity: int = 0  # release velocity, rarely meaningful


@dataclass(frozen=True)
class ControlChange:
    tick: int
    channel: int  # 1..16
    cc: int  # 0..127
    value: int  # 0..127
    function: str | None = None
    """Abstract knob name (``"cutoff"``, ``"resonance"``, ``"glide"``, ...).

    Consumed by the parameter router to rewrite this event per the
    voice's parameter_map. Untagged events pass through unchanged.
    """


@dataclass(frozen=True)
class PitchBend:
    tick: int
    channel: int  # 1..16
    value: int  # 14-bit signed, -8192..8191
    function: str | None = None


@dataclass(frozen=True)
class ChannelPressure:
    """MIDI channel pressure (aftertouch).

    Distinct from polyphonic key pressure (per-note aftertouch); under
    MPE the receiving instrument interprets channel pressure as
    per-note expression because each MPE note owns its own channel.
    """

    tick: int
    channel: int  # 1..16
    value: int  # 0..127
    function: str | None = None


Event = NoteOn | NoteOff | ControlChange | PitchBend | ChannelPressure
"""Discriminated union of the MIDI message types jtx emits."""
