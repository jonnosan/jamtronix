#!/usr/bin/env python3
"""Fire jtx's 8 standard CCs one-by-one to drive MIDI Learn on a Live rack.

For each CC in turn:
* Sends the CC on channel 1 of ``IAC Driver Bus 1`` once per second with a
  slowly-cycling value (0 → 32 → 64 → 96 → 127 → 96 → 64 → 32 → loop) so
  Live's MIDI Map mode picks it up reliably.
* Waits for you to press Enter, then moves to the next CC.

Workflow:
    1. In Live, drop a fresh ``JtxCCRack`` (or any empty Instrument Rack
       with 8 Macros) on a track.
    2. Click Live's **MIDI** button (top-right) to enter MIDI Map mode.
    3. Run this script.
    4. When ``Cutoff (CC74)`` appears, click Macro 1.
    5. Press Enter to move to ``Resonance``; click Macro 2.
    6. Repeat through all 8.

Run:
    .venv/bin/python tools/midi_learn_helper.py
"""

from __future__ import annotations

import select
import sys
import time

import mido

PORT_NAME = "IAC Driver Bus 1"

CCS: tuple[tuple[int, str], ...] = (
    (74, "Cutoff"),
    (71, "Resonance"),
    (5, "Glide"),
    (65, "Port"),
    (1, "Mod"),
    (102, "Aux 1"),
    (103, "Aux 2"),
    (104, "Aux 3"),
)

# Slow cyclic sweep — Live's MIDI Learn fires on any incoming CC, but a
# moving value confirms visually that the Macro responds after assignment.
SWEEP_VALUES = (0, 32, 64, 96, 127, 96, 64, 32)


def _wait_for_enter(timeout: float) -> bool:
    """Block on stdin up to *timeout* seconds. Return True if Enter pressed."""
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        sys.stdin.readline()  # consume the buffered line
        return True
    return False


def main() -> None:
    print(f"Opening MIDI output: {PORT_NAME}")
    try:
        out = mido.open_output(PORT_NAME)
    except OSError as exc:
        print(f"failed to open '{PORT_NAME}': {exc}")
        print("available ports:")
        for name in mido.get_output_names():
            print(f"  {name}")
        sys.exit(1)

    try:
        total = len(CCS)
        for index, (cc, label) in enumerate(CCS, start=1):
            print()
            print(f"=== [{index}/{total}] {label} (CC{cc}) — press Enter for next ===")
            tick = 0
            while True:
                value = SWEEP_VALUES[tick % len(SWEEP_VALUES)]
                out.send(
                    mido.Message(
                        "control_change",
                        channel=0,
                        control=cc,
                        value=value,
                    )
                )
                print(f"  CC{cc} = {value}")
                tick += 1
                if _wait_for_enter(1.0):
                    break
        print()
        print("done — all 8 CCs streamed")
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        out.close()


if __name__ == "__main__":
    main()
