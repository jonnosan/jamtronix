"""Acid style template — 303 lead bass, four-on-floor, hat groove.

Produces a 16-bar arrangement covering kick + snare + hats + acid bass
+ chord stab + cc_lfo filter sweep + a melodic lead. A-minor at 126 BPM.
"""

from __future__ import annotations

from jtx.model import (
    ChordProgression,
    Key,
    Part,
    Song,
    VoiceConfig,
)


def build(title: str, setup_ref: str) -> Song:
    voices = {
        "kick": VoiceConfig(
            algorithm="drum_pattern",
            pattern={"style": "four_floor", "velocity": 118},
        ),
        "snare": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={"pulses": 2, "offset": 4, "velocity": 100, "duration_ticks": 60},
        ),
        "chh": VoiceConfig(
            algorithm="drum_pattern",
            pattern={
                "style": "euclid",
                "pulses": 8,
                "offset": 0,
                "velocity": 92,
                "vel_curve": "pulse",
                "vel_curve_depth": 0.25,
            },
            feel={"swing": 0.18},
        ),
        "ohh": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={"pulses": 2, "offset": 2, "velocity": 88, "duration_ticks": 180},
        ),
        "acid": VoiceConfig(
            algorithm="acid_bass",
            pattern={
                "drop_prob": 0.25,
                "slide_prob": 0.30,
                "base_vel": 96,
                "intensity": 1.1,
                "gate": 0.6,
                "cycle": 2,
                "resonance": 105,
            },
        ),
        "stab": VoiceConfig(
            algorithm="chord_stab",
            pattern={
                "quality": "minor",
                "pulses": 4,
                "offset": 2,
                "base_vel": 88,
                "gate": 0.3,
            },
        ),
        "lead": VoiceConfig(
            algorithm="melodic_line",
            pattern={
                "drop_prob": 0.55,
                "octave": 1,
                "base_vel": 90,
                "passing_prob": 0.15,
                "palette": "tones_only",
            },
        ),
        "filter": VoiceConfig(
            algorithm="cc_lfo",
            pattern={
                "cc": 74,
                "shape": "sine",
                "period_bars": 8,
                "depth": 0.85,
                "offset": 0.55,
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
        key=Key(tonic="A", scale="minor"),
        meter="4/4",
        tempo=126,
        chord_progression=ChordProgression(
            degrees=["i", "VI", "III", "VII"],
            bars_per_chord=4,
        ),
        voices=voices,
        parts=parts,
        arrangement=["intro", "build", "drop", "build", "drop2", "outro"],
    )
