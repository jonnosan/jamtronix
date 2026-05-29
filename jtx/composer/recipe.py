"""Recipe = the deterministic blueprint :func:`compose` walks.

The recipe sits between high-level mood/format/chaos inputs and the
concrete :class:`jtx.model.Song`. ``build_recipe`` collapses the inputs
into:

* :class:`MoodBlueprint` — tempo / key / scale / feel-knob targets.
* :class:`FormatBlueprint` — part-count / bar-budget / intensity shape.
* :class:`VoiceRecipe` per palette voice — algorithm pick + pattern
  knob *ranges*. Concrete knob values are sampled by ``compose``.

Texture and motion shape what gets played, in two independent ways:

* **Texture** in ``[0, 1]`` is arrangement thickness. Each palette voice
  has an activation threshold ``τ_v``; below it the voice runs
  ``rest``. At or above ``τ_v`` the voice's per-algorithm "density"
  knob ramps from 0 → 1 as texture rises further.
* **Motion** in ``[0, 1]`` shifts the algorithm shortlist toward
  animated variants (bass → rolling acid; arp subdivision ↑;
  chord stab vs sustained) and drives the filter LFO depth + speed.
  Motion also nudges τ — high motion lowers τ for ``arp`` / ``lead``
  and raises τ for ``pad`` / ``sub``, so the same texture fills the
  palette with different voices depending on motion.

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


def _mood_blueprint(
    mood: MoodSpec, chaos: float, texture: float, motion: float
) -> MoodBlueprint:
    """Translate mood + texture + motion into tempo / key / feel windows."""
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
    # Texture + motion now nudge each centre:
    # - pump rises with texture (lush mixes need sidechain breathing room)
    #   and drops with motion (psytrance = high motion + low pump).
    # - groove gains a small lift from motion.
    # - drive rises with motion.
    # - wander gains from motion in addition to chaos.
    pump = 0.25 + energy * 0.35 + texture * 0.20 - motion * 0.20
    groove = 0.20 + (1.0 - abs(mood.valence)) * 0.30 + motion * 0.10
    drive = 0.20 + energy * 0.45 + motion * 0.20
    tension = 0.20 + (1.0 - valence) * 0.45 + chaos * 0.15
    wander = 0.10 + chaos * 0.35 + motion * 0.20

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
        return ((floor + 0.1, peak),)
    if archetype == "build":
        envs: list[tuple[float, float]] = []
        for i in range(part_count):
            start = floor + (peak - floor) * (i / max(1, part_count))
            end = floor + (peak - floor) * ((i + 1) / part_count)
            envs.append((start, end))
        return tuple(envs)
    if archetype == "arc":
        shape = (
            (floor, floor + 0.15),
            (floor + 0.15, peak - 0.1),
            (peak - 0.05, peak),
            (peak * 0.55, peak * 0.7),
            (peak - 0.1, peak),
            (peak * 0.6, floor + 0.05),
        )
        return shape[:part_count]
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
    pc_lo, pc_hi = spec.part_count_range
    part_count = pc_lo + round(chaos * (pc_hi - pc_lo))
    envelope = _intensity_envelope(spec.intensity_archetype, part_count, energy_norm)
    return FormatBlueprint(
        part_count=part_count,
        bars_per_part=spec.bars_per_part_range,
        intensity_envelope=envelope,
        loop=spec.loop_only,
    )


# ---------- voice activation: τ + motion shortlists --------------------

# Texture activation thresholds (τ_v) per palette voice. Below τ the
# voice is forced to ``rest``; at or above τ the voice's density-like
# knob ramps from 0 → 1 across the remaining texture range (slope =
# 1 - τ_v so every voice reaches full density at texture=1.0).
_VOICE_TAU: dict[str, float] = {
    "drumkit": 0.00,
    "bass": 0.00,
    "stabs": 0.05,
    "lead": 0.20,
    "arp": 0.30,
    "sub": 0.40,
    "pad": 0.50,
    "chord": 0.60,
    "fx": 0.70,
}

# Algorithm choice per (voice, motion-band). Index 0 = low motion,
# 1 = mid, 2 = high. ``rest`` lives outside this table — picked by the
# texture-activation check.
_VOICE_MOTION_SHORTLISTS: dict[str, tuple[str, str, str]] = {
    "drumkit": ("drum_kit", "drum_kit", "drum_kit"),
    "bass": ("reese_bass", "acid_bass", "acid_bass"),
    "sub": ("sub_drone", "sub_drone", "sub_drone"),
    "lead": ("motif_phrase", "melodic_line", "melodic_line"),
    "pad": ("sustained_chord", "sustained_chord", "sustained_chord"),
    "chord": ("sustained_chord", "chord_stab", "chord_stab"),
    "arp": ("arp", "arp", "arp"),
    "stabs": ("chord_stab", "chord_stab", "chord_stab"),
    "fx": ("step_cc", "step_cc", "noise_riser"),
}

# Motion biases τ by ±0.075 for voices that have a clear "movement
# preference". High motion → animated voices (arp, lead) activate
# sooner; low motion → sustained voices (pad, sub) activate sooner.
_TAU_BIAS_DIRECTION: dict[str, int] = {
    "arp": -1,
    "lead": -1,
    "pad": +1,
    "sub": +1,
}
_TAU_BIAS_MAGNITUDE = 0.15


def _effective_tau(voice: str, motion: float) -> float:
    """τ_v after motion bias."""
    base = _VOICE_TAU[voice]
    direction = _TAU_BIAS_DIRECTION.get(voice, 0)
    if direction == 0:
        return base
    # motion - 0.5 maps to [-0.5, +0.5]; bias is ±_TAU_BIAS_MAGNITUDE / 2.
    bias = direction * (motion - 0.5) * _TAU_BIAS_MAGNITUDE
    return _clamp(base + bias, 0.0, 1.0)


def _motion_band(motion: float) -> int:
    """Bucket motion into 0 (low) / 1 (mid) / 2 (high)."""
    if motion < 0.34:
        return 0
    if motion < 0.67:
        return 1
    return 2


def _pick_voice(
    voice: str,
    energy_norm: float,
    valence_norm: float,
    texture: float,
    motion: float,
    chaos: float,
) -> tuple[str, float]:
    """Return ``(algorithm, density_norm)`` for *voice*.

    ``density_norm`` is in ``[0, 1]`` — 0 = barely on, 1 = full
    density. It's 0.0 when the voice is ``rest`` (below threshold).
    """
    tau_eff = _effective_tau(voice, motion)
    if texture < tau_eff:
        return "rest", 0.0

    # Slope = 1 - τ_v (the original, pre-bias τ) so each voice reaches
    # density=1.0 at texture=1.0 regardless of motion bias.
    slope = max(1e-6, 1.0 - _VOICE_TAU[voice])
    density_norm = _clamp((texture - tau_eff) / slope, 0.0, 1.0)

    shortlist = _VOICE_MOTION_SHORTLISTS[voice]
    algo = shortlist[_motion_band(motion)]

    # Valence bias on bass: dark valence prefers reese (woolly), bright
    # valence prefers acid. Motion shortlist still wins at high motion.
    if voice == "bass" and _motion_band(motion) >= 1 and valence_norm < 0.35:
        algo = "reese_bass"

    # Chaos can promote arp into the lead slot.
    if voice == "lead" and chaos > 0.55 and _motion_band(motion) >= 1:
        algo = "arp"

    return algo, density_norm


# ---------- per-(voice, algorithm) knob ranges -------------------------


def _density_blend(
    base_lo: float, base_hi: float, density: float
) -> tuple[float, float]:
    """Scale ``(base_lo, base_hi)`` window by *density* in ``[0, 1]``.

    At density=0 the window collapses toward base_lo; at density=1 it
    sits at the full ``(base_lo, base_hi)``.
    """
    span = base_hi - base_lo
    return (base_lo, _clamp(base_lo + span * density, base_lo, base_hi))


def _voice_pattern_ranges(
    voice: str,
    algorithm: str,
    density_norm: float,
    energy_norm: float,
    valence_norm: float,
    motion: float,
    chaos: float,
) -> tuple[
    dict[str, tuple[float, float]],
    dict[str, tuple[int, int]],
    dict[str, object],
]:
    """Per-(voice, algorithm) knob ranges + fixed knobs.

    Density (texture above τ) scales the "active-ness" of each voice;
    motion shapes the rhythmic / animated character (arp subdivision,
    bass cycle for psy rolling bass, chord stab pulses).
    """
    floats: dict[str, tuple[float, float]] = {}
    ints: dict[str, tuple[int, int]] = {}
    fixed: dict[str, object] = {}

    if algorithm == "rest":
        return floats, ints, fixed

    if algorithm == "drum_kit":
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
        # Drum density tracks texture-density directly.
        floats["density"] = _density_blend(0.4, 0.85, density_norm)
        floats["variation"] = (0.15 + chaos * 0.2, 0.3 + chaos * 0.3)
        floats["perc_complexity"] = (0.2 + chaos * 0.15, 0.4 + chaos * 0.35)
        return floats, ints, fixed

    if algorithm == "acid_bass":
        # Density inversely drives drop_prob (more density = fewer drops).
        max_drop = 0.55 - density_norm * 0.4
        min_drop = max(0.05, max_drop - 0.2)
        floats["drop_prob"] = (min_drop, max_drop + chaos * 0.1)
        floats["slide_prob"] = (0.1 + motion * 0.1, 0.45 + chaos * 0.2)
        floats["gate"] = (0.4, 0.9)
        floats["intensity"] = (0.9, 1.2 + chaos * 0.2)
        ints["base_vel"] = (85, 105)
        ints["resonance"] = (
            70 + int(energy_norm * 30),
            110 + int(chaos * 17),
        )
        # Psy rolling: high energy + high motion bumps LFO cycle so the
        # filter rolls instead of settling.
        if energy_norm > 0.65 and motion > 0.65:
            ints["cycle"] = (3, 6)
        return floats, ints, fixed

    if algorithm == "reese_bass":
        floats["wobble_depth"] = (
            0.3 + motion * 0.2,
            0.6 + motion * 0.3,
        )
        floats["detune_depth"] = (0.2, 0.5 + chaos * 0.3)
        ints["base_vel"] = (90, 110)
        return floats, ints, fixed

    if algorithm == "sub_drone":
        floats["fifth_prob"] = _density_blend(0.0, 0.4, density_norm)
        ints["bars_per_chord"] = (2, 4)
        return floats, ints, fixed

    if algorithm == "melodic_line":
        max_drop = 0.7 - density_norm * 0.25
        min_drop = max(0.2, max_drop - 0.25)
        floats["drop_prob"] = (min_drop, max_drop + chaos * 0.1)
        floats["passing_prob"] = (
            0.05 + motion * 0.1,
            0.2 + chaos * 0.2 + motion * 0.15,
        )
        floats["intensity"] = (0.9, 1.2)
        return floats, ints, fixed

    if algorithm == "motif_phrase":
        floats["motif_complexity"] = (
            0.3 + energy_norm * 0.2,
            0.6 + energy_norm * 0.2,
        )
        floats["variation_depth"] = (0.3, 0.6 + chaos * 0.3)
        floats["density"] = _density_blend(0.4, 0.85, density_norm)
        return floats, ints, fixed

    if algorithm == "arp":
        floats["gate"] = _density_blend(0.4, 0.8, density_norm)
        # Motion drives subdivision rate.
        subdivision = ("8", "16", "16t")[_motion_band(motion)]
        fixed["subdivision"] = subdivision
        # High density opens up a second octave.
        if density_norm > 0.55:
            ints["octaves"] = (1, 2)
        else:
            ints["octaves"] = (1, 1)
        ints["base_vel"] = (85, 105)
        return floats, ints, fixed

    if algorithm == "sustained_chord":
        floats["gate"] = (0.85, 0.98)
        floats["drift_prob"] = _density_blend(0.0, 0.4 + chaos * 0.2, density_norm)
        ints["base_vel"] = (65, 90)
        return floats, ints, fixed

    if algorithm == "chord_stab":
        # Density bumps pulses (more hits per bar at high texture).
        max_pulses = 3 + int(round(density_norm * 4))
        ints["pulses"] = (3, max(3, max_pulses))
        # Motion punches the stab — shorter gate at high motion.
        gate_hi = 0.5 - motion * 0.15
        floats["gate"] = (max(0.15, gate_hi - 0.2), max(0.2, gate_hi))
        floats["drop_prob"] = (0.0, 0.15 + chaos * 0.15)
        ints["offset"] = (1, 3)
        ints["base_vel"] = (80, 100)
        return floats, ints, fixed

    if algorithm == "step_cc":
        # Used as an FX voice here; motion drives sweep depth.
        floats["depth"] = (
            0.3 + motion * 0.5,
            0.5 + motion * 0.45,
        )
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


def build_recipe(
    mood: MoodSpec,
    fmt: FormatType,
    chaos: float,
    texture: float = 0.5,
    motion: float = 0.5,
) -> Recipe:
    """Collapse (mood, format, chaos, texture, motion) into a :class:`Recipe`.

    The recipe carries ranges, not concrete values — :func:`compose`
    is the consumer that samples from them with a seeded RNG. Pure
    function: same inputs always return the same Recipe.

    ``texture`` and ``motion`` are clamped to ``[0, 1]``. Defaults of
    0.5 give a "centre" arrangement — most voices on at mid density,
    mid-motion algorithms, mid filter sweep.
    """
    chaos = _clamp(chaos, 0.0, 1.0)
    texture = _clamp(texture, 0.0, 1.0)
    motion = _clamp(motion, 0.0, 1.0)
    energy_norm = _norm_axis(mood.energy)
    valence_norm = _norm_axis(mood.valence)

    mood_bp = _mood_blueprint(mood, chaos, texture, motion)
    fmt_bp = _format_blueprint(fmt, energy_norm, chaos)

    voices: dict[str, VoiceRecipe] = {}
    for voice in FIXED_PALETTE:
        algorithm, density_norm = _pick_voice(
            voice, energy_norm, valence_norm, texture, motion, chaos
        )
        floats, ints, fixed = _voice_pattern_ranges(
            voice,
            algorithm,
            density_norm,
            energy_norm,
            valence_norm,
            motion,
            chaos,
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
