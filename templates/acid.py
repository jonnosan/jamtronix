"""Acid style template — 303 lead bass, four-on-floor, hat groove.

Knob ranges below are picked fresh on every build so each new
acid song lands in a different musical neighbourhood: tempo, key
root, chord progression family, and the acid_bass / chord_stab
character knobs all jitter within musically sensible bounds.

Bar-by-bar variation (which steps fire, slide on/off, octave jumps)
still flows from the title-derived SHA-256 seed — these jitters
only affect the *macro* shape of the song.
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
        "cycle": random.choice((1, 2, 2, 4, 8)),  # 2-bar LFO most common
        "resonance": random.randint(80, 120),
        "octave": random.choice((-1, 0, 0, 0, 1)),  # 0 most common
    }

    voices = {
        "kick": VoiceConfig(
            # Genre signature — always strict 4-on-the-floor, no ghost
            # notes / polyrhythm / per-step velocity drift. Variation
            # belongs on the hats / snare / clap / percussion voices.
            algorithm="drum_pattern",
            pattern={"style": "four_floor", "velocity": 118},
        ),
        "snare": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={
                # 2-on-4 backbeat most of the time; occasionally
                # delayed-snare (offset 6) or 1-hit (pulses 1, offset 4).
                "pulses": random.choice((1, 2, 2, 2)),
                "offset": random.choice((4, 4, 4, 6)),
                "velocity": random.randint(94, 108),
                "flam_count": random.choice((0, 0, 0, 1)),
                "flam_spacing_ticks": 12,
            },
        ),
        "chh": VoiceConfig(
            algorithm="drum_pattern",
            pattern={
                "style": "euclid",
                "pulses": random.choice((6, 8, 8, 10, 12)),
                "offset": random.choice((0, 0, 0, 1, 2)),
                "velocity": random.randint(80, 100),
                "vel_curve": random.choice(("pulse", "drift", "ramp_up", "arc")),
                "vel_curve_depth": round(random.uniform(0.15, 0.35), 2),
            },
            feel={"swing": round(random.uniform(0.0, 0.22), 2)},
        ),
        "ohh": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={
                "pulses": random.choice((1, 2, 2, 4)),
                "offset": random.choice((2, 2, 6, 10)),
                "velocity": random.randint(80, 92),
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

    parts = {
        "intro": Part(bars=8),
        "build": Part(bars=8),
        "drop": Part(bars=16),
        "drop2": Part(bars=16),
        "outro": Part(bars=8),
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
    )
