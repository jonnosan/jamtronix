"""Algorithm metadata for the GUI: voice-type compatibility + knob schemas.

The engine's :class:`jtx.engine.algorithm.Algorithm` classes don't yet
declare a structured pattern-knob schema — they just read from a dict
inside ``generate_bar``. The GUI needs schemas to render knob widgets
with correct ranges and types, so we mirror that information here.

Living in ``jtx_gui`` keeps the engine free of UI concerns, and lets us
extend schemas without touching the algorithm code. When the engine
eventually grows declarative schemas this module is the obvious thing
to delete in favour of reading from the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from jtx.model import VoiceType

KnobKind = Literal["float", "int", "choice", "list_int", "list_str", "string"]


@dataclass(frozen=True)
class KnobSpec:
    """Declarative shape of one pattern (or feel) knob."""

    name: str
    kind: KnobKind
    default: object
    minimum: float = 0.0
    maximum: float = 1.0
    step: float = 0.01
    decimals: int = 2
    choices: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class AlgorithmMeta:
    name: str
    voice_types: tuple[VoiceType, ...]
    pattern: tuple[KnobSpec, ...] = ()


# ---- pattern-knob schemas --------------------------------------------------

_VEL_CURVES = ("flat", "ramp_up", "ramp_down", "arc", "valley", "pulse", "drift")

_DRUM_PATTERN = (
    KnobSpec("style", "choice", default="four_floor", choices=("four_floor", "euclid", "break")),
    KnobSpec("velocity", "int", default=100, minimum=0, maximum=127),
    KnobSpec("pulses", "int", default=4, minimum=0, maximum=16),
    KnobSpec("offset", "int", default=0, minimum=0, maximum=15),
    KnobSpec("ghost", "float", default=0.0, minimum=0.0, maximum=1.0),
    KnobSpec("ghost_velocity_ratio", "float", default=0.35, minimum=0.0, maximum=1.0),
    KnobSpec("polyrhythm", "int", default=0, minimum=0, maximum=16),
    KnobSpec("vel_curve", "choice", default="flat", choices=_VEL_CURVES),
    KnobSpec("vel_curve_depth", "float", default=0.15, minimum=0.0, maximum=1.0),
    KnobSpec("duration_ticks", "int", default=60, minimum=1, maximum=960),
)

_DRUM_ONE_SHOT = (
    KnobSpec("steps", "list_int", default=[0, 4, 8, 12]),
    KnobSpec("velocity", "int", default=110, minimum=0, maximum=127),
    KnobSpec("duration_ticks", "int", default=60, minimum=1, maximum=960),
    KnobSpec("flam_ticks", "list_int", default=[]),
    KnobSpec("flam_decay", "float", default=0.7, minimum=0.0, maximum=1.0),
)

_ACID_BASS = (
    KnobSpec("drop_prob", "float", default=0.35, minimum=0.0, maximum=1.0),
    KnobSpec("slide_prob", "float", default=0.0, minimum=0.0, maximum=1.0),
    KnobSpec("octave", "int", default=0, minimum=-3, maximum=3),
    KnobSpec("base_vel", "int", default=90, minimum=0, maximum=127),
    KnobSpec("intensity", "float", default=1.0, minimum=0.0, maximum=2.0),
    KnobSpec("gate", "float", default=0.75, minimum=0.05, maximum=2.0),
    KnobSpec("bend", "int", default=80, minimum=0, maximum=4096, step=8),
    KnobSpec("cycle", "int", default=2, minimum=0, maximum=16),
    KnobSpec("resonance", "int", default=100, minimum=0, maximum=127),
)

_SUB_DRONE = (
    KnobSpec("gate", "float", default=0.95, minimum=0.05, maximum=2.0),
    KnobSpec("fifth_prob", "float", default=0.0, minimum=0.0, maximum=1.0),
    KnobSpec("bars_per_chord", "int", default=2, minimum=1, maximum=16),
    KnobSpec("kick_env", "float", default=0.0, minimum=0.0, maximum=1.0),
    KnobSpec("base_vel", "int", default=85, minimum=0, maximum=127),
    KnobSpec("octave", "int", default=0, minimum=-3, maximum=3),
)

_MELODIC_LINE = (
    KnobSpec("drop_prob", "float", default=0.5, minimum=0.0, maximum=1.0),
    KnobSpec("octave", "int", default=0, minimum=-3, maximum=3),
    KnobSpec("gate", "float", default=0.5, minimum=0.05, maximum=2.0),
    KnobSpec("base_vel", "int", default=90, minimum=0, maximum=127),
    KnobSpec("intensity", "float", default=1.0, minimum=0.0, maximum=2.0),
    KnobSpec("passing_prob", "float", default=0.0, minimum=0.0, maximum=1.0),
    KnobSpec("degree_palette", "list_int", default=[]),
)

_ARP = (
    KnobSpec("mode", "choice", default="up", choices=("up", "down", "up_down", "random", "walk")),
    KnobSpec("rate_steps", "int", default=1, minimum=1, maximum=16),
    KnobSpec("octaves", "int", default=1, minimum=1, maximum=4),
    KnobSpec("gate", "float", default=0.7, minimum=0.05, maximum=2.0),
    KnobSpec("base_vel", "int", default=95, minimum=0, maximum=127),
    KnobSpec("octave", "int", default=0, minimum=-3, maximum=3),
    KnobSpec("chord_intervals", "list_int", default=[0, 3, 7]),
)

_SUSTAINED_CHORD = (
    KnobSpec("intervals", "list_int", default=[0, 3, 7]),
    KnobSpec("gate", "float", default=0.95, minimum=0.05, maximum=2.0),
    KnobSpec("octave", "int", default=0, minimum=-3, maximum=3),
    KnobSpec("base_vel", "int", default=75, minimum=0, maximum=127),
    KnobSpec("velocity_spread", "int", default=5, minimum=0, maximum=64),
    KnobSpec("drift_prob", "float", default=0.0, minimum=0.0, maximum=1.0),
)

_CHORD_STAB = (
    KnobSpec("intervals", "list_int", default=[0, 3, 7]),
    KnobSpec("steps", "list_int", default=[2, 6, 10, 14]),
    KnobSpec("gate", "float", default=0.4, minimum=0.05, maximum=2.0),
    KnobSpec("octave", "int", default=0, minimum=-3, maximum=3),
    KnobSpec("base_vel", "int", default=90, minimum=0, maximum=127),
    KnobSpec("velocity_spread", "int", default=6, minimum=0, maximum=64),
    KnobSpec("drop_prob", "float", default=0.0, minimum=0.0, maximum=1.0),
)

_CC_LFO = (
    KnobSpec("cc", "int", default=74, minimum=0, maximum=127),
    KnobSpec(
        "shape",
        "choice",
        default="sine",
        choices=("sine", "tri", "saw", "ramp", "square", "random", "sh"),
    ),
    KnobSpec(
        "period_bars", "float", default=4.0, minimum=0.25, maximum=64.0, step=0.25, decimals=2
    ),
    KnobSpec("phase", "float", default=0.0, minimum=0.0, maximum=1.0),
    KnobSpec("depth", "float", default=1.0, minimum=0.0, maximum=1.0),
    KnobSpec("offset", "float", default=0.5, minimum=0.0, maximum=1.0),
    KnobSpec("samples_per_bar", "int", default=16, minimum=1, maximum=128),
)

_CC_ENVELOPE = (
    KnobSpec("cc", "int", default=74, minimum=0, maximum=127),
    KnobSpec("trigger_steps", "list_int", default=[0, 4, 8, 12]),
    KnobSpec("attack_ticks", "int", default=40, minimum=1, maximum=1920),
    KnobSpec("decay_ticks", "int", default=120, minimum=1, maximum=1920),
    KnobSpec("release_ticks", "int", default=240, minimum=1, maximum=1920),
    KnobSpec("peak_value", "int", default=120, minimum=0, maximum=127),
    KnobSpec("sustain_value", "int", default=90, minimum=0, maximum=127),
    KnobSpec("rest_value", "int", default=40, minimum=0, maximum=127),
    KnobSpec("samples", "int", default=8, minimum=2, maximum=128),
)

_ROOT_PULSE = (
    KnobSpec("steps", "list_int", default=[0, 4, 8, 12]),
    KnobSpec("velocity", "int", default=90, minimum=1, maximum=127),
    KnobSpec("octave", "int", default=0, minimum=-3, maximum=3),
    KnobSpec("gate", "float", default=0.5, minimum=0.05, maximum=4.0),
    KnobSpec("duration_ticks", "int", default=0, minimum=0, maximum=8192),
)

_VOICE_FOLLOWER = (
    KnobSpec("source", "string", default=""),
    KnobSpec("shift_bars", "int", default=0, minimum=0, maximum=16),
    KnobSpec(
        "latch",
        "choice",
        default="all",
        choices=("all", "first_per_bar", "every_nth", "accent_only"),
    ),
    KnobSpec("every_nth", "int", default=2, minimum=1, maximum=16),
    KnobSpec("accent_threshold", "int", default=100, minimum=1, maximum=127),
    KnobSpec(
        "transform", "choice", default="none", choices=("none", "invert", "retrograde", "thin")
    ),
    KnobSpec("invert_axis", "int", default=60, minimum=0, maximum=127),
    KnobSpec("thin_prob", "float", default=0.5, minimum=0.0, maximum=1.0),
    KnobSpec("transpose_semitones", "int", default=0, minimum=-24, maximum=24),
    KnobSpec("transpose_octaves", "int", default=0, minimum=-3, maximum=3),
    KnobSpec("chord", "list_int", default=[0]),
    KnobSpec("quantize", "choice", default="off", choices=("off", "nearest", "up", "down")),
    KnobSpec("quantize_scale", "string", default=""),
    KnobSpec("ratchet", "int", default=1, minimum=1, maximum=8),
)


ALGORITHMS: dict[str, AlgorithmMeta] = {
    "drum_pattern": AlgorithmMeta("drum_pattern", ("drum",), _DRUM_PATTERN),
    "drum_one_shot": AlgorithmMeta("drum_one_shot", ("drum",), _DRUM_ONE_SHOT),
    "acid_bass": AlgorithmMeta("acid_bass", ("mono",), _ACID_BASS),
    "sub_drone": AlgorithmMeta("sub_drone", ("mono",), _SUB_DRONE),
    "melodic_line": AlgorithmMeta("melodic_line", ("mono",), _MELODIC_LINE),
    "arp": AlgorithmMeta("arp", ("mono",), _ARP),
    "sustained_chord": AlgorithmMeta("sustained_chord", ("poly",), _SUSTAINED_CHORD),
    "chord_stab": AlgorithmMeta("chord_stab", ("poly",), _CHORD_STAB),
    "cc_lfo": AlgorithmMeta("cc_lfo", ("modulator",), _CC_LFO),
    "cc_envelope": AlgorithmMeta("cc_envelope", ("modulator",), _CC_ENVELOPE),
    "root_pulse": AlgorithmMeta("root_pulse", ("drum", "mono", "poly"), _ROOT_PULSE),
    "voice_follower": AlgorithmMeta("voice_follower", ("follower",), _VOICE_FOLLOWER),
}


def algorithms_for(voice_type: VoiceType) -> list[AlgorithmMeta]:
    """Return all algorithms whose declared voice-type list includes ``voice_type``."""
    return [meta for meta in ALGORITHMS.values() if voice_type in meta.voice_types]


# ---- universal feel-knob schema (mirrors docs/SPEC.md §Feel Knobs) ---------

FEEL_KNOBS: tuple[KnobSpec, ...] = (
    KnobSpec(
        "humanize",
        "int",
        default=0,
        minimum=0,
        maximum=60,
        description="±N ticks of micro-timing jitter",
    ),
    KnobSpec(
        "vel_jitter",
        "int",
        default=0,
        minimum=0,
        maximum=64,
        description="±N velocity jitter per note-on",
    ),
    KnobSpec(
        "gate_jitter",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="±fraction of duration jitter",
    ),
    KnobSpec(
        "swing",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=0.5,
        description="Delay every other 16th by this fraction",
    ),
    KnobSpec(
        "accent",
        "int",
        default=0,
        minimum=0,
        maximum=40,
        description="Velocity boost on accented beats",
    ),
    KnobSpec(
        "mute_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-bar drop chance",
    ),
    KnobSpec(
        "evolution",
        "float",
        default=0.0,
        minimum=-1.0,
        maximum=1.0,
        description="Linear velocity ramp across the part",
    ),
    KnobSpec(
        "octave_jump",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-event ±12 chance",
    ),
    KnobSpec(
        "passing_tones",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Chromatic neighbour swap chance",
    ),
)


@dataclass(frozen=True)
class _LoadedSchemas:
    pattern_by_algo: dict[str, dict[str, KnobSpec]] = field(default_factory=dict)
    feel: dict[str, KnobSpec] = field(default_factory=dict)


def _build() -> _LoadedSchemas:
    return _LoadedSchemas(
        pattern_by_algo={
            name: {k.name: k for k in meta.pattern} for name, meta in ALGORITHMS.items()
        },
        feel={k.name: k for k in FEEL_KNOBS},
    )


SCHEMAS = _build()
