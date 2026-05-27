"""MIDI event types produced by algorithms.

Each event carries an *absolute tick* offset measured from the start of
playback. The scheduler computes the wall-clock dispatch time from the
tick using the active :class:`ClockSource`.

Events are intentionally thin — they map 1:1 to MIDI messages. Higher-
level structures (e.g. a note with both on + off) decompose into two
events at the algorithm boundary. This keeps the sort + dispatch path
trivial.
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


@dataclass(frozen=True)
class PitchBend:
    tick: int
    channel: int  # 1..16
    value: int  # 14-bit signed, -8192..8191


Event = NoteOn | NoteOff | ControlChange | PitchBend
"""Discriminated union of the four MIDI message types jtx emits."""
