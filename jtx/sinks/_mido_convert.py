"""Convert jtx :class:`Event` instances to ``mido.Message`` and back.

Shared between :class:`jtx.sinks.realtime.RealtimeMidiSink` and
:class:`jtx.sinks.midifile.MidiFileSink`. Pulled out so the channel
1-vs-0 indexing fix lives in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend

if TYPE_CHECKING:  # pragma: no cover - mido has no stubs
    import mido


def event_to_mido(event: Event) -> mido.Message:
    """Translate an :class:`Event` to its ``mido.Message`` equivalent.

    MIDI channels in jtx are 1..16 (the conventional human numbering);
    mido uses 0..15 on the wire. Translation happens here so algorithm
    code never has to think about it.
    """
    import mido

    if isinstance(event, NoteOn):
        return mido.Message(
            "note_on",
            channel=event.channel - 1,
            note=event.note,
            velocity=event.velocity,
        )
    if isinstance(event, NoteOff):
        return mido.Message(
            "note_off",
            channel=event.channel - 1,
            note=event.note,
            velocity=event.velocity,
        )
    if isinstance(event, ControlChange):
        return mido.Message(
            "control_change",
            channel=event.channel - 1,
            control=event.cc,
            value=event.value,
        )
    if isinstance(event, PitchBend):
        return mido.Message(
            "pitchwheel",
            channel=event.channel - 1,
            pitch=event.value,
        )
    raise TypeError(f"unsupported event type: {type(event).__name__}")
