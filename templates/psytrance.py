"""Psytrance style — rolling offbeat bass, fast arp leads.

Knob jitter at build time keeps each new psytrance song fresh: tonic,
tempo, bass character, arp shape, filter sweep rate. Per-bar pitch
choices still flow from the title-seeded RNG.
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
        "kick": VoiceConfig(
            # Strict 4-on-floor; variation belongs on hats / snare / ohh.
            algorithm="drum_pattern",
            pattern={"style": "four_floor", "velocity": 122},
        ),
        "snare": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={
                "pulses": random.choice((1, 2, 2)),
                "offset": random.choice((4, 4, 6)),
                "velocity": random.randint(92, 102),
            },
        ),
        "chh": VoiceConfig(
            algorithm="drum_pattern",
            pattern={
                "style": "euclid",
                "pulses": random.choice((10, 12, 12, 14)),
                "offset": random.choice((0, 0, 1)),
                "velocity": random.randint(80, 96),
                "vel_curve": random.choice(("pulse", "ramp_up", "drift")),
                "vel_curve_depth": round(random.uniform(0.10, 0.30), 2),
                # Psy hat roll into the drop — sparse so it stays a fill.
                "roll_pos": random.choice(("none", "none", "last_bar_of_8")),
                "roll_subdiv": "16t",
                "roll_depth": round(random.uniform(0.55, 0.8), 2),
            },
        ),
        "ohh": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={
                "pulses": random.choice((2, 4, 4, 8)),
                "offset": random.choice((2, 2, 6)),
                "velocity": random.randint(72, 88),
            },
        ),
        "acid": VoiceConfig(
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
        "stab": VoiceConfig(
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
        "intro": Part(bars=16),
        "rolling": Part(bars=32),
        "lead": Part(bars=32),
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
        arrangement=["intro", "rolling", "lead", "breakdown", "lead", "outro"],
    )
