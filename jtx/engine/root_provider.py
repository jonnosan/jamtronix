"""RootProvider interface + default progression-based implementation.

Architecture hook for future MIDI-in chord steering (see
``docs/SPEC.md`` §External-Input Hooks). Per-bar chord-root resolution
sits behind an ABC so:

* the default ``ProgressionRootProvider`` reads the song's static
  Roman-numeral chord progression (this file);
* a future ``ExternalMidiRootProvider`` will read the last note
  received on a configured MIDI-in channel — no concrete impl in v1.

Switching providers is a single line in the engine bootstrap. The
glue layer queries ``provider.root_semitones_for_bar(bar_index)`` once
per bar and stamps the result into each voice's ``BarContext`` as
``chord_root_semitones``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from jtx.algorithms._theory import scale_intervals
from jtx.model.song import ChordProgression, Key


class RootProvider(ABC):
    """Per-bar chord-root source.

    Returns the semitone offset above the song tonic for the chord
    active in *bar_index*. Implementations are pure functions of
    ``bar_index`` so per-bar regeneration stays deterministic.
    """

    @abstractmethod
    def root_semitones_for_bar(self, bar_index: int) -> int:
        """Semitones above the song tonic for the chord at this bar."""


class ProgressionRootProvider(RootProvider):
    """Default provider: resolves the song's Roman-numeral progression.

    Indexes into ``progression.degrees`` using ``bar_index //
    bars_per_chord`` (mod the degree count). Each degree resolves to a
    scale-step semitone offset via ``key.scale``.
    """

    def __init__(self, key: Key, progression: ChordProgression | None) -> None:
        self.key = key
        self.progression = progression
        self._scale_steps = scale_intervals(key.scale)

    def root_semitones_for_bar(self, bar_index: int) -> int:
        if self.progression is None or not self.progression.degrees:
            return 0
        bars_per_chord = max(1, self.progression.bars_per_chord)
        idx = (bar_index // bars_per_chord) % len(self.progression.degrees)
        degree_str = self.progression.degrees[idx]
        return degree_to_semitones(degree_str, self._scale_steps)


# ---------------------------------------------------------------- parsing

_DEGREE_NUMERALS: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
}

# Markers we strip before degree lookup. Chord *quality* (major/minor/
# diminished/augmented) doesn't change the root, so we ignore those
# decorations for root semantics — but we keep parsing them out so
# future-us can lift them into a returned ``ChordQuality`` if needed.
_STRIP_MARKERS = ("maj7", "maj", "m7", "7", "9", "11", "13", "sus4", "sus2", "°", "+", "*")

# Accidental markers on the degree itself: ``bIII`` = lowered III (one
# semitone below the diatonic III).
_FLAT = ("b", "♭")
_SHARP = ("#", "♯")


def degree_to_semitones(degree_str: str, scale_steps: tuple[int, ...]) -> int:
    """Resolve a Roman-numeral degree to semitones above the tonic.

    Supports the seven diatonic numerals (I..VII / i..vii), case-
    insensitive for root semantics. Leading ``b`` / ``♭`` lowers the
    degree by 1 semitone; ``#`` / ``♯`` raises it by 1. Trailing chord
    quality markers (``°``, ``7``, ``maj7``, ``sus4``, etc.) are
    stripped — they affect the chord *quality*, not the root.

    Unknown degrees raise ``ValueError``.
    """
    s = degree_str.strip()
    if not s:
        raise ValueError("empty degree")

    flat = 0
    while s and s[0] in _FLAT + _SHARP:
        if s[0] in _FLAT:
            flat -= 1
        else:
            flat += 1
        s = s[1:]

    upper = s.upper()
    for marker in _STRIP_MARKERS:
        upper = upper.replace(marker.upper(), "")

    if upper not in _DEGREE_NUMERALS:
        raise ValueError(f"unknown chord degree {degree_str!r}")

    degree = _DEGREE_NUMERALS[upper]  # 1..7
    # Diatonic semitone of the degree = scale_steps[degree - 1].
    diatonic = scale_steps[(degree - 1) % len(scale_steps)]
    return diatonic + flat
