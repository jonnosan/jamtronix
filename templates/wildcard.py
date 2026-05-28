"""Wildcard style — randomise almost everything.

For when you want a fresh, unpredictable starting point that's not
locked into any genre. Picks the key, scale, tempo, progression,
voice algorithms, and every knob from broad ranges. Schema v3: drums
collapse into one ``kit`` voice (with the drum_kit algorithm); a
``kit_focus="full"`` ground state with broad density / variation
ranges.
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

_TONICS: tuple[str, ...] = (
    "A",
    "A#",
    "B",
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
)
_SCALES: tuple[str, ...] = (
    "minor",
    "minor",
    "minor",
    "major",
    "major",
    "minor_pentatonic",
    "major_pentatonic",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
)
_PROGRESSIONS: tuple[tuple[str, ...], ...] = (
    ("i", "VII", "VI", "V"),
    ("i", "VI", "III", "VII"),
    ("i", "v", "III", "VII"),
    ("i", "iv", "V", "i"),
    ("I", "V", "vi", "IV"),
    ("vi", "IV", "I", "V"),
    ("I", "vi", "IV", "V"),
    ("i", "II", "i", "VII"),
    ("I", "I", "IV", "V"),
)

# Algorithm pools per voice slot.
_BASS_ALGOS: tuple[str, ...] = ("acid_bass", "sub_drone", "melodic_line")
_LEAD_ALGOS: tuple[str, ...] = ("arp", "melodic_line", "arp")  # arp weighted
_POLY_ALGOS: tuple[str, ...] = ("chord_stab", "sustained_chord")
_MOD_ALGOS: tuple[str, ...] = ("cc_lfo", "cc_envelope")
_KIT_STYLES: tuple[str, ...] = ("acid", "techno", "psy")

_CHORD_QUALITIES: tuple[str, ...] = (
    "minor",
    "major",
    "sus2",
    "sus4",
    "min7",
    "maj7",
    "dom7",
    "min9",
    "power",
)
_PALETTES: tuple[str, ...] = (
    "tones_only",
    "triad",
    "pentatonic",
    "full",
    "high",
    "low",
)


def build(title: str, setup_ref: str) -> Song:
    voices = {
        "kit": _build_kit(),
        "acid": _build_bass_voice(),
        "stab": _build_poly_voice(),
        "lead": _build_lead_voice(),
        "filter": _build_modulator(),
    }

    parts = {
        "intro": Part(
            bars=random.choice((8, 16)),
            intensity_start=0.2,
            intensity_end=0.45,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "minimal"})},
        ),
        "groove": Part(
            bars=random.choice((16, 32)),
            intensity_start=0.45,
            intensity_end=0.8,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "build"})},
        ),
        "main": Part(
            bars=random.choice((16, 32)),
            intensity_start=0.85,
            intensity_end=0.95,
        ),
        "break": Part(
            bars=random.choice((8, 16)),
            intensity_start=0.5,
            intensity_end=0.3,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "percussion"})},
        ),
        "outro": Part(
            bars=8,
            intensity_start=0.6,
            intensity_end=0.1,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "wind_down"})},
        ),
    }

    base = random.choice(_PROGRESSIONS)
    rotation = random.randrange(len(base))
    degrees = list(base[rotation:]) + list(base[:rotation])
    bars_per_chord = random.choice((2, 4, 4, 4, 8, 8, 16))

    feel = {
        "pump": round(random.uniform(0.1, 0.7), 2),
        "groove": round(random.uniform(0.0, 0.4), 2),
        "drive": round(random.uniform(0.2, 0.8), 2),
        "tension": round(random.uniform(0.3, 0.85), 2),
        "wander": round(random.uniform(0.05, 0.25), 2),
    }

    return Song(
        title=title,
        setup_ref=setup_ref,
        key=Key(tonic=random.choice(_TONICS), scale=random.choice(_SCALES)),
        meter="4/4",
        tempo=random.randint(100, 150),
        chord_progression=ChordProgression(
            degrees=degrees,
            bars_per_chord=bars_per_chord,
        ),
        voices=voices,
        parts=parts,
        arrangement=["intro", "groove", "main", "break", "main", "outro"],
        feel=feel,
    )


# ---- voice builders --------------------------------------------------------


def _build_kit() -> VoiceConfig:
    return VoiceConfig(
        algorithm="drum_kit",
        pattern={
            "style": random.choice(_KIT_STYLES),
            "kit_focus": "full",
            "density": round(random.uniform(0.4, 0.85), 2),
            "variation": round(random.uniform(0.15, 0.5), 2),
            "perc_complexity": round(random.uniform(0.2, 0.65), 2),
        },
    )


def _build_bass_voice() -> VoiceConfig:
    algo = random.choice(_BASS_ALGOS)
    if algo == "acid_bass":
        return VoiceConfig(
            algorithm="acid_bass",
            pattern={
                "drop_prob": round(random.uniform(0.1, 0.5), 2),
                "slide_prob": round(random.uniform(0.0, 0.6), 2),
                "base_vel": random.randint(85, 110),
                "intensity": round(random.uniform(0.8, 1.4), 2),
                "gate": round(random.uniform(0.4, 1.0), 2),
                "cycle": random.choice((0, 1, 2, 4, 8)),
                "resonance": random.randint(60, 125),
                "octave": random.choice((-1, 0, 0, 1)),
            },
        )
    if algo == "sub_drone":
        return VoiceConfig(
            algorithm="sub_drone",
            pattern={
                "gate": round(random.uniform(0.7, 1.0), 2),
                "fifth_prob": round(random.uniform(0.0, 0.35), 2),
                "bars_per_chord": random.choice((2, 4, 8)),
                "kick_env": round(random.uniform(0.0, 0.5), 2),
                "base_vel": random.randint(80, 100),
                "octave": random.choice((-2, -1, -1, 0)),
            },
        )
    # melodic_line as bass
    return VoiceConfig(
        algorithm="melodic_line",
        pattern={
            "drop_prob": round(random.uniform(0.3, 0.7), 2),
            "octave": random.choice((-1, 0)),
            "base_vel": random.randint(82, 100),
            "intensity": round(random.uniform(0.8, 1.2), 2),
            "passing_prob": round(random.uniform(0.0, 0.3), 2),
            "palette": random.choice(_PALETTES),
        },
    )


def _build_poly_voice() -> VoiceConfig:
    algo = random.choice(_POLY_ALGOS)
    quality = random.choice(_CHORD_QUALITIES)
    if algo == "chord_stab":
        return VoiceConfig(
            algorithm="chord_stab",
            pattern={
                "quality": quality,
                "pulses": random.choice((1, 2, 2, 4, 4, 8)),
                "offset": random.choice((0, 2, 4, 6)),
                "base_vel": random.randint(70, 95),
                "gate": round(random.uniform(0.15, 0.6), 2),
                "drop_prob": round(random.uniform(0.0, 0.4), 2),
            },
        )
    return VoiceConfig(
        algorithm="sustained_chord",
        pattern={
            "quality": quality,
            "gate": round(random.uniform(0.6, 1.0), 2),
            "octave": random.choice((-1, 0, 0, 0, 1)),
            "base_vel": random.randint(65, 90),
            "velocity_spread": random.randint(0, 12),
            "drift_prob": round(random.uniform(0.0, 0.25), 2),
        },
    )


def _build_lead_voice() -> VoiceConfig:
    algo = random.choice(_LEAD_ALGOS)
    if algo == "arp":
        return VoiceConfig(
            algorithm="arp",
            pattern={
                "mode": random.choice(("up", "down", "up_down", "random", "walk")),
                "subdivision": random.choice(("16", "8", "8", "4", "8t")),
                "octaves": random.choice((1, 2, 2, 3)),
                "gate": round(random.uniform(0.3, 0.8), 2),
                "base_vel": random.randint(80, 105),
                "octave": random.choice((0, 1, 1)),
                "quality": random.choice(_CHORD_QUALITIES),
            },
        )
    return VoiceConfig(
        algorithm="melodic_line",
        pattern={
            "drop_prob": round(random.uniform(0.4, 0.75), 2),
            "octave": random.choice((0, 1, 1)),
            "base_vel": random.randint(80, 100),
            "passing_prob": round(random.uniform(0.0, 0.35), 2),
            "palette": random.choice(_PALETTES),
            "subdivision": random.choice(("16", "16", "8", "16t")),
            "triplet_prob": round(random.uniform(0.0, 0.25), 2),
            "triplet_subdiv": "16t",
        },
    )


def _build_modulator() -> VoiceConfig:
    algo = random.choice(_MOD_ALGOS)
    if algo == "cc_lfo":
        return VoiceConfig(
            algorithm="cc_lfo",
            pattern={
                "cc": random.choice((71, 74, 74, 74, 11, 1)),
                "shape": random.choice(("sine", "tri", "saw", "square", "random")),
                "period_bars": float(random.choice((1, 2, 4, 4, 8, 16))),
                "phase": round(random.uniform(0.0, 1.0), 2),
                "depth": round(random.uniform(0.5, 1.0), 2),
                "offset": round(random.uniform(0.3, 0.7), 2),
            },
        )
    return VoiceConfig(
        algorithm="cc_envelope",
        pattern={
            "cc": random.choice((71, 74, 74)),
            "pulses": random.choice((1, 2, 4, 4, 8)),
            "offset": random.choice((0, 0, 2, 4)),
            "attack_ticks": random.randint(20, 80),
            "decay_ticks": random.randint(80, 240),
            "release_ticks": random.randint(120, 360),
            "peak_value": random.randint(90, 127),
            "sustain_value": random.randint(60, 100),
            "rest_value": random.randint(20, 60),
        },
    )
