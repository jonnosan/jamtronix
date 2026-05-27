"""Realtime MIDI output sink — emits events through a mido out-port.

Opens a CoreMIDI / IAC bus port on macOS via ``python-rtmidi``. The
port is a thin wrapper over rtmidi, so emit-latency is dominated by
the OS scheduler, not Python. On ``stop()`` the sink sends an
"all notes off" CC on every channel before closing the port — that
guarantees no stuck notes if playback aborts mid-bar.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jtx.engine.events import Event
from jtx.engine.sink import Sink
from jtx.sinks._mido_convert import event_to_mido

PortFactory = Callable[[str | None], Any]
"""Opens a mido out-port. Default = :func:`mido.open_output`; tests
inject a fake to avoid touching CoreMIDI."""


def _default_factory(name: str | None) -> Any:
    import mido

    return mido.open_output() if name is None else mido.open_output(name)


class RealtimeMidiSink(Sink):
    """Dispatches jtx events to a mido out-port as MIDI messages."""

    def __init__(
        self,
        port_name: str | None = None,
        *,
        port_factory: PortFactory | None = None,
    ) -> None:
        self.port_name = port_name
        self._port_factory: PortFactory = port_factory or _default_factory
        self._port: Any = None

    def start(self) -> None:
        if self._port is None:
            self._port = self._port_factory(self.port_name)

    def emit(self, event: Event) -> None:
        if self._port is None:
            raise RuntimeError("RealtimeMidiSink not started")
        self._port.send(event_to_mido(event))

    def stop(self) -> None:
        if self._port is None:
            return
        try:
            self._send_all_notes_off()
        finally:
            self._port.close()
            self._port = None

    def _send_all_notes_off(self) -> None:
        """CC 123 (All Notes Off) on every channel.

        Some hosts also need CC 120 (All Sound Off) for sustained
        notes — we'll add that if it shows up as a real problem.
        """
        import mido

        for ch0 in range(16):
            self._port.send(mido.Message("control_change", channel=ch0, control=123, value=0))
