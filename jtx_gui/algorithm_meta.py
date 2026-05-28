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
from jtx.algorithms._contours import CONTOUR_NAMES
from jtx.algorithms._cycle import CYCLE_BARS_CHOICES
from jtx.algorithms._palettes import PALETTE_CHOICES
from jtx.algorithms._phrase_shapes import PHRASE_SHAPE_CHOICES, PROGRESSION_MODES
from jtx.algorithms._rhythm_templates import TEMPLATE_NAMES
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

_DRUM_KIT = (
    KnobSpec(
        "style",
        "choice",
        default="techno",
        choices=("acid", "techno", "psy"),
        description="Preset family — biases kick/snare/hat velocities + ghost-note flavour.",
    ),
    KnobSpec(
        "kit_focus",
        "choice",
        default="full",
        choices=(
            "full",
            "minimal",
            "kick_only",
            "no_kick",
            "percussion",
            "build",
            "wind_down",
        ),
        description=(
            "Which pieces play. 'build' ramps snare density with part_progress; "
            "'wind_down' fades to half-time kick; 'kick_only' is the psy "
            "drop's moment-of-silence move."
        ),
    ),
    KnobSpec(
        "density",
        "float",
        default=0.5,
        minimum=0.0,
        maximum=1.0,
        description="Overall density multiplier on top of part intensity.",
    ),
    KnobSpec(
        "variation",
        "float",
        default=0.3,
        minimum=0.0,
        maximum=1.0,
        description="Per-bar pseudo-random drift amplitude (kept seed-deterministic).",
    ),
    KnobSpec(
        "kick_pattern",
        "choice",
        default="auto",
        choices=("auto", "four_floor", "half_time", "break"),
        description=(
            "Force a kick pattern, or 'auto' to derive from intensity "
            "(four_floor when high, half_time when low)."
        ),
    ),
    KnobSpec(
        "snare_subdiv",
        "choice",
        default="auto",
        choices=("auto", "16", "32", "8t"),
        description=(
            "Snare grid. 'auto' ramps 8th → 16th → 32nd across intensity² "
            "(the machine-gun snare path)."
        ),
    ),
    KnobSpec(
        "hat_pulses",
        "int",
        default=-1,
        minimum=-1,
        maximum=16,
        description="Closed-hat pulses across the bar; -1 = auto-derive from intensity.",
    ),
    KnobSpec(
        "clap_on",
        "choice",
        default="intensity_gate",
        choices=("never", "2_and_4", "intensity_gate"),
        description=(
            "When the clap fires. 'intensity_gate' = backbeat above 0.7 intensity."
        ),
    ),
    KnobSpec(
        "perc_complexity",
        "float",
        default=0.4,
        minimum=0.0,
        maximum=1.0,
        description="How busy percussion + tom + clave + cowbell layers run.",
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
    KnobSpec(
        "pitch_cycle_bars",
        "choice",
        default="off",
        choices=CYCLE_BARS_CHOICES,
        description=(
            "Loop the root/octave/third pitch picks (and pitch-bend) on an N-bar cycle. "
            "Combine with rhythm_cycle_bars for a fully repeating acid line. "
            "Not v1 LFO target."
        ),
    ),
    KnobSpec(
        "rhythm_cycle_bars",
        "choice",
        default="off",
        choices=CYCLE_BARS_CHOICES,
        description=("Loop drop / triplet / slide rolls on an N-bar cycle. Not v1 LFO target."),
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
    KnobSpec(
        "fifth_cycle_bars",
        "choice",
        default="off",
        choices=CYCLE_BARS_CHOICES,
        description=(
            "Loop the fifth_prob override roll on an N-bar cycle. "
            "With '4' the per-bar 'force fifth?' coin flip becomes a 4-bar pattern. "
            "Not v1 LFO target."
        ),
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
    KnobSpec(
        "pitch_cycle_bars",
        "choice",
        default="off",
        choices=CYCLE_BARS_CHOICES,
        description=(
            "Loop palette-degree picks on an N-bar cycle. "
            "'off' = bar-fresh; '4' = 4-bar phrase repeats; 'part' = same across part. "
            "Not v1 LFO target."
        ),
    ),
    KnobSpec(
        "rhythm_cycle_bars",
        "choice",
        default="off",
        choices=CYCLE_BARS_CHOICES,
        description=(
            "Loop drop / triplet rolls on an N-bar cycle. "
            "Compose with pitch_cycle_bars for a fully looping phrase. "
            "Not v1 LFO target."
        ),
    ),
)

_MOTIF_PHRASE = (
    KnobSpec(
        "phrase_shape",
        "choice",
        default="A_A_A_B",
        choices=PHRASE_SHAPE_CHOICES,
        description=(
            "Phrase template: which bars are A, A', A'', B. "
            "'random_walk' falls back to per-bar fresh motifs (no phrase structure). "
            "Not v1 LFO target."
        ),
    ),
    KnobSpec(
        "phrase_length_bars",
        "int",
        default=4,
        minimum=2,
        maximum=8,
        description=(
            "Bars per phrase cycle. Also the hold period for the motif content RNG. "
            "LFO target — int range not scaled in v1."
        ),
    ),
    KnobSpec(
        "motif_length_beats",
        "int",
        default=1,
        minimum=1,
        maximum=4,
        description=(
            "Beats per motif cell. Cell repeats inside the bar; trailing partial truncated. "
            "LFO target — int range not scaled in v1."
        ),
    ),
    KnobSpec(
        "rhythm_template",
        "choice",
        default="auto",
        choices=("auto",) + TEMPLATE_NAMES,
        description=(
            "Rhythm cell. 'auto' lets motif_complexity + phrase RNG pick. Not v1 LFO target."
        ),
    ),
    KnobSpec(
        "motif_complexity",
        "float",
        default=0.4,
        minimum=0.0,
        maximum=1.0,
        description=(
            "Biases 'auto' template / contour selection toward busier shapes. LFO-friendly."
        ),
    ),
    KnobSpec(
        "contour",
        "choice",
        default="auto",
        choices=("auto",) + CONTOUR_NAMES,
        description=(
            "Pitch curve through palette positions. 'auto' uses motif_complexity. "
            "Not v1 LFO target."
        ),
    ),
    KnobSpec(
        "palette",
        "choice",
        default="tones_only",
        choices=PALETTE_CHOICES,
        description="Scale-degree pool the motif draws from. Not v1 LFO target.",
    ),
    KnobSpec(
        "density",
        "float",
        default=0.7,
        minimum=0.0,
        maximum=1.0,
        description=(
            "Post-template fire probability per position (1.0 = all template hits fire). "
            "LFO-friendly."
        ),
    ),
    KnobSpec(
        "variation_depth",
        "float",
        default=0.5,
        minimum=0.0,
        maximum=1.0,
        description=(
            "A' / A'' transform intensity. Higher = more transforms composed in. LFO-friendly."
        ),
    ),
    KnobSpec(
        "b_section_difference",
        "float",
        default=0.7,
        minimum=0.0,
        maximum=1.0,
        description=(
            "How far the B-section motif departs from A "
            "(0 = contour swap; 0.5 = tension transpose; 1 = full re-roll). "
            "LFO-friendly."
        ),
    ),
    KnobSpec(
        "progression_mode",
        "choice",
        default="static",
        choices=PROGRESSION_MODES,
        description=(
            "Cross-bar scale-step transpose per phrase-slot. Scale-aware (not chromatic). "
            "Not v1 LFO target."
        ),
    ),
    KnobSpec(
        "progression_range",
        "int",
        default=4,
        minimum=1,
        maximum=7,
        description=(
            "Max scale-step span for the progression. LFO target — int range not scaled in v1."
        ),
    ),
    KnobSpec(
        "octave",
        "int",
        default=0,
        minimum=-3,
        maximum=3,
        description=(
            "Register shift (0 = octave 4 lead range). LFO target — int range not scaled in v1."
        ),
    ),
    KnobSpec(
        "gate",
        "float",
        default=0.5,
        minimum=0.05,
        maximum=2.0,
        description="Note length as a fraction of position spacing. LFO-friendly.",
    ),
    KnobSpec(
        "base_vel",
        "int",
        default=95,
        minimum=0,
        maximum=127,
        description=("Baseline MIDI velocity. LFO target — int range not scaled in v1."),
    ),
    KnobSpec(
        "intensity",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=2.0,
        description="Velocity multiplier — >1 punches harder, <1 softer. LFO-friendly.",
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
    KnobSpec(
        "pitch_cycle_bars",
        "choice",
        default="off",
        choices=CYCLE_BARS_CHOICES,
        description=(
            "Loop the random / walk pitch picks on an N-bar cycle. "
            "No effect on deterministic up / down / up_down modes. "
            "Not v1 LFO target."
        ),
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

_CC_ENVELOPE = (
    KnobSpec(
        "function",
        "string",
        default="cutoff",
        description=(
            "Semantic parameter name (cutoff / resonance / glide / …). "
            "The voice slot's parameter_map decides whether this becomes "
            "a CC / MPE / OSC message."
        ),
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


_NOISE_RISER = (
    KnobSpec(
        "trigger",
        "choice",
        default="every",
        choices=("once", "every", "last_bar_of_4", "last_bar_of_8", "last_bar_of_16"),
        description="When the riser fires (once / repeating / single bar).",
    ),
    KnobSpec(
        "duration_bars",
        "int",
        default=4,
        minimum=1,
        maximum=32,
        description="Riser window length in bars (once / every triggers).",
    ),
    KnobSpec(
        "cycle_bars",
        "int",
        default=16,
        minimum=1,
        maximum=64,
        description="Repeat period for the 'every' trigger.",
    ),
    KnobSpec(
        "base_note",
        "string",
        default="A4",
        description="Held pitch (e.g. A4, C#3).",
    ),
    KnobSpec(
        "cutoff_start",
        "int",
        default=30,
        minimum=0,
        maximum=127,
        description="Starting CC74 value at the bottom of the rise.",
    ),
    KnobSpec(
        "cutoff_end",
        "int",
        default=120,
        minimum=0,
        maximum=127,
        description="Final CC74 value at the top of the rise.",
    ),
    KnobSpec(
        "vel_start",
        "int",
        default=40,
        minimum=1,
        maximum=127,
        description="Starting per-bar NoteOn velocity.",
    ),
    KnobSpec(
        "vel_end",
        "int",
        default=120,
        minimum=1,
        maximum=127,
        description="Final per-bar NoteOn velocity.",
    ),
    KnobSpec(
        "pitch_rise_cents",
        "int",
        default=0,
        minimum=0,
        maximum=2400,
        description="Total pitch-bend rise in cents (0 = no pitch movement).",
    ),
    KnobSpec(
        "curve",
        "choice",
        default="exp",
        choices=("linear", "exp", "s_curve"),
        description="Shape of the rise: linear / exp / s_curve.",
    ),
    KnobSpec(
        "samples_per_bar",
        "int",
        default=16,
        minimum=2,
        maximum=64,
        description="CC density per bar (higher = smoother sweep).",
    ),
)

_REESE_BASS = (
    KnobSpec(
        "gate",
        "float",
        default=0.95,
        minimum=0.05,
        maximum=1.0,
        description="Note length as a fraction of the bar.",
    ),
    KnobSpec(
        "wobble_subdiv",
        "choice",
        default="8",
        choices=SUBDIVISION_CHOICES,
        description="Subdivision the cutoff wobble runs on (8t/16t = triplet wobble).",
    ),
    KnobSpec(
        "wobble_depth",
        "float",
        default=0.7,
        minimum=0.0,
        maximum=1.0,
        description="CC74 modulation depth (0 = silent wobble, 1 = full swing).",
    ),
    KnobSpec(
        "wobble_phase",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Initial phase of the wobble (0..1).",
    ),
    KnobSpec(
        "cutoff_min",
        "int",
        default=35,
        minimum=0,
        maximum=127,
        description="Low end of the CC74 wobble range.",
    ),
    KnobSpec(
        "cutoff_max",
        "int",
        default=110,
        minimum=0,
        maximum=127,
        description="High end of the CC74 wobble range.",
    ),
    KnobSpec(
        "detune_depth",
        "float",
        default=0.4,
        minimum=0.0,
        maximum=1.0,
        description="Modwheel-routed detune modulation depth (0 = off).",
    ),
    KnobSpec(
        "detune_cycle_bars",
        "float",
        default=2.0,
        minimum=0.0,
        maximum=32.0,
        description="Detune LFO period in bars.",
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
        minimum=-2,
        maximum=3,
        description="Register shift; 0 = default reese register (octave 1).",
    ),
    KnobSpec(
        "bars_per_chord",
        "int",
        default=2,
        minimum=1,
        maximum=16,
        description="Cell length in bars for root/fifth alternation.",
    ),
    KnobSpec(
        "fifth_prob",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-bar chance of jumping to the fifth.",
    ),
)

_STEP_CC = (
    KnobSpec(
        "function",
        "string",
        default="cutoff",
        description=(
            "Semantic parameter name (cutoff / resonance / glide / …). "
            "The voice slot's parameter_map decides the concrete target."
        ),
    ),
    KnobSpec(
        "subdivision",
        "choice",
        default="16",
        choices=SUBDIVISION_CHOICES,
        description="Step grid (16t/8t = triplet-feel rhythmic sweep).",
    ),
    KnobSpec(
        "value_curve",
        "choice",
        default="ramp_up",
        choices=("flat", "ramp_up", "ramp_down", "arc", "valley", "pulse", "drift", "surprise"),
        description="Per-step value shape across the bar.",
    ),
    KnobSpec(
        "value_min",
        "int",
        default=40,
        minimum=0,
        maximum=127,
        description="Low end of the value range (0..127).",
    ),
    KnobSpec(
        "value_max",
        "int",
        default=110,
        minimum=0,
        maximum=127,
        description="High end of the value range (0..127).",
    ),
    KnobSpec(
        "depth",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=1.0,
        description="How strongly the curve modulates around centre (0 = flat at centre).",
    ),
    KnobSpec(
        "samples_per_step",
        "int",
        default=1,
        minimum=1,
        maximum=8,
        description="Emit N CCs per step for smoothing (1 = raw step values).",
    ),
)


ALGORITHMS: dict[str, AlgorithmMeta] = {
    "drum_kit": AlgorithmMeta("drum_kit", ("drum_kit",), _DRUM_KIT),
    "drum_pattern": AlgorithmMeta("drum_pattern", ("drum",), _DRUM_PATTERN),
    "drum_one_shot": AlgorithmMeta("drum_one_shot", ("drum",), _DRUM_ONE_SHOT),
    "acid_bass": AlgorithmMeta("acid_bass", ("mono",), _ACID_BASS),
    "sub_drone": AlgorithmMeta("sub_drone", ("mono",), _SUB_DRONE),
    "reese_bass": AlgorithmMeta("reese_bass", ("mono",), _REESE_BASS),
    "melodic_line": AlgorithmMeta("melodic_line", ("mono",), _MELODIC_LINE),
    "motif_phrase": AlgorithmMeta("motif_phrase", ("mono",), _MOTIF_PHRASE),
    "arp": AlgorithmMeta("arp", ("mono",), _ARP),
    "noise_riser": AlgorithmMeta("noise_riser", ("mono",), _NOISE_RISER),
    "sustained_chord": AlgorithmMeta("sustained_chord", ("poly",), _SUSTAINED_CHORD),
    "chord_stab": AlgorithmMeta("chord_stab", ("poly",), _CHORD_STAB),
    "cc_envelope": AlgorithmMeta("cc_envelope", ("modulator",), _CC_ENVELOPE),
    "step_cc": AlgorithmMeta("step_cc", ("modulator",), _STEP_CC),
    "root_pulse": AlgorithmMeta("root_pulse", ("drum", "mono", "poly"), _ROOT_PULSE),
    "voice_follower": AlgorithmMeta("voice_follower", ("follower",), _VOICE_FOLLOWER),
}


def algorithms_for(voice_type: VoiceType) -> list[AlgorithmMeta]:
    """Return all algorithms whose declared voice-type list includes ``voice_type``."""
    return [meta for meta in ALGORITHMS.values() if voice_type in meta.voice_types]


# ---- per-voice mix-pass knob schema (schema v3, was "feel") -----------------
#
# In schema v3 the bar-internal per-voice feel knobs (humanize / swing /
# accent / mute_prob / octave_jump …) were retired in favour of the
# song-wide :data:`GLOBAL_FEEL_KNOBS`. What survives at the per-voice
# layer are the mix-pass knobs — sidechain, fade envelope, evolution.
# These live in :attr:`VoiceConfig.mix` / :attr:`VoiceOverride.mix`.

MIX_KNOBS: tuple[KnobSpec, ...] = (
    KnobSpec(
        "sidechain_floor",
        "int",
        default=60,
        minimum=0,
        maximum=127,
        description="Velocity floor at full duck",
    ),
    KnobSpec(
        "sidechain_release_beats",
        "float",
        default=1.0,
        minimum=0.05,
        maximum=4.0,
        description="Release time of duck in quarter notes",
    ),
    KnobSpec(
        "fade_in_at_bar",
        "int",
        default=0,
        minimum=0,
        maximum=64,
        description="Bar within part at which fade-in begins",
    ),
    KnobSpec(
        "fade_in_beats",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=64.0,
        description="Fade-in ramp duration (quarter notes)",
    ),
    KnobSpec(
        "fade_out_at_bar",
        "int",
        default=0,
        minimum=0,
        maximum=64,
        description="Bar within part at which fade-out begins",
    ),
    KnobSpec(
        "fade_out_beats",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=64.0,
        description="Fade-out ramp duration (quarter notes)",
    ),
    KnobSpec(
        "fade_sustain_level",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=1.0,
        description="Sustained velocity multiplier after fade-in",
    ),
    KnobSpec(
        "evolution_start",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=2.0,
        description="Velocity multiplier at bar 0 of part",
    ),
    KnobSpec(
        "evolution_end",
        "float",
        default=1.0,
        minimum=0.0,
        maximum=2.0,
        description="Velocity multiplier at last bar of part",
    ),
)

# Backwards-compat alias for the GUI's old import name. Identical to MIX_KNOBS.
FEEL_KNOBS: tuple[KnobSpec, ...] = MIX_KNOBS


# ---- song-wide feel knob schema (schema v3) ----------------------------------
#
# The five global feel knobs live at the song level and are compiled or
# applied across all voices: Pump (sidechain), Groove (swing/humanize/
# accent), Drive (velocity boost), Tension (intensity reshape), Wander
# (mute / octave-jump).

GLOBAL_FEEL_KNOBS: tuple[KnobSpec, ...] = (
    KnobSpec(
        "pump",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Sidechain depth driven by kick triggers",
    ),
    KnobSpec(
        "groove",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Swing + humanize + backbeat accent",
    ),
    KnobSpec(
        "drive",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Velocity boost + drum_kit ghost/roll energy",
    ),
    KnobSpec(
        "tension",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Reshape part intensity envelope",
    ),
    KnobSpec(
        "wander",
        "float",
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="Per-bar mute + per-note octave-jump probability",
    ),
)


@dataclass(frozen=True)
class _LoadedSchemas:
    pattern_by_algo: dict[str, dict[str, KnobSpec]] = field(default_factory=dict)
    mix_knobs: dict[str, KnobSpec] = field(default_factory=dict)
    global_feel: dict[str, KnobSpec] = field(default_factory=dict)


def _build() -> _LoadedSchemas:
    return _LoadedSchemas(
        pattern_by_algo={
            name: {k.name: k for k in meta.pattern} for name, meta in ALGORITHMS.items()
        },
        mix_knobs={k.name: k for k in MIX_KNOBS},
        global_feel={k.name: k for k in GLOBAL_FEEL_KNOBS},
    )


SCHEMAS = _build()
