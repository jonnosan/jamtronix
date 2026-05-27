"""Sink tests — RealtimeMidiSink with a fake port, MidiFileSink with round-trip read-back."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mido
import pytest

from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend
from jtx.sinks import MidiFileSink, RealtimeMidiSink


class FakePort:
    """Stand-in for a mido out-port — records sends + close calls."""

    def __init__(self) -> None:
        self.sent: list[mido.Message] = []
        self.closed = False

    def send(self, msg: mido.Message) -> None:
        self.sent.append(msg)

    def close(self) -> None:
        self.closed = True


def _make_realtime_sink() -> tuple[RealtimeMidiSink, FakePort]:
    fake = FakePort()

    def factory(_name: str | None) -> Any:
        return fake

    return RealtimeMidiSink(port_name="IAC fake", port_factory=factory), fake


def test_realtime_translates_note_on() -> None:
    sink, port = _make_realtime_sink()
    sink.start()
    sink.emit(NoteOn(tick=0, channel=2, note=60, velocity=100))
    msg = port.sent[0]
    assert msg.type == "note_on"
    assert msg.channel == 1  # 2 (jtx 1-based) → 1 (mido 0-based)
    assert msg.note == 60
    assert msg.velocity == 100


def test_realtime_translates_all_event_kinds() -> None:
    sink, port = _make_realtime_sink()
    sink.start()
    events: list[Event] = [
        NoteOn(tick=0, channel=1, note=60, velocity=100),
        NoteOff(tick=10, channel=1, note=60),
        ControlChange(tick=20, channel=2, cc=74, value=64),
        PitchBend(tick=30, channel=2, value=4096),
    ]
    for ev in events:
        sink.emit(ev)
    sink.stop()  # stop emits 16 all-notes-off CCs

    kinds = [m.type for m in port.sent]
    # First four are the events, then 16 all-notes-off (control_change).
    assert kinds[:4] == ["note_on", "note_off", "control_change", "pitchwheel"]
    assert len(port.sent) == 4 + 16
    assert all(m.type == "control_change" and m.control == 123 for m in port.sent[4:])


def test_realtime_stop_sends_all_notes_off_on_every_channel() -> None:
    sink, port = _make_realtime_sink()
    sink.start()
    sink.stop()
    cc_msgs = [m for m in port.sent if m.type == "control_change"]
    assert len(cc_msgs) == 16
    channels = sorted(m.channel for m in cc_msgs)
    assert channels == list(range(16))
    assert all(m.control == 123 and m.value == 0 for m in cc_msgs)
    assert port.closed


def test_realtime_emit_before_start_raises() -> None:
    sink = RealtimeMidiSink(port_factory=lambda _n: FakePort())
    with pytest.raises(RuntimeError, match="not started"):
        sink.emit(NoteOn(tick=0, channel=1, note=60, velocity=100))


def test_realtime_start_is_idempotent() -> None:
    factory_calls = 0

    def factory(_name: str | None) -> Any:
        nonlocal factory_calls
        factory_calls += 1
        return FakePort()

    sink = RealtimeMidiSink(port_factory=factory)
    sink.start()
    sink.start()
    assert factory_calls == 1


def test_midifile_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "out.mid"
    sink = MidiFileSink(path, ppq=480)
    sink.start()
    sink.emit(NoteOn(tick=0, channel=1, note=60, velocity=100))
    sink.emit(NoteOff(tick=240, channel=1, note=60))
    sink.emit(ControlChange(tick=480, channel=2, cc=74, value=64))
    sink.emit(NoteOn(tick=720, channel=1, note=72, velocity=90))
    sink.emit(NoteOff(tick=960, channel=1, note=72))
    sink.stop()

    assert path.exists()
    mf = mido.MidiFile(path)
    assert mf.ticks_per_beat == 480
    assert mf.type == 0
    msgs = [m for m in mf.tracks[0] if not m.is_meta]
    assert len(msgs) == 5
    # Delta-time encoding: cumulative ticks reconstruct absolute ticks.
    cum = 0
    abs_ticks: list[int] = []
    for m in mf.tracks[0]:
        cum += m.time
        if not m.is_meta:
            abs_ticks.append(cum)
    assert abs_ticks == [0, 240, 480, 720, 960]


def test_midifile_sorts_events_before_writing(tmp_path: Path) -> None:
    """Even if emit() is called out of tick order, the file is sorted."""
    path = tmp_path / "out.mid"
    sink = MidiFileSink(path, ppq=480)
    sink.start()
    sink.emit(NoteOff(tick=240, channel=1, note=60))  # later
    sink.emit(NoteOn(tick=0, channel=1, note=60, velocity=100))  # earlier
    sink.stop()

    mf = mido.MidiFile(path)
    cum = 0
    order: list[tuple[int, str]] = []
    for m in mf.tracks[0]:
        cum += m.time
        if not m.is_meta:
            order.append((cum, m.type))
    assert order == [(0, "note_on"), (240, "note_off")]


def test_midifile_ends_with_end_of_track_meta(tmp_path: Path) -> None:
    path = tmp_path / "out.mid"
    sink = MidiFileSink(path)
    sink.start()
    sink.stop()  # no events at all

    mf = mido.MidiFile(path)
    last = mf.tracks[0][-1]
    assert last.is_meta and last.type == "end_of_track"


def test_midifile_translates_channel_correctly(tmp_path: Path) -> None:
    """jtx channel 10 (drums) must write as mido channel 9."""
    path = tmp_path / "drums.mid"
    sink = MidiFileSink(path)
    sink.start()
    sink.emit(NoteOn(tick=0, channel=10, note=36, velocity=120))
    sink.stop()

    mf = mido.MidiFile(path)
    note_on = next(m for m in mf.tracks[0] if not m.is_meta)
    assert note_on.channel == 9
