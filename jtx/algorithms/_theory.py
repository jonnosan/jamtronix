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


# Scale → semitone offsets from the tonic (ascending one octave).
# Add new modes here as needed; the algorithms fall back to "minor"
# when a song requests an unknown scale.
_SCALES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    # 5-note scales — fewer degrees per octave; melodic_line and arp
    # voices treat them as scale subsets, which means tighter, more
    # consonant lines (no avoid-notes to dodge).
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "major_pentatonic": (0, 2, 4, 7, 9),
}


def scale_intervals(scale: str) -> tuple[int, ...]:
    """Semitone offsets for *scale* ascending one octave.

    Unknown scales fall back to natural minor (the safest acid/techno
    default). To extend, edit ``_SCALES`` above — the algorithms read
    from it directly.
    """
    return _SCALES.get(scale.lower(), _SCALES["minor"])


def note_to_midi(tonic: str, octave: int) -> int:
    """``("C", 4) → 60``. ``("A", 2) → 45``. ``("F#", 3) → 54``.

    MIDI convention: C4 = 60 (the "middle C" used by Yamaha + most DAWs).
    Octaves below ``-1`` or above ``9`` are accepted but their resulting
    MIDI note may fall outside 0..127; clamp at use-site if needed.
    """
    if tonic not in _NOTE_SEMITONES:
        raise ValueError(f"unknown note name {tonic!r}")
    return 12 * (octave + 1) + _NOTE_SEMITONES[tonic]
