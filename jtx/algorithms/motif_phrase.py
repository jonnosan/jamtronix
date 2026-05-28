"""``motif_phrase`` — A-A'-A-B lead with motif memory.

Generates a multi-bar phrase by combining:

* A **base motif** — a short pitch+rhythm cell drawn from a phrase-level
  RNG (``ctx.rng_hold(phrase_length_bars)``), so all bars within the
  phrase share the same motif content.
* A **phrase shape** — controls how each bar's slot maps to a slot label
  (A / A' / A'' / B). ``A_A_A_B``, ``A_B_A_B``, ``A_A'_A_A''`` etc.
* **Per-bar transforms** applied to A' / A'' / B slots, drawn from
  ``ctx.rng`` so transforms vary even between supposedly-identical
  A' bars (one of two intentional happy-accident knobs).

The output is clean MIDI: a downstream ``voice_follower`` can further
transform it. ``random_walk`` mode is an escape hatch — each bar is a
fresh motif from ``ctx.rng``, no phrase structure.

Knobs are documented in :mod:`jtx_gui.algorithm_meta` under
``_MOTIF_PHRASE``. The motif/contour libraries live in
:mod:`jtx.algorithms._rhythm_templates` / :mod:`jtx.algorithms._contours`.
Phrase mapping + slot transforms + progression live in
:mod:`jtx.algorithms._phrase_shapes`.
"""

from __future__ import annotations

import random
from typing import ClassVar

from jtx.algorithms._contours import apply_contour, pick_contour
from jtx.algorithms._palettes import palette_for
from jtx.algorithms._phrase_shapes import (
    ADOUBLE,
    APRIME,
    A,
    B,
    apply_transforms_ranked,
    choose_b_strategy,
    progression_offset_for,
    slot_label_for,
)
from jtx.algorithms._rhythm_templates import RhythmTemplate, min_position_spacing, pick_template
from jtx.algorithms._theory import note_to_midi, scale_intervals
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note

# (tick, scale_degree, base_velocity) — the internal pipeline note shape.
_Note = tuple[int, int, int]


class MotifPhrase(Algorithm):
    """Structured A-A'-A-B lead with cyclic motif memory."""

    name: ClassVar[str] = "motif_phrase"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        bar_rng = ctx.rng

        # Knob resolution.
        phrase_shape = str(knobs.get("phrase_shape", "A_A_A_B"))
        phrase_length_bars = max(1, int(knobs.get("phrase_length_bars", 4)))
        motif_length_beats = max(1, int(knobs.get("motif_length_beats", 1)))
        rhythm_template_name = str(knobs.get("rhythm_template", "auto"))
        motif_complexity = float(knobs.get("motif_complexity", 0.4))
        contour_name = str(knobs.get("contour", "auto"))
        palette_name = str(knobs.get("palette", "tones_only"))
        density = float(knobs.get("density", 0.7))
        variation_depth = float(knobs.get("variation_depth", 0.5))
        b_section_difference = float(knobs.get("b_section_difference", 0.7))
        progression_mode = str(knobs.get("progression_mode", "static"))
        progression_range = max(1, int(knobs.get("progression_range", 4)))
        octave_shift = int(knobs.get("octave", 0))
        gate = float(knobs.get("gate", 0.5))
        base_vel = int(knobs.get("base_vel", 95))
        intensity = float(knobs.get("intensity", 1.0))

        palette = palette_for(palette_name)

        # STEP 1: phrase coordinates.
        if phrase_shape == "random_walk":
            slot_label = A
            content_rng: random.Random = bar_rng
            progression_offset = 0
        else:
            slot_in_phrase = ctx.bar_index % phrase_length_bars
            slot_label = slot_label_for(phrase_shape, slot_in_phrase)
            content_rng = ctx.rng_hold(phrase_length_bars)
            progression_offset = progression_offset_for(
                progression_mode,
                slot_in_phrase,
                phrase_length_bars,
                progression_range,
                content_rng,
            )

        # STEP 2: base motif "A" (stable across all bars in the phrase).
        template = pick_template(rhythm_template_name, motif_complexity, content_rng)
        contour = pick_contour(contour_name, motif_complexity, content_rng)
        start_index = content_rng.randrange(len(palette)) if palette else 0
        base_motif = _build_motif(
            template=template,
            contour=contour,
            motif_length_beats=motif_length_beats,
            ppq=ctx.ppq,
            palette=palette,
            start_index=start_index,
            base_vel=base_vel,
            rng=content_rng,
        )

        # STEP 3: B-section substitution.
        motif: list[_Note]
        if slot_label == B and phrase_shape != "random_walk":
            b_rng = ctx.rng_hold(phrase_length_bars, salt="b")
            strategy = choose_b_strategy(b_section_difference, b_rng)
            if strategy.kind == "contour_swap":
                alt_contour = pick_contour(contour_name, motif_complexity, b_rng)
                alt_start = b_rng.randrange(len(palette)) if palette else 0
                motif = _build_motif(
                    template=template,
                    contour=alt_contour,
                    motif_length_beats=motif_length_beats,
                    ppq=ctx.ppq,
                    palette=palette,
                    start_index=alt_start,
                    base_vel=base_vel,
                    rng=b_rng,
                )
            elif strategy.kind == "tension_transpose":
                motif = [(t, deg + strategy.tension_degree, v) for t, deg, v in base_motif]
            else:  # "fresh"
                alt_template = pick_template(rhythm_template_name, motif_complexity, b_rng)
                alt_contour = pick_contour(contour_name, motif_complexity, b_rng)
                alt_start = b_rng.randrange(len(palette)) if palette else 0
                motif = _build_motif(
                    template=alt_template,
                    contour=alt_contour,
                    motif_length_beats=motif_length_beats,
                    ppq=ctx.ppq,
                    palette=palette,
                    start_index=alt_start,
                    base_vel=base_vel,
                    rng=b_rng,
                )
        else:
            motif = list(base_motif)

        # STEP 4: tile motif across the bar (truncate trailing partial).
        bar_pre = _tile_motif(motif, motif_length_beats, ctx.ppq, ctx.ticks_per_bar)

        # STEP 5: apply slot transforms (per-bar randomness via bar_rng).
        if phrase_shape != "random_walk":
            if slot_label == APRIME:
                bar_pre = apply_transforms_ranked(
                    bar_pre,
                    depth=variation_depth * 0.4,
                    bar_ticks=ctx.ticks_per_bar,
                    rng=bar_rng,
                )
            elif slot_label == ADOUBLE:
                bar_pre = apply_transforms_ranked(
                    bar_pre,
                    depth=variation_depth,
                    bar_ticks=ctx.ticks_per_bar,
                    rng=bar_rng,
                )

        # STEP 6: progression (scale-step transpose).
        if progression_offset != 0:
            bar_pre = [(t, deg + progression_offset, v) for t, deg, v in bar_pre]

        # STEP 7: density thinning (bar-fresh).
        if density < 1.0:
            bar_pre = [n for n in bar_pre if bar_rng.random() < density]

        # STEP 8: resolve to MIDI.
        scale = scale_intervals(ctx.key.scale)
        register_octave = 4 + octave_shift
        tonic_midi = note_to_midi(ctx.key.tonic, register_octave) + ctx.chord_root_semitones
        spacing = min_position_spacing(template, ctx.ppq)
        duration = max(1, int(spacing * gate * template.duration_mult))

        events: list[AbstractEvent] = []
        for tick, deg, vel_base in bar_pre:
            pitch = tonic_midi + _degree_to_semitones(deg, scale)
            pitch = max(0, min(127, pitch))
            vel = max(1, min(127, int(vel_base * intensity) + bar_rng.randint(-5, 5)))
            events.append(
                Note(pitch=pitch, velocity=vel, duration_ticks=duration, tick=tick)
            )
        events.sort(key=lambda e: e.tick)
        return events


def _build_motif(
    *,
    template: RhythmTemplate,
    contour: str,
    motif_length_beats: int,
    ppq: int,
    palette: tuple[int, ...] | list[int],
    start_index: int,
    base_vel: int,
    rng: random.Random,
) -> list[_Note]:
    """One motif cell — list of (tick, degree, base_velocity)."""
    # Build fire ticks: template.positions are fractions within one beat,
    # stacked across motif_length_beats. Result ticks span [0, motif_length_beats*ppq).
    ticks: list[int] = []
    for beat in range(motif_length_beats):
        beat_start = beat * ppq
        for frac in template.positions:
            ticks.append(beat_start + int(round(frac * ppq)))
    ticks.sort()
    degrees = apply_contour(contour, len(ticks), palette, start_index, rng)
    motif: list[_Note] = []
    for tick, deg in zip(ticks, degrees, strict=True):
        # Template-level accent boost (stand-in until feel layer integrates).
        motif.append((tick, deg, base_vel))
    return motif


def _tile_motif(
    motif: list[_Note],
    motif_length_beats: int,
    ppq: int,
    ticks_per_bar: int,
) -> list[_Note]:
    if not motif:
        return []
    cell_ticks = motif_length_beats * ppq
    if cell_ticks <= 0:
        return []
    out: list[_Note] = []
    repeats = (ticks_per_bar + cell_ticks - 1) // cell_ticks
    for r in range(repeats):
        cell_start = r * cell_ticks
        if cell_start >= ticks_per_bar:
            break
        for rel_tick, deg, vel in motif:
            tick = cell_start + rel_tick
            if tick >= ticks_per_bar:
                break
            out.append((tick, deg, vel))
    return out


def _degree_to_semitones(degree: int, scale: tuple[int, ...]) -> int:
    """Resolve a (possibly negative, possibly multi-octave) scale degree."""
    octaves, idx = divmod(degree, len(scale))
    return octaves * 12 + scale[idx]
