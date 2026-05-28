"""Acid style template — 303 lead bass, four-on-floor, hat groove.

Schema v3: drums collapse to one ``kit`` voice with the drum_kit
algorithm. Parts carry an intensity envelope and (in build / outro)
a ``kit_focus`` override that morphs the drum pattern across the
section. Five song-wide feel knobs randomised per build() pick this
particular song's flavour of Pump / Groove / Drive / Tension / Wander.
"""

from __future__ import annotations

import random

from jtx.model import (
    ChordProgression,
    Key,
    Part,
    Song,
    VoiceConfig,
    VoiceOverride,
)

# Progressions that fit acid's minor-scale, four-on-the-floor feel.
_ACID_PROGRESSIONS: tuple[tuple[str, ...], ...] = (
    ("i", "VII", "VI", "V"),  # andalusian descent
    ("i", "VI", "III", "VII"),  # phuture-style
    ("i", "v", "III", "VII"),  # dark circle
    ("i", "VII", "VI", "VII"),  # descent + return
)

_ACID_TONICS: tuple[str, ...] = ("A", "C", "D", "E", "F", "G")


def build(title: str, setup_ref: str) -> Song:
    tonic = random.choice(_ACID_TONICS)
    tempo = random.randint(122, 130)

    base_progression = random.choice(_ACID_PROGRESSIONS)
    rotation = random.randrange(len(base_progression))
    degrees = list(base_progression[rotation:]) + list(base_progression[:rotation])
    bars_per_chord = random.choice((2, 4, 4, 4, 8))  # weighted toward 4

    acid_knobs = {
        "drop_prob": round(random.uniform(0.15, 0.45), 2),
        "slide_prob": round(random.uniform(0.10, 0.55), 2),
        "base_vel": random.randint(88, 104),
        "intensity": round(random.uniform(0.9, 1.3), 2),
        "gate": round(random.uniform(0.45, 0.95), 2),
        "cycle": random.choice((1, 2, 2, 4, 8)),
        "resonance": random.randint(80, 120),
        "octave": random.choice((-1, 0, 0, 0, 1)),
        "triplet_prob": round(random.uniform(0.0, 0.10), 2),
        "triplet_subdiv": "16t",
    }

    voices = {
        "kit": VoiceConfig(
            algorithm="drum_kit",
            pattern={
                "style": "acid",
                "kit_focus": "full",
                "density": round(random.uniform(0.5, 0.75), 2),
                "variation": round(random.uniform(0.2, 0.45), 2),
                "perc_complexity": round(random.uniform(0.25, 0.5), 2),
            },
        ),
        "acid": VoiceConfig(
            algorithm="acid_bass",
            pattern=acid_knobs,
        ),
        "stab": VoiceConfig(
            algorithm="chord_stab",
            pattern={
                "quality": random.choice(("minor", "minor", "min7", "sus4")),
                "pulses": random.choice((2, 4, 4, 8)),
                "offset": random.choice((0, 2, 2, 4)),
                "base_vel": 88,
                "gate": round(random.uniform(0.2, 0.5), 2),
            },
        ),
        "lead": VoiceConfig(
            algorithm="melodic_line",
            pattern={
                "drop_prob": round(random.uniform(0.5, 0.75), 2),
                "octave": 1,
                "base_vel": 90,
                "passing_prob": round(random.uniform(0.05, 0.25), 2),
                "palette": random.choice(("tones_only", "triad", "pentatonic")),
            },
        ),
        "filter": VoiceConfig(
            algorithm="cc_lfo",
            pattern={
                "cc": 74,
                "shape": random.choice(("sine", "sine", "tri", "saw")),
                "period_bars": float(random.choice((4, 8, 8, 16))),
                "depth": round(random.uniform(0.6, 0.95), 2),
                "offset": round(random.uniform(0.4, 0.7), 2),
            },
        ),
    }

    # Per-part intensity envelopes drive the drum_kit voice's density
    # ramps; ``kit_focus`` overrides switch the kit between modes for
    # the build (snare-density ramp) and outro (wind-down).
    parts = {
        "intro": Part(
            bars=8,
            intensity_start=0.2,
            intensity_end=0.35,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "minimal"})},
        ),
        "build": Part(
            bars=8,
            intensity_start=0.35,
            intensity_end=0.95,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "build"})},
        ),
        "drop": Part(
            bars=16,
            intensity_start=0.9,
            intensity_end=0.85,
        ),
        "drop2": Part(
            bars=16,
            intensity_start=0.85,
            intensity_end=0.95,
        ),
        "outro": Part(
            bars=8,
            intensity_start=0.7,
            intensity_end=0.15,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "wind_down"})},
        ),
    }

    feel = {
        "pump": round(random.uniform(0.4, 0.55), 2),
        "groove": round(random.uniform(0.1, 0.25), 2),
        "drive": round(random.uniform(0.4, 0.6), 2),
        "tension": round(random.uniform(0.4, 0.7), 2),
        "wander": round(random.uniform(0.05, 0.15), 2),
    }

    return Song(
        title=title,
        setup_ref=setup_ref,
        key=Key(tonic=tonic, scale="minor"),
        meter="4/4",
        tempo=tempo,
        chord_progression=ChordProgression(
            degrees=degrees,
            bars_per_chord=bars_per_chord,
        ),
        voices=voices,
        parts=parts,
        arrangement=["intro", "build", "drop", "build", "drop2", "outro"],
        feel=feel,
    )
