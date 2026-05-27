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

from jtx.algorithms._chords import QUALITY_CHOICES
from jtx.algorithms._palettes import PALETTE_CHOICES
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

# Subdivision strings supported by jtx.algorithms._subdivision (kept in
# sync manually; the GUI doesn't import engine internals).
SUBDIVISION_CHOICES: tuple[str, ...] = (
    "2",
    "4",
    "8",
    "16",
    "32",
    "2t",
    "4t",
    "8t",
    "16t",
    "32t",
)
TRIPLET_SUBDIV_CHOICES: tuple[str, ...] = ("4t", "8t", "16t", "32t")
ROLL_POS_CHOICES: tuple[str, ...] = (
    "none",
    "last_beat",
    "last_bar_of_4",
    "last_bar_of_8",
    "random_sparse",
)
RATCHET_CURVE_CHOICES: tuple[str, ...] = ("flat", "ramp_up", "last_beat", "pulse")

_DRUM_PATTERN = (
    KnobSpec(
        "style",
        "choice",
        default="four_floor",
        choices=("four_floor", "euclid", "break"),
        description="Drum-pattern shape: four-on-floor, euclidean rotation, or breakbeat.",
    ),
    KnobSpec(
        "velocity",
        "int",
        default=100,
        minimum=0,
        maximum=127,
        description="Base MIDI velocity for each hit.",
    ),
    KnobSpec(
        "pulses",
        "int",
        default=4,
        minimum=0,
        maximum=16,
        description="Number of hits per bar (used by euclid/break styles).",
    ),
    KnobSpec(
        "offset",
        "int",
        default=0,
        minimum=0,
        maximum=15,
        description="Rotate the euclid pattern N 16ths within the bar.",
    ),
    KnobSpec(
        "ghost",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Probability of a quiet ghost note between main hits.",
    ),
    KnobSpec(
        "ghost_velocity_ratio",
        "float",
        default=0.35,
        minimum=0.0,
        maximum=1.0,
        description="Ghost-note velocity as a fraction of main velocity.",
    ),
    KnobSpec(
        "polyrhythm",
        "int",
        default=0,
        minimum=0,
        maximum=16,
        description="Polyrhythm pulse count: a second pulse layer at N steps/bar (0 = off).",
    ),
    KnobSpec(
        "polyrhythm_subdiv",
        "choice",
        default="16",
        choices=SUBDIVISION_CHOICES,
        description="Subdivision grid for the polyrhythm layer (8t/16t = triplet hat).",
    ),
    KnobSpec(
        "roll_pos",
        "choice",
        default="none",
        choices=ROLL_POS_CHOICES,
        description="When to fire a triplet roll fill (last beat / last bar of N / random).",
    ),
    KnobSpec(
        "roll_subdiv",
        "choice",
        default="16t",
        choices=TRIPLET_SUBDIV_CHOICES,
        description="Triplet subdivision used inside the roll fill.",
    ),
    KnobSpec(
        "roll_depth",
        "float",
        default=0.6,
        minimum=0.0,
        maximum=1.0,
        description="Fraction of roll-grid positions that fire (1.0 = continuous fill).",
    ),
    KnobSpec(
        "vel_curve",
        "choice",
        default="flat",
        choices=_VEL_CURVES,
        description="Velocity-modulation shape across the bar (flat / ramps / arc / drift / …).",
    ),
    KnobSpec(
        "vel_curve_depth",
        "float",
        default=0.15,
        minimum=0.0,
        maximum=1.0,
        description="How strongly vel_curve modulates the base velocity.",
    ),
)

_DRUM_ONE_SHOT = (
    KnobSpec(
        "pulses",
        "int",
        default=1,
        minimum=0,
        maximum=16,
        description="How many hits per bar (euclid-distributed across 16 steps).",
    ),
    KnobSpec(
        "offset",
        "int",
        default=0,
        minimum=0,
        maximum=15,
        description="Rotate the pattern N 16ths within the bar.",
    ),
    KnobSpec(
        "velocity",
        "int",
        default=110,
        minimum=0,
        maximum=127,
        description="MIDI velocity for each hit.",
    ),
    KnobSpec(
        "flam_count",
        "int",
        default=0,
        minimum=0,
        maximum=3,
        description="Extra flam-cluster hits after each main hit (0 = no flam).",
    ),
    KnobSpec(
        "flam_spacing_ticks",
        "int",
        default=12,
        minimum=1,
        maximum=60,
        description="Ticks between successive flam hits (PPQ 480).",
    ),
    KnobSpec(
        "flam_decay",
        "float",
        default=0.7,
        minimum=0.0,
        maximum=1.0,
        description="Velocity reduction for each flam hit (0=silent, 1=same as main).",
    ),
    KnobSpec(
        "roll_pos",
        "choice",
        default="none",
        choices=ROLL_POS_CHOICES,
        description="When to fire a triplet roll fill (best for tom rolls into drops).",
    ),
    KnobSpec(
        "roll_subdiv",
        "choice",
        default="16t",
        choices=TRIPLET_SUBDIV_CHOICES,
        description="Triplet subdivision used inside the roll fill.",
    ),
    KnobSpec(
        "roll_depth",
        "float",
        default=0.6,
        minimum=0.0,
        maximum=1.0,
        description="Fraction of roll-grid positions that fire (1.0 = continuous fill).",
    ),
)

_ACID_BASS = (
    KnobSpec(
        "drop_prob",
        "float",
        default=0.35,
        minimum=0.0,
        maximum=1.0,
        description="Per-step chance the step is a rest. Higher = sparser line.",
    ),
    KnobSpec(
        "slide_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Chance each note slides into the next via CC65/CC5 portamento.",
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Transpose the whole line by N octaves.",
    ),
    KnobSpec(
        "base_vel",
        "int",
        default=90,
        minimum=0,
        maximum=127,
        description="Baseline MIDI velocity (per-step accent adds +15).",
    ),
    KnobSpec(
        "intensity",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=2.0,
        description="Multiplier on base velocity + filter range. >1 = squelchier.",
    ),
    KnobSpec(
        "gate",
        "float",
        default=0.75,
        minimum=0.05,
        maximum=2.0,
        description="Note length as a fraction of a step (>1 = legato overlap).",
    ),
    KnobSpec(
        "bend",
        "int",
        default=80,
        minimum=0,
        maximum=4096,
        step=8,
        description="Pitch-bend wobble depth in cents around each note.",
    ),
    KnobSpec(
        "cycle",
        "int",
        default=2,
        minimum=0,
        maximum=16,
        description="Internal CC74/CC71 LFO period in bars (0 = silence the built-in LFO).",
    ),
    KnobSpec(
        "resonance",
        "int",
        default=100,
        minimum=0,
        maximum=127,
        description="Resonance ceiling sent on CC71 (or your remapped CC).",
    ),
    KnobSpec(
        "triplet_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-beat chance the four 16ths become a 3-position triplet roll.",
    ),
    KnobSpec(
        "triplet_subdiv",
        "choice",
        default="16t",
        choices=TRIPLET_SUBDIV_CHOICES,
        description="Subdivision used when triplet_prob fires.",
    ),
)

_SUB_DRONE = (
    KnobSpec(
        "gate",
        "float",
        default=0.95,
        minimum=0.05,
        maximum=2.0,
        description="Note length as a fraction of a bar (>1 = sustains past bar end).",
    ),
    KnobSpec(
        "fifth_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-bar chance of jumping to the fifth instead of root.",
    ),
    KnobSpec(
        "bars_per_chord",
        "int",
        default=2,
        minimum=1,
        maximum=16,
        description="Bars between root/fifth alternations.",
    ),
    KnobSpec(
        "kick_env",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Strength of kick-locked filter envelope on CC74 (0 = off).",
    ),
    KnobSpec(
        "base_vel",
        "int",
        default=85,
        minimum=0,
        maximum=127,
        description="Baseline MIDI velocity for the drone note.",
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Transpose the drone by N octaves (default is register 1, ≈A1).",
    ),
)

_MELODIC_LINE = (
    KnobSpec(
        "drop_prob",
        "float",
        default=0.5,
        minimum=0.0,
        maximum=1.0,
        description="Per-step chance the step rests. Higher = sparser riff.",
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Transpose the whole line by N octaves.",
    ),
    KnobSpec(
        "gate",
        "float",
        default=0.5,
        minimum=0.05,
        maximum=2.0,
        description="Note length as a fraction of a step.",
    ),
    KnobSpec(
        "base_vel",
        "int",
        default=90,
        minimum=0,
        maximum=127,
        description="Baseline MIDI velocity.",
    ),
    KnobSpec(
        "intensity",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=2.0,
        description="Velocity multiplier — >1 punches harder, <1 softer.",
    ),
    KnobSpec(
        "passing_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Chance of inserting a chromatic passing tone between picks.",
    ),
    KnobSpec(
        "palette",
        "choice",
        default="tones_only",
        choices=PALETTE_CHOICES,
        description="Which scale degrees the line draws from (triad / pentatonic / full / …).",
    ),
    KnobSpec(
        "subdivision",
        "choice",
        default="16",
        choices=SUBDIVISION_CHOICES,
        description="Grid the line walks on (16t/8t = full triplet phrase).",
    ),
    KnobSpec(
        "triplet_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-beat chance the beat becomes a 3-position triplet micro-roll.",
    ),
    KnobSpec(
        "triplet_subdiv",
        "choice",
        default="16t",
        choices=TRIPLET_SUBDIV_CHOICES,
        description="Triplet subdivision used inside the inserted rolls.",
    ),
)

_ARP = (
    KnobSpec(
        "mode",
        "choice",
        default="up",
        choices=("up", "down", "up_down", "random", "walk"),
        description="Arpeggio direction across the chord intervals.",
    ),
    KnobSpec(
        "subdivision",
        "choice",
        default="16",
        choices=SUBDIVISION_CHOICES,
        description="Grid the arp runs on (16 = 16ths, 8 = 8ths, 8t = 8th triplets, …).",
    ),
    KnobSpec(
        "octaves",
        "int",
        default=1,
        minimum=1,
        maximum=4,
        description="How many octaves the arp spans before wrapping.",
    ),
    KnobSpec(
        "gate",
        "float",
        default=0.7,
        minimum=0.05,
        maximum=2.0,
        description="Note length as a fraction of a step.",
    ),
    KnobSpec(
        "base_vel",
        "int",
        default=95,
        minimum=0,
        maximum=127,
        description="Baseline MIDI velocity.",
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Transpose by N octaves.",
    ),
    KnobSpec(
        "quality",
        "choice",
        default="minor",
        choices=QUALITY_CHOICES,
        description="Chord shape to arpeggiate (minor / major / sus4 / maj7 / …).",
    ),
)

_SUSTAINED_CHORD = (
    KnobSpec(
        "quality",
        "choice",
        default="minor",
        choices=QUALITY_CHOICES,
        description="Chord voicing (minor / major / sus2 / maj7 / power / …).",
    ),
    KnobSpec(
        "gate",
        "float",
        default=0.95,
        minimum=0.05,
        maximum=2.0,
        description="Chord-hold length as a fraction of a bar.",
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Transpose the chord by N octaves.",
    ),
    KnobSpec(
        "base_vel",
        "int",
        default=75,
        minimum=0,
        maximum=127,
        description="Baseline MIDI velocity for each chord note.",
    ),
    KnobSpec(
        "velocity_spread",
        "int",
        default=5,
        minimum=0,
        maximum=64,
        description="±N velocity variation between chord notes (humanises the voicing).",
    ),
    KnobSpec(
        "drift_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-bar chance a chord note drifts up/down a semitone.",
    ),
)

_CHORD_STAB = (
    KnobSpec(
        "quality",
        "choice",
        default="minor",
        choices=QUALITY_CHOICES,
        description="Chord voicing (minor / major / sus4 / maj7 / …).",
    ),
    KnobSpec(
        "pulses",
        "int",
        default=4,
        minimum=0,
        maximum=16,
        description="How many stabs per bar (euclid-distributed).",
    ),
    KnobSpec(
        "offset",
        "int",
        default=2,
        minimum=0,
        maximum=15,
        description="Rotate the stab pattern N 16ths (offset 2 = classic off-beat).",
    ),
    KnobSpec(
        "gate",
        "float",
        default=0.4,
        minimum=0.05,
        maximum=2.0,
        description="Stab length as a fraction of a step. Short = staccato.",
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Transpose by N octaves.",
    ),
    KnobSpec(
        "base_vel",
        "int",
        default=90,
        minimum=0,
        maximum=127,
        description="Baseline velocity for each chord note.",
    ),
    KnobSpec(
        "velocity_spread",
        "int",
        default=6,
        minimum=0,
        maximum=64,
        description="±N velocity variation between chord notes.",
    ),
    KnobSpec(
        "drop_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-step chance the stab drops out (silence).",
    ),
)

_CC_LFO = (
    KnobSpec(
        "cc",
        "int",
        default=74,
        minimum=0,
        maximum=127,
        description="MIDI CC number to modulate (default 74 = filter cutoff).",
    ),
    KnobSpec(
        "shape",
        "choice",
        default="sine",
        choices=("sine", "tri", "saw", "ramp", "square", "random", "sh"),
        description="LFO waveform: sine / tri / saw / ramp / square / random / sample+hold.",
    ),
    KnobSpec(
        "period_bars",
        "float",
        default=4.0,
        minimum=0.25,
        maximum=64.0,
        step=0.25,
        decimals=2,
        description="Cycle length in bars (0.25 = beat, 1 = bar, 4 = 4 bars).",
    ),
    KnobSpec(
        "phase",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Starting phase of the cycle (0–1).",
    ),
    KnobSpec(
        "depth",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=1.0,
        description="How wide the LFO swings around the offset (0=flat, 1=full range).",
    ),
    KnobSpec(
        "offset",
        "float",
        default=0.5,
        minimum=0.0,
        maximum=1.0,
        description="Centre value (0=bottom, 0.5=middle, 1=top).",
    ),
    KnobSpec(
        "samples_per_bar",
        "int",
        default=16,
        minimum=1,
        maximum=128,
        description="How many CC values to emit per bar (higher = smoother).",
    ),
)

_CC_ENVELOPE = (
    KnobSpec(
        "cc",
        "int",
        default=74,
        minimum=0,
        maximum=127,
        description="MIDI CC number to send the envelope on (74 = filter cutoff).",
    ),
    KnobSpec(
        "pulses",
        "int",
        default=4,
        minimum=0,
        maximum=16,
        description="How many envelope retriggers per bar (euclid-distributed).",
    ),
    KnobSpec(
        "offset",
        "int",
        default=0,
        minimum=0,
        maximum=15,
        description="Rotate the trigger pattern N 16ths.",
    ),
    KnobSpec(
        "attack_ticks",
        "int",
        default=40,
        minimum=1,
        maximum=1920,
        description="Attack length in ticks (PPQ 480; 480 = a beat).",
    ),
    KnobSpec(
        "decay_ticks",
        "int",
        default=120,
        minimum=1,
        maximum=1920,
        description="Decay length in ticks.",
    ),
    KnobSpec(
        "release_ticks",
        "int",
        default=240,
        minimum=1,
        maximum=1920,
        description="Release length in ticks (from sustain back to rest).",
    ),
    KnobSpec(
        "peak_value",
        "int",
        default=120,
        minimum=0,
        maximum=127,
        description="CC value at the end of attack (envelope peak).",
    ),
    KnobSpec(
        "sustain_value",
        "int",
        default=90,
        minimum=0,
        maximum=127,
        description="CC value held between decay and release.",
    ),
    KnobSpec(
        "rest_value",
        "int",
        default=40,
        minimum=0,
        maximum=127,
        description="CC value the envelope rests at between triggers.",
    ),
    KnobSpec(
        "samples",
        "int",
        default=8,
        minimum=2,
        maximum=128,
        description="Samples per envelope stage (higher = smoother CC stream).",
    ),
)

_ROOT_PULSE = (
    KnobSpec(
        "pulses",
        "int",
        default=4,
        minimum=0,
        maximum=16,
        description="How many root-note pulses per bar (euclid-distributed).",
    ),
    KnobSpec(
        "offset",
        "int",
        default=0,
        minimum=0,
        maximum=15,
        description="Rotate the pulse pattern N 16ths within the bar.",
    ),
    KnobSpec(
        "velocity",
        "int",
        default=90,
        minimum=1,
        maximum=127,
        description="MIDI velocity for each pulse.",
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Octave offset for the emitted root note.",
    ),
    KnobSpec(
        "gate",
        "float",
        default=0.5,
        minimum=0.05,
        maximum=32.0,
        description=(
            "Note length as a fraction of a step. Range goes up to 32 so a"
            " single pulse can sustain across most of the bar (e.g. gate=15"
            " with pulses=1 = near-whole-bar root)."
        ),
    ),
)

_VOICE_FOLLOWER = (
    KnobSpec(
        "source",
        "string",
        default="",
        description="Name of the source voice this follower derives from.",
    ),
    KnobSpec(
        "shift_bars",
        "int",
        default=0,
        minimum=0,
        maximum=16,
        description="Delay the follower by N bars (creates a one-bar echo at 1).",
    ),
    KnobSpec(
        "latch",
        "choice",
        default="all",
        choices=("all", "first_per_bar", "every_nth", "accent_only"),
        description=("Which events pass through: all, first per bar, every Nth, or accents only."),
    ),
    KnobSpec(
        "every_nth",
        "int",
        default=2,
        minimum=1,
        maximum=16,
        description="N for the every_nth latch mode.",
    ),
    KnobSpec(
        "accent_threshold",
        "int",
        default=100,
        minimum=1,
        maximum=127,
        description="Minimum velocity counted as an 'accent' for the accent_only latch.",
    ),
    KnobSpec(
        "transform",
        "choice",
        default="none",
        choices=("none", "invert", "retrograde", "thin"),
        description="Per-bar transform: none / invert pitch / reverse order / thin events.",
    ),
    KnobSpec(
        "invert_axis",
        "int",
        default=60,
        minimum=0,
        maximum=127,
        description="Pitch axis for the invert transform (MIDI note number).",
    ),
    KnobSpec(
        "thin_prob",
        "float",
        default=0.5,
        minimum=0.0,
        maximum=1.0,
        description="Per-event drop probability for the thin transform.",
    ),
    KnobSpec(
        "transpose_semitones",
        "int",
        default=0,
        minimum=-24,
        maximum=24,
        description="Semitone shift applied to every output note.",
    ),
    KnobSpec(
        "transpose_octaves",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description="Additional octave shift applied to every output note.",
    ),
    KnobSpec(
        "quality",
        "choice",
        default="unison",
        choices=QUALITY_CHOICES,
        description="Stack a chord shape on every input note (unison = pass-through).",
    ),
    KnobSpec(
        "quantize",
        "choice",
        default="off",
        choices=("off", "nearest", "up", "down"),
        description="Snap output notes to a scale: off / nearest / up / down.",
    ),
    KnobSpec(
        "quantize_scale",
        "string",
        default="",
        description="Scale name to quantize to (empty = use the song's current scale).",
    ),
    KnobSpec(
        "ratchet",
        "int",
        default=1,
        minimum=1,
        maximum=8,
        description="Base retriggers per output note (1 = off; 3 = triplet fill primitive).",
    ),
    KnobSpec(
        "ratchet_curve",
        "choice",
        default="flat",
        choices=RATCHET_CURVE_CHOICES,
        description=(
            "How ratchet count varies across the bar: flat / ramp_up / last_beat / pulse "
            "(combine with ratchet=3 for triplet fills)."
        ),
    ),
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
        maximum=1.0,
        description="Shuffle: 0=straight, 0.5≈classic MPC, 1.0=full 16th-triplet feel",
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
