"""Deep techno style — sub_drone, dub stab, sparse top-end. C-minor at 122."""

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
            pattern={"style": "four_floor", "velocity": 116},
        ),
        "snare": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={"pulses": 2, "offset": 4, "velocity": 92},
            feel={"humanize": 6},
        ),
        "chh": VoiceConfig(
            algorithm="drum_pattern",
            pattern={
                "style": "euclid",
                "pulses": 6,
                "offset": 1,
                "velocity": 76,
            },
            feel={"swing": 0.12},
        ),
        "ohh": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={"pulses": 1, "offset": 6, "velocity": 84},
        ),
        "acid": VoiceConfig(
            algorithm="sub_drone",
            pattern={
                "gate": 1.0,
                "fifth_prob": 0.15,
                "bars_per_chord": 4,
                "kick_env": 0.25,
                "base_vel": 92,
                "octave": -1,
            },
        ),
        "stab": VoiceConfig(
            algorithm="chord_stab",
            pattern={
                "quality": "min7",
                "pulses": 2,
                "offset": 6,
                "base_vel": 78,
                "gate": 0.35,
                "drop_prob": 0.4,
            },
            feel={"swing": 0.08, "humanize": 8},
        ),
        "lead": VoiceConfig(
            algorithm="melodic_line",
            pattern={
                "drop_prob": 0.78,
                "octave": 0,
                "base_vel": 80,
                "passing_prob": 0.25,
                "palette": "pentatonic",
            },
        ),
        "filter": VoiceConfig(
            algorithm="cc_lfo",
            pattern={
                "cc": 74,
                "shape": "sine",
                "period_bars": 16,
                "depth": 0.7,
                "offset": 0.45,
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
        key=Key(tonic="C", scale="minor"),
        meter="4/4",
        tempo=122,
        chord_progression=ChordProgression(
            degrees=["i", "VI", "iv", "v"],
            bars_per_chord=8,
        ),
        voices=voices,
        parts=parts,
        arrangement=["intro", "groove", "main", "breakdown", "main", "outro"],
    )
