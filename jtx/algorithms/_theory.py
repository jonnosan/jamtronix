"""Minimal music-theory helpers used by the pitched algorithms.

v1 only needs note-name → MIDI conversion and the scale-degree mode
table. The progression-degree → semitone-offset resolver lives in the
engine glue layer (later milestone) and feeds ``BarContext.chord_root_semitones``.
"""

from __future__ import annotations

# Letter (with optional accidental) → semitones above C.
_NOTE_SEMITONES: dict[str, int] = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}


def note_to_midi(tonic: str, octave: int) -> int:
    """``("C", 4) → 60``. ``("A", 2) → 45``. ``("F#", 3) → 54``.

    MIDI convention: C4 = 60 (the "middle C" used by Yamaha + most DAWs).
    Octaves below ``-1`` or above ``9`` are accepted but their resulting
    MIDI note may fall outside 0..127; clamp at use-site if needed.
    """
    if tonic not in _NOTE_SEMITONES:
        raise ValueError(f"unknown note name {tonic!r}")
    return 12 * (octave + 1) + _NOTE_SEMITONES[tonic]
