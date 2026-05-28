"""Psytrance style — rolling offbeat bass, fast arp leads.

Schema v3: one ``kit`` voice with the drum_kit algorithm; the drop
gets a brief ``kick_only`` "moment of silence" override (psy's
signature mid-bar drop). Drive runs hot, Pump stays relatively low —
the psy mix is broadband, not pumping.
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

_PSY_PROGRESSIONS: tuple[tuple[str, ...], ...] = (
    ("i", "v", "VI", "iv"),  # default psy
    ("i", "VII", "VI", "V"),  # andalusian
    ("i", "II", "i", "VII"),  # phrygian pull
    ("i", "v", "III", "VII"),  # dark circle
)
_PSY_TONICS: tuple[str, ...] = ("E", "F", "F#", "G", "A")


def build(title: str, setup_ref: str) -> Song:
    tonic = random.choice(_PSY_TONICS)
    tempo = random.randint(140, 148)

    base = random.choice(_PSY_PROGRESSIONS)
    rotation = random.randrange(len(base))
    degrees = list(base[rotation:]) + list(base[:rotation])
    bars_per_chord = random.choice((2, 4, 4, 4))

    voices = {
        "kit": VoiceConfig(
            algorithm="drum_kit",
            pattern={
                "style": "psy",
                "kit_focus": "full",
                "density": round(random.uniform(0.6, 0.85), 2),
                "variation": round(random.uniform(0.2, 0.4), 2),
                "perc_complexity": round(random.uniform(0.4, 0.65), 2),
            },
        ),
        "bass": VoiceConfig(
            algorithm="acid_bass",
            pattern={
                "drop_prob": round(random.uniform(0.0, 0.15), 2),
                "slide_prob": round(random.uniform(0.05, 0.25), 2),
                "base_vel": random.randint(100, 108),
                "intensity": round(random.uniform(1.2, 1.4), 2),
                "gate": round(random.uniform(0.35, 0.55), 2),
                "octave": random.choice((-1, -1, 0)),
                "cycle": random.choice((0, 0, 1, 2)),
            },
        ),
        "pluck": VoiceConfig(
            algorithm="chord_stab",
            pattern={
                "quality": random.choice(("power", "power", "minor", "sus4")),
                "pulses": random.choice((2, 4, 4, 8)),
                "offset": random.choice((0, 2, 2, 4)),
                "base_vel": 84,
                "gate": round(random.uniform(0.15, 0.3), 2),
            },
        ),
        "lead": VoiceConfig(
            algorithm="arp",
            pattern={
                "mode": random.choice(("up", "up_down", "up_down", "walk")),
                "subdivision": random.choice(("16", "8", "8", "4")),
                "octaves": random.choice((1, 2, 2, 3)),
                "gate": round(random.uniform(0.35, 0.55), 2),
                "base_vel": 96,
                "octave": 1,
                "quality": random.choice(("min7", "minor", "min9", "power")),
            },
        ),
        "filter": VoiceConfig(
            algorithm="cc_lfo",
            pattern={
                "cc": 74,
                "shape": random.choice(("sine", "tri", "saw")),
                "period_bars": float(random.choice((1, 2, 2, 4))),
                "depth": round(random.uniform(0.7, 0.95), 2),
                "offset": round(random.uniform(0.5, 0.7), 2),
            },
        ),
    }

    parts = {
        "intro": Part(
            bars=16,
            intensity_start=0.2,
            intensity_end=0.4,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "minimal"})},
        ),
        "rolling": Part(
            bars=32,
            intensity_start=0.6,
            intensity_end=0.9,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "build"})},
        ),
        "lead": Part(
            bars=32,
            intensity_start=0.9,
            intensity_end=0.95,
            # The classic psy "moment of silence" — drop everything to
            # just the kick for the drop part.
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "kick_only"})},
        ),
        "breakdown": Part(
            bars=16,
            intensity_start=0.5,
            intensity_end=0.3,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "percussion"})},
        ),
        "outro": Part(
            bars=16,
            intensity_start=0.7,
            intensity_end=0.15,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "wind_down"})},
        ),
    }

    feel = {
        "pump": round(random.uniform(0.15, 0.3), 2),
        "groove": round(random.uniform(0.0, 0.1), 2),
        "drive": round(random.uniform(0.6, 0.85), 2),
        "tension": round(random.uniform(0.6, 0.85), 2),
        "wander": round(random.uniform(0.1, 0.2), 2),
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
        arrangement=["intro", "rolling", "lead", "breakdown", "lead", "outro"],
        feel=feel,
    )
