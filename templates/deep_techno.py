"""Deep techno style — sub drone, dub stab, sparse top-end.

Knob ranges jitter at build time so each new deep_techno song lands
on a different tonic, tempo, kick-locked filter envelope strength,
chord voicing, and stab density. Bar-by-bar pitch / step choices
still derive from the title-seeded RNG.
"""

from __future__ import annotations

import random

from jtx.model import (
    ChordProgression,
    Key,
    Part,
    Song,
    VoiceConfig,
)

_DEEP_PROGRESSIONS: tuple[tuple[str, ...], ...] = (
    ("i", "VI", "iv", "v"),  # natural cadence
    ("i", "iv", "V", "i"),  # tonic-subdominant
    ("i", "v", "III", "VII"),  # dark circle
    ("i", "VI", "III", "VII"),  # phuture-style
)
_DEEP_TONICS: tuple[str, ...] = ("C", "D", "F", "G", "A", "B")


def build(title: str, setup_ref: str) -> Song:
    tonic = random.choice(_DEEP_TONICS)
    tempo = random.randint(118, 124)

    base = random.choice(_DEEP_PROGRESSIONS)
    rotation = random.randrange(len(base))
    degrees = list(base[rotation:]) + list(base[:rotation])
    bars_per_chord = random.choice((4, 8, 8, 8, 16))

    voices = {
        "kick": VoiceConfig(
            # Strict 4-on-floor; variation belongs on hats / snare / ohh.
            algorithm="drum_pattern",
            pattern={"style": "four_floor", "velocity": 116},
        ),
        "snare": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={
                "pulses": random.choice((1, 2, 2)),
                "offset": random.choice((4, 4, 6, 8)),
                "velocity": random.randint(86, 98),
            },
            feel={"humanize": random.randint(4, 10)},
        ),
        "chh": VoiceConfig(
            algorithm="drum_pattern",
            pattern={
                "style": "euclid",
                "pulses": random.choice((4, 6, 6, 8)),
                "offset": random.choice((0, 1, 2)),
                "velocity": random.randint(68, 84),
                "vel_curve": random.choice(("flat", "drift", "valley")),
                "vel_curve_depth": round(random.uniform(0.08, 0.22), 2),
            },
            feel={"swing": round(random.uniform(0.08, 0.16), 2)},
        ),
        "ohh": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={
                "pulses": random.choice((1, 1, 2)),
                "offset": random.choice((4, 6, 8, 10)),
                "velocity": random.randint(78, 90),
            },
        ),
        "acid": VoiceConfig(
            algorithm="sub_drone",
            pattern={
                "gate": round(random.uniform(0.85, 1.0), 2),
                "fifth_prob": round(random.uniform(0.05, 0.25), 2),
                "bars_per_chord": random.choice((2, 4, 4, 8)),
                "kick_env": round(random.uniform(0.1, 0.4), 2),
                "base_vel": random.randint(88, 96),
                "octave": random.choice((-2, -1, -1, 0)),
            },
        ),
        "stab": VoiceConfig(
            algorithm="chord_stab",
            pattern={
                "quality": random.choice(("min7", "min7", "min9", "sus4", "minor")),
                "pulses": random.choice((1, 2, 2, 4)),
                "offset": random.choice((2, 4, 6, 10, 14)),
                "base_vel": 78,
                "gate": round(random.uniform(0.25, 0.5), 2),
                "drop_prob": round(random.uniform(0.25, 0.55), 2),
            },
            feel={"swing": round(random.uniform(0.04, 0.12), 2), "humanize": 8},
        ),
        "lead": VoiceConfig(
            algorithm="melodic_line",
            pattern={
                "drop_prob": round(random.uniform(0.7, 0.85), 2),
                "octave": 0,
                "base_vel": 80,
                "passing_prob": round(random.uniform(0.15, 0.3), 2),
                "palette": random.choice(("pentatonic", "triad", "tones_only")),
            },
        ),
        "filter": VoiceConfig(
            algorithm="cc_lfo",
            pattern={
                "cc": 74,
                "shape": random.choice(("sine", "sine", "tri")),
                "period_bars": float(random.choice((8, 16, 16, 32))),
                "depth": round(random.uniform(0.5, 0.8), 2),
                "offset": round(random.uniform(0.4, 0.55), 2),
            },
        ),
    }

    parts = {
        "intro": Part(bars=16),
        "groove": Part(bars=16),
        "main": Part(bars=32),
        "breakdown": Part(bars=16),
        "outro": Part(bars=16),
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
        arrangement=["intro", "groove", "main", "breakdown", "main", "outro"],
    )
