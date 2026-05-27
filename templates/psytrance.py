"""Psytrance style — rolling offbeat bass, fast arp leads. F# minor at 145."""

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
            pattern={"style": "four_floor", "velocity": 122},
        ),
        "snare": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={"steps": [4, 12], "velocity": 96, "duration_ticks": 40},
        ),
        "chh": VoiceConfig(
            algorithm="drum_pattern",
            pattern={
                "style": "euclid",
                "pulses": 12,
                "offset": 0,
                "velocity": 88,
            },
        ),
        "ohh": VoiceConfig(
            algorithm="drum_one_shot",
            pattern={"steps": [2, 6, 10, 14], "velocity": 80, "duration_ticks": 80},
        ),
        "acid": VoiceConfig(
            algorithm="acid_bass",
            pattern={
                "drop_prob": 0.05,
                "slide_prob": 0.10,
                "base_vel": 104,
                "intensity": 1.3,
                "gate": 0.45,
                "octave": -1,
                "cycle": 0,
            },
        ),
        "stab": VoiceConfig(
            algorithm="chord_stab",
            pattern={
                "intervals": [0, 7],
                "steps": [2, 6, 10, 14],
                "base_vel": 84,
                "gate": 0.2,
            },
        ),
        "lead": VoiceConfig(
            algorithm="arp",
            pattern={
                "mode": "up_down",
                "rate_steps": 2,
                "octaves": 2,
                "gate": 0.4,
                "base_vel": 96,
                "octave": 1,
                "chord_intervals": [0, 5, 7, 10],
            },
        ),
        "filter": VoiceConfig(
            algorithm="cc_lfo",
            pattern={
                "cc": 74,
                "shape": "sine",
                "period_bars": 4,
                "depth": 0.9,
                "offset": 0.6,
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
        key=Key(tonic="F#", scale="minor"),
        meter="4/4",
        tempo=145,
        chord_progression=ChordProgression(
            degrees=["i", "v", "VI", "iv"],
            bars_per_chord=4,
        ),
        voices=voices,
        parts=parts,
        arrangement=["intro", "rolling", "lead", "breakdown", "lead", "outro"],
    )
