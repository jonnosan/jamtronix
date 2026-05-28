"""Deep techno style — sub drone, dub stab, sparse top-end.

Schema v3: one ``kit`` voice with the drum_kit algorithm replaces the
separate kick / snare / chh / ohh setup. Parts carry intensity
envelopes; the build / outro override ``kit_focus`` for the canonical
snare-density ramp and wind-down. Song-wide Pump runs hot — deep
techno's signature pulsing sidechain on the sub.
"""

from __future__ import annotations

import random

from jtx.model import (
    LFO,
    ChordProgression,
    Key,
    LFOApplication,
    Part,
    Song,
    VoiceConfig,
    VoiceOverride,
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
        "kit": VoiceConfig(
            algorithm="drum_kit",
            pattern={
                "style": "techno",
                "kit_focus": "full",
                "density": round(random.uniform(0.45, 0.7), 2),
                "variation": round(random.uniform(0.15, 0.35), 2),
                "perc_complexity": round(random.uniform(0.3, 0.55), 2),
            },
        ),
        "sub": VoiceConfig(
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
        ),
        "pad": VoiceConfig(
            algorithm="sustained_chord",
            pattern={
                "quality": random.choice(("min7", "min9", "minor", "sus4")),
                "base_vel": random.randint(54, 70),
                "gate": round(random.uniform(0.85, 1.0), 2),
            },
        ),
    }

    # Filter sweep — song-level LFO targeting the phantom "filter"
    # modulator voice's "cutoff" function. The setup's filter slot
    # routes "cutoff" to a concrete MIDI/OSC destination.
    filter_lfo = LFO(
        name="filter_sweep",
        shape=random.choice(("sine", "sine", "tri")),
        period_bars=float(random.choice((8, 16, 16, 32))),
        depth=round(random.uniform(0.5, 0.8), 2),
        samples_per_bar=16,
        applications=[
            LFOApplication(part=part, target="voice:filter:cutoff")
            for part in ("intro", "groove", "main", "breakdown", "outro")
        ],
    )

    parts = {
        "intro": Part(
            bars=16,
            intensity_start=0.15,
            intensity_end=0.4,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "minimal"})},
        ),
        "groove": Part(
            bars=16,
            intensity_start=0.4,
            intensity_end=0.7,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "build"})},
        ),
        "main": Part(
            bars=32,
            intensity_start=0.85,
            intensity_end=0.95,
        ),
        "breakdown": Part(
            bars=16,
            intensity_start=0.5,
            intensity_end=0.3,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "no_kick"})},
        ),
        "outro": Part(
            bars=16,
            intensity_start=0.7,
            intensity_end=0.1,
            voice_overrides={"kit": VoiceOverride(pattern={"kit_focus": "wind_down"})},
        ),
    }

    feel = {
        "pump": round(random.uniform(0.5, 0.75), 2),
        "groove": round(random.uniform(0.2, 0.35), 2),
        "drive": round(random.uniform(0.2, 0.4), 2),
        "tension": round(random.uniform(0.5, 0.8), 2),
        "wander": round(random.uniform(0.1, 0.25), 2),
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
        feel=feel,
        lfos=[filter_lfo],
    )
