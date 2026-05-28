"""Voicing stage — translate abstract events to MIDI events.

Algorithms emit abstract events (``Hit``, ``Note``, ``Param``,
``PolyAftertouch``) that name musical concepts without picking MIDI
channels or CC numbers. This stage consumes those abstract events
together with the voice's :class:`VoiceSlot` and produces the concrete
MIDI events (``NoteOn`` / ``NoteOff`` / ``ControlChange`` /
``PitchBend`` / ``ChannelPressure``) downstream.

This is **pure translation** — no MPE channel allocation, no parameter
routing. The translated MIDI events still need to pass through the
mix pass (sidechain / fade / evolution), feel pass (groove / drive /
wander), and the :class:`ParameterRouter` (CC remap, MPE allocation,
OSC dispatch) before reaching the sink. Keeping translation pure lets
the mix + feel passes operate on the same MIDI representation
regardless of whether the algorithm emitted abstract or concrete
events.

Resolutions per event kind:

* :class:`Hit` → ``NoteOn`` + ``NoteOff`` pair.
  - On a ``drum_kit`` slot, ``instrument`` keys into ``slot.kit_map``;
    the resulting ``KitPiece`` provides ``(channel, note)``. Unknown
    instrument names are silently dropped (logged at DEBUG).
  - On any other voice type, either no ``instrument`` or the
    instrument name matches the voice's name — both map to
    ``(slot.midi_channel, slot.note)``.
* :class:`Note` → ``NoteOn`` + ``NoteOff`` pair at
  ``slot.midi_channel``. MPE allocation happens later in the parameter
  router using the source channel.
* :class:`Param` → ``ControlChange`` or ``PitchBend`` with the
  ``function`` tag set. The parameter router resolves the function to
  the final target downstream.
* :class:`PolyAftertouch` → ``ChannelPressure`` tagged
  ``function="aftertouch"`` for the router to rebind under MPE.

Output ticks are bar-relative; the scheduler offsets to absolute
ticks further down the pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from jtx.engine.events import (
    ChannelPressure,
    ControlChange,
    Event,
    NoteOff,
    NoteOn,
    PitchBend,
)
from jtx.model.events import AbstractEvent, Hit, Note, Param, PolyAftertouch
from jtx.model.setup import VoiceSlot

_log = logging.getLogger(__name__)

_DRUM_NOTE_OFF_DURATION_DEFAULT = 30
"""Fallback NoteOff offset for Hit events that don't set their own.

Drum samples ignore note-off anyway; this is just MIDI-protocol
housekeeping.
"""

# Approximate "bend" pivot — abstract Param value is normalised to
# [-1, 1] for bend-style functions; PitchBend's wire format is a
# 14-bit signed int in [-8192, 8191]. We round-trip through int.
_PITCH_BEND_HALFRANGE = 8192

# Functions whose semantics are "pitch-bend like": value range [-1, 1]
# normalised on the abstract side. Everything else is [0, 1].
_BEND_FUNCTIONS: frozenset[str] = frozenset({"bend"})


def translate_abstract_events(
    abstract_events: Iterable[AbstractEvent],
    slot: VoiceSlot,
) -> list[Event]:
    """Translate abstract events → MIDI events via ``slot``.

    Pure function: returns un-routed MIDI events in input order. The
    caller (typically :class:`jtx.player.SongPlayer`) feeds the result
    through the mix pass, feel pass, and parameter router downstream.

    Mixed inputs (abstract + already-MIDI events) are allowed —
    instances of the concrete MIDI event classes pass through
    unchanged, so a transition-period algorithm that emits some
    abstract events alongside legacy concrete events still works.
    """
    out: list[Event] = []
    for ev in abstract_events:
        if isinstance(ev, Hit):
            out.extend(_hit_to_midi(ev, slot))
        elif isinstance(ev, Note):
            out.extend(_note_to_midi(ev, slot))
        elif isinstance(ev, Param):
            event = _param_to_midi(ev, slot)
            if event is not None:
                out.append(event)
        elif isinstance(ev, PolyAftertouch):
            out.append(_polyaftertouch_to_midi(ev, slot))
        elif isinstance(ev, NoteOn | NoteOff | ControlChange | PitchBend | ChannelPressure):
            # Pass-through for algorithms still emitting concrete MIDI.
            out.append(ev)
        else:  # pragma: no cover — narrowed by union
            raise TypeError(f"voicing: unsupported event {type(ev).__name__}")
    return out


def _hit_to_midi(hit: Hit, slot: VoiceSlot) -> list[Event]:
    """Resolve a Hit to a NoteOn+NoteOff pair using the slot's kit_map / note."""
    resolved = _resolve_hit_target(hit, slot)
    if resolved is None:
        return []
    channel, note = resolved
    velocity = max(1, min(127, int(hit.velocity)))
    duration = hit.duration_ticks if hit.duration_ticks > 0 else _DRUM_NOTE_OFF_DURATION_DEFAULT
    return [
        NoteOn(tick=hit.tick, channel=channel, note=note, velocity=velocity),
        NoteOff(tick=hit.tick + duration, channel=channel, note=note),
    ]


def _resolve_hit_target(hit: Hit, slot: VoiceSlot) -> tuple[int, int] | None:
    """Look up ``(channel, note)`` for ``hit`` on ``slot``.

    Returns ``None`` (and logs) for unknown instruments on a
    ``drum_kit`` slot — caller drops the event.
    """
    if slot.type == "drum_kit":
        if hit.instrument is None:
            _log.warning(
                "voicing: drum_kit voice %r received Hit with instrument=None; dropping",
                slot.name,
            )
            return None
        piece = slot.kit_map.get(hit.instrument)
        if piece is None:
            _log.debug(
                "voicing: drum_kit voice %r has no kit_map entry for instrument %r; dropping",
                slot.name,
                hit.instrument,
            )
            return None
        return (piece.channel, piece.note)
    # Single-piece drum voice (or any other type using Hit).
    # `instrument` is either None or the voice's own name — both map
    # to (slot.midi_channel, slot.note).
    return (slot.midi_channel, slot.note)


def _note_to_midi(note: Note, slot: VoiceSlot) -> list[Event]:
    """Resolve a Note to NoteOn+NoteOff at the slot's channel.

    For MPE voices, channel allocation is handled by the parameter
    router downstream; we emit on ``slot.midi_channel`` as the source
    channel.
    """
    velocity = max(1, min(127, int(note.velocity)))
    pitch = max(0, min(127, int(note.pitch)))
    return [
        NoteOn(tick=note.tick, channel=slot.midi_channel, note=pitch, velocity=velocity),
        NoteOff(tick=note.tick + note.duration_ticks, channel=slot.midi_channel, note=pitch),
    ]


def _param_to_midi(param: Param, slot: VoiceSlot) -> Event | None:
    """Convert an abstract Param into a function-tagged MIDI event.

    The parameter router resolves the function name to the actual
    target (CC#, OSC, MPE pitch-bend) using the slot's parameter_map.
    Here we just choose a wire representation suitable for the
    router's existing logic:

    * Bend-style functions emit a :class:`PitchBend` (the router will
      re-route to CC or OSC if the slot's parameter_map says so).
    * Everything else emits a :class:`ControlChange` with placeholder
      ``cc=0`` (the router replaces ``cc`` based on the target).
    """
    if param.name in _BEND_FUNCTIONS:
        bend_value = max(-_PITCH_BEND_HALFRANGE, min(
            _PITCH_BEND_HALFRANGE - 1,
            int(round(param.value * _PITCH_BEND_HALFRANGE)),
        ))
        return PitchBend(
            tick=param.tick,
            channel=slot.midi_channel,
            value=bend_value,
            function=param.name,
        )
    cc_value = max(0, min(127, int(round(param.value * 127))))
    return ControlChange(
        tick=param.tick,
        channel=slot.midi_channel,
        cc=0,
        value=cc_value,
        function=param.name,
    )


def _polyaftertouch_to_midi(pa: PolyAftertouch, slot: VoiceSlot) -> Event:
    """Convert a PolyAftertouch to a function-tagged ChannelPressure.

    Under MPE, the parameter router rebinds this onto the per-note
    channel so the receiving instrument hears it as polyphonic.
    """
    value = max(0, min(127, int(round(pa.pressure * 127))))
    return ChannelPressure(
        tick=pa.tick,
        channel=slot.midi_channel,
        value=value,
        function="aftertouch",
    )
