"""Recipe = the deterministic blueprint :func:`compose` walks.

The recipe sits between high-level mood/format/chaos inputs and the
concrete :class:`jtx.model.Song`. ``build_recipe`` collapses the inputs
into:

* :class:`MoodBlueprint` — tempo / key / scale / feel-knob targets.
* :class:`FormatBlueprint` — part-count / bar-budget / intensity shape.
* :class:`VoiceRecipe` per palette voice — algorithm pick + pattern
  knob *ranges*. Concrete knob values are sampled by ``compose``.

Chaos perturbs every range (widens windows + bumps the chance of
weird-pick algorithms) so the same anchor + format combination still
produces varied songs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jtx.composer.format import FORMAT_SPECS, FormatType
from jtx.composer.mood import MoodSpec
from jtx.composer.voices import FIXED_PALETTE


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _norm_axis(value: float) -> float:
    """Clamp a [-1, 1] axis and shift to [0, 1] for monotonic math."""
    return (_clamp(value, -1.0, 1.0) + 1.0) * 0.5


@dataclass(frozen=True)
class MoodBlueprint:
    """High-level musical defaults derived from a :class:`MoodSpec`."""

    tempo_range: tuple[int, int]
    """BPM range the sampler picks from."""
    scale: str
    """Scale name (e.g. ``"minor"``, ``"major"``)."""
    tonic_choices: tuple[str, ...]
    """Tonic letters the sampler picks from."""
    feel_targets: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Per-feel-knob (pump/groove/drive/tension/wander) sampling
    windows in ``[0, 1]``."""


@dataclass(frozen=True)
class FormatBlueprint:
    """Structural budget derived from a :class:`FormatType`."""

    part_count: int
    """How many parts to generate."""
    bars_per_part: tuple[int, int]
    """Range for individual part bar counts."""
    intensity_envelope: tuple[tuple[float, float], ...]
    """One ``(start, end)`` tuple per part, in arrangement order."""
    loop: bool
    """If True, the (single) part is generated with ``Part.loop=True``."""


@dataclass(frozen=True)
class VoiceRecipe:
    """Per-voice algorithm pick + pattern-knob ranges."""

    algorithm: str
    """Algorithm name registered in :mod:`jtx.algorithms`."""
    pattern_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Float knob ranges. The sampler picks one value per knob."""
    pattern_int_ranges: dict[str, tuple[int, int]] = field(default_factory=dict)
    """Int knob ranges (inclusive on both ends)."""
    pattern_fixed: dict[str, object] = field(default_factory=dict)
    """Knobs whose value is fixed by the recipe (not sampled)."""


@dataclass(frozen=True)
class Recipe:
    """A composable recipe ``compose`` turns into a Song."""

    mood: MoodBlueprint
    format: FormatBlueprint
    voices: dict[str, VoiceRecipe]
    """Keyed by palette voice name; one entry per :data:`FIXED_PALETTE`
    voice. Utility voices (``filter``, ``root_ref``, ``chord_ref``) are
    wired by :func:`compose` directly — they have no per-song range
    space to sample."""


# ---------- mood → musical defaults ------------------------------------


def _mood_blueprint(mood: MoodSpec, chaos: float) -> MoodBlueprint:
    """Translate mood-pad position into tempo / key / feel windows."""
    energy = _norm_axis(mood.energy)
    valence = _norm_axis(mood.valence)

    # Energy drives tempo. Calm 80 -> intense 152 BPM (rough club range).
    tempo_centre = int(80 + energy * 72)
    spread = int(6 + chaos * 8)
    tempo_range = (
        max(60, tempo_centre - spread),
        min(180, tempo_centre + spread),
    )

    scale = "major" if valence > 0.55 else "minor"
    # Tonic letters: bright moods favour sharp keys, dark moods flat keys.
    if valence > 0.55:
        tonic_choices = ("C", "D", "E", "G", "A")
    elif valence < 0.45:
        tonic_choices = ("A", "C", "D", "E", "F", "G")
    else:
        tonic_choices = ("A", "C", "D", "E", "G")

    # Five global feel knobs; each window centred on a mood-driven point.
    pump = 0.25 + energy * 0.45
    groove = 0.20 + (1.0 - abs(mood.valence)) * 0.35
    drive = 0.20 + energy * 0.55
    tension = 0.20 + (1.0 - valence) * 0.45 + chaos * 0.15
    wander = 0.10 + chaos * 0.45

    def _window(centre: float) -> tuple[float, float]:
        half = 0.05 + chaos * 0.12
        return (_clamp(centre - half, 0.0, 1.0), _clamp(centre + half, 0.0, 1.0))

    feel_targets = {
        "pump": _window(pump),
        "groove": _window(groove),
        "drive": _window(drive),
        "tension": _window(tension),
        "wander": _window(wander),
    }

    return MoodBlueprint(
        tempo_range=tempo_range,
        scale=scale,
        tonic_choices=tonic_choices,
        feel_targets=feel_targets,
    )


# ---------- format → structural budget ---------------------------------


def _intensity_envelope(
    archetype: str, part_count: int, energy_norm: float
) -> tuple[tuple[float, float], ...]:
    """Build the per-part (start, end) intensity tuples for *archetype*."""
    peak = _clamp(0.6 + energy_norm * 0.35, 0.4, 0.98)
    floor = _clamp(0.15 + energy_norm * 0.15, 0.1, 0.5)

    if archetype == "single":
        # A single part — small ramp toward peak, no full arc.
        return ((floor + 0.1, peak),)
    if archetype == "build":
        # Monotonic ascent from floor to peak across all parts.
        envs: list[tuple[float, float]] = []
        for i in range(part_count):
            start = floor + (peak - floor) * (i / max(1, part_count))
            end = floor + (peak - floor) * ((i + 1) / part_count)
            envs.append((start, end))
        return tuple(envs)
    if archetype == "arc":
        # intro / build / drop / break / drop2 / outro shape.
        shape = (
            (floor, floor + 0.15),
            (floor + 0.15, peak - 0.1),
            (peak - 0.05, peak),
            (peak * 0.55, peak * 0.7),
            (peak - 0.1, peak),
            (peak * 0.6, floor + 0.05),
        )
        return shape[:part_count]
    # extended_arc: intro / build / drop / break / build2 / drop2 / break2 / outro
    shape = (
        (floor, floor + 0.1),
        (floor + 0.1, peak - 0.15),
        (peak - 0.05, peak),
        (peak * 0.55, peak * 0.7),
        (peak * 0.7, peak - 0.05),
        (peak, peak),
        (peak * 0.55, peak * 0.65),
        (peak * 0.6, floor),
    )
    return shape[:part_count]


def _format_blueprint(
    fmt: FormatType, energy_norm: float, chaos: float
) -> FormatBlueprint:
    spec = FORMAT_SPECS[fmt]
    # Part count: anchor to the upper end of the range as chaos rises.
    pc_lo, pc_hi = spec.part_count_range
    part_count = pc_lo + round(chaos * (pc_hi - pc_lo))
    envelope = _intensity_envelope(spec.intensity_archetype, part_count, energy_norm)
    return FormatBlueprint(
        part_count=part_count,
        bars_per_part=spec.bars_per_part_range,
        intensity_envelope=envelope,
        loop=spec.loop_only,
    )


# ---------- voice recipes ----------------------------------------------

# Algorithm shortlists per palette voice. The first entry is the
# "default" pick the sampler chooses without chaos; the rest become
# eligible as chaos rises.
_VOICE_ALGO_SHORTLISTS: dict[str, tuple[str, ...]] = {
    "drumkit": ("drum_kit",),
    "bass": ("acid_bass", "reese_bass"),
    "sub": ("sub_drone", "rest"),
    "lead": ("melodic_line", "motif_phrase", "arp", "rest"),
    "pad": ("sustained_chord", "rest"),
    "chord": ("chord_stab", "sustained_chord"),
    "arp": ("arp", "rest"),
    "stabs": ("chord_stab", "rest"),
    "fx": ("step_cc", "noise_riser", "rest"),
}


def _pick_voice_algorithm(
    voice: str, energy_norm: float, valence_norm: float, chaos: float
) -> str:
    """Pick an algorithm for *voice* using mood + chaos as bias.

    Low-energy songs favour ``rest`` for energy-heavy voices (lead,
    arp, fx); low-valence songs favour darker basses (reese over acid).
    Chaos broadens the shortlist of eligible algorithms.
    """
    shortlist = _VOICE_ALGO_SHORTLISTS[voice]

    if voice == "bass":
        return shortlist[0] if valence_norm > 0.45 else shortlist[1]
    if voice == "sub":
        # Sub joins as energy rises; chaos lets it sneak in earlier.
        return "sub_drone" if (energy_norm + chaos * 0.3) > 0.4 else "rest"
    if voice == "lead":
        if energy_norm + chaos * 0.2 < 0.35:
            return "rest"
        if valence_norm > 0.6:
            return "motif_phrase"
        if energy_norm > 0.7:
            return "melodic_line"
        return "arp" if chaos > 0.4 else shortlist[0]
    if voice == "pad":
        return "sustained_chord" if valence_norm > 0.3 or chaos > 0.3 else "rest"
    if voice == "chord":
        return "chord_stab" if energy_norm > 0.45 else "sustained_chord"
    if voice == "arp":
        return "arp" if (energy_norm > 0.55 or chaos > 0.5) else "rest"
    if voice == "stabs":
        return "chord_stab" if energy_norm > 0.4 else "rest"
    if voice == "fx":
        if energy_norm > 0.7:
            return "noise_riser"
        return "step_cc" if chaos > 0.25 else "rest"
    return shortlist[0]


def _voice_pattern_ranges(
    voice: str, algorithm: str, energy_norm: float, valence_norm: float, chaos: float
) -> tuple[
    dict[str, tuple[float, float]],
    dict[str, tuple[int, int]],
    dict[str, object],
]:
    """Per-(voice, algorithm) knob ranges + fixed knobs.

    Kept compact: only knobs the composer actively shapes appear here;
    every other knob inherits its algorithm default. This is enough for
    PR 2 (the GUI layer in PR 4+ can over-tune).
    """
    floats: dict[str, tuple[float, float]] = {}
    ints: dict[str, tuple[int, int]] = {}
    fixed: dict[str, object] = {}

    if algorithm == "rest":
        return floats, ints, fixed

    if algorithm == "drum_kit":
        # Punch follows energy; mech is biased mid with chaos spread.
        punch_centre = 0.4 + energy_norm * 0.45
        mech_centre = 0.5
        spread = 0.05 + chaos * 0.2
        floats["punch"] = (
            _clamp(punch_centre - spread, 0.0, 1.0),
            _clamp(punch_centre + spread, 0.0, 1.0),
        )
        floats["mech"] = (
            _clamp(mech_centre - spread, 0.0, 1.0),
            _clamp(mech_centre + spread, 0.0, 1.0),
        )
        floats["density"] = (0.4 + energy_norm * 0.2, 0.55 + energy_norm * 0.25)
        floats["variation"] = (0.15 + chaos * 0.2, 0.3 + chaos * 0.3)
        floats["perc_complexity"] = (0.2 + chaos * 0.15, 0.4 + chaos * 0.35)
        return floats, ints, fixed

    if algorithm == "acid_bass":
        floats["drop_prob"] = (0.15 + chaos * 0.1, 0.4 + chaos * 0.15)
        floats["slide_prob"] = (0.1, 0.45 + chaos * 0.2)
        floats["gate"] = (0.4, 0.9)
        floats["intensity"] = (0.9, 1.2 + chaos * 0.2)
        ints["base_vel"] = (85, 105)
        ints["resonance"] = (70 + int(energy_norm * 30), 110 + int(chaos * 17))
        return floats, ints, fixed

    if algorithm == "reese_bass":
        floats["wobble_depth"] = (0.4 + energy_norm * 0.2, 0.7 + energy_norm * 0.2)
        floats["detune_depth"] = (0.2, 0.5 + chaos * 0.3)
        ints["base_vel"] = (90, 110)
        return floats, ints, fixed

    if algorithm == "sub_drone":
        floats["fifth_prob"] = (0.0, 0.25 + chaos * 0.25)
        ints["bars_per_chord"] = (2, 4)
        return floats, ints, fixed

    if algorithm == "melodic_line":
        floats["drop_prob"] = (0.4, 0.7 + chaos * 0.1)
        floats["passing_prob"] = (0.05, 0.2 + chaos * 0.2)
        floats["intensity"] = (0.9, 1.2)
        return floats, ints, fixed

    if algorithm == "motif_phrase":
        floats["motif_complexity"] = (0.3 + energy_norm * 0.2, 0.6 + energy_norm * 0.2)
        floats["variation_depth"] = (0.3, 0.6 + chaos * 0.3)
        floats["density"] = (0.5 + energy_norm * 0.2, 0.85)
        return floats, ints, fixed

    if algorithm == "arp":
        floats["gate"] = (0.4, 0.8)
        ints["octaves"] = (1, 2 if chaos > 0.4 else 1)
        ints["base_vel"] = (85, 105)
        return floats, ints, fixed

    if algorithm == "sustained_chord":
        floats["gate"] = (0.85, 0.98)
        floats["drift_prob"] = (0.0, 0.15 + chaos * 0.25)
        ints["base_vel"] = (65, 90)
        return floats, ints, fixed

    if algorithm == "chord_stab":
        floats["gate"] = (0.25, 0.5)
        floats["drop_prob"] = (0.0, 0.15 + chaos * 0.15)
        ints["pulses"] = (3, 6)
        ints["offset"] = (1, 3)
        ints["base_vel"] = (80, 100)
        return floats, ints, fixed

    if algorithm == "step_cc":
        floats["depth"] = (0.4 + energy_norm * 0.3, 0.8)
        ints["value_min"] = (20, 45)
        ints["value_max"] = (95, 120)
        fixed["function"] = "cutoff"
        return floats, ints, fixed

    if algorithm == "noise_riser":
        ints["duration_bars"] = (2, 4)
        ints["cutoff_start"] = (20, 40)
        ints["cutoff_end"] = (100, 124)
        ints["vel_start"] = (35, 55)
        ints["vel_end"] = (100, 122)
        return floats, ints, fixed

    return floats, ints, fixed


def build_recipe(mood: MoodSpec, fmt: FormatType, chaos: float) -> Recipe:
    """Collapse (mood, format, chaos) into a deterministic :class:`Recipe`.

    The recipe carries ranges, not concrete values — :func:`compose`
    is the consumer that samples from them with a seeded RNG. Pure
    function: same inputs always return the same Recipe.
    """
    chaos = _clamp(chaos, 0.0, 1.0)
    energy_norm = _norm_axis(mood.energy)
    valence_norm = _norm_axis(mood.valence)

    mood_bp = _mood_blueprint(mood, chaos)
    fmt_bp = _format_blueprint(fmt, energy_norm, chaos)

    voices: dict[str, VoiceRecipe] = {}
    for voice in FIXED_PALETTE:
        algorithm = _pick_voice_algorithm(voice, energy_norm, valence_norm, chaos)
        floats, ints, fixed = _voice_pattern_ranges(
            voice, algorithm, energy_norm, valence_norm, chaos
        )
        voices[voice] = VoiceRecipe(
            algorithm=algorithm,
            pattern_ranges=floats,
            pattern_int_ranges=ints,
            pattern_fixed=fixed,
        )

    return Recipe(mood=mood_bp, format=fmt_bp, voices=voices)


__all__ = [
    "FormatBlueprint",
    "MoodBlueprint",
    "Recipe",
    "VoiceRecipe",
    "build_recipe",
]
