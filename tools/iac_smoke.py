"""Manual IAC smoke test.

Plays a short ascending scale through the named output port (default
``IAC Driver Bus 1``). Use to confirm a real macOS CoreMIDI route
before wiring the GUI.

Setup:

    Audio MIDI Setup → MIDI Studio → IAC Driver → "Device is online".

Run:

    .venv/bin/python tools/iac_smoke.py
    .venv/bin/python tools/iac_smoke.py "IAC Driver Bus 2"

Not part of the automated test suite — touching CoreMIDI requires a
real Mac with IAC enabled.
"""

from __future__ import annotations

import sys
import time

from jtx.engine.events import NoteOff, NoteOn
from jtx.sinks import RealtimeMidiSink


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "IAC Driver Bus 1"
    sink = RealtimeMidiSink(port_name=port)
    sink.start()
    try:
        scale = [60, 62, 64, 65, 67, 69, 71, 72]
        for n in scale:
            sink.emit(NoteOn(tick=0, channel=1, note=n, velocity=100))
            time.sleep(0.18)
            sink.emit(NoteOff(tick=0, channel=1, note=n))
            time.sleep(0.02)
    finally:
        sink.stop()


if __name__ == "__main__":
    main()
