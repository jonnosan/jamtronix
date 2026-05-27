"""Phrase shape mapping + slot transforms + progression offsets.

``motif_phrase`` maps each bar's slot inside a phrase to a *slot label*
(``A`` / ``A'`` / ``A''`` / ``B``). For slots other than the plain ``A``,
``apply_transforms_ranked`` perturbs the motif using a ranked list of
musically-useful transforms; ``progression_offset_for`` shapes a
multi-bar scale-step climb / drop.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

PHRASE_SHAPE_CHOICES: tuple[str, ...] = (
    "A_A_A_A",
    "A_A_A_B",
    "A_A_B_A",
    "A_B_A_B",
    "A_A'_A_A''",
    "random_walk",
)

# Slot labels per pattern. Use unicode-free identifiers for readability.
A = "A"
APRIME = "Aprime"
ADOUBLE = "Adouble"
B = "B"

_PATTERNS: dict[str, tuple[str, ...]] = {
    "A_A_A_A": (A,),
    "A_A_A_B": (A, A, A, B),
    "A_A_B_A": (A, A, B, A),
    "A_B_A_B": (A, B),
    "A_A'_A_A''": (A, APRIME, A, ADOUBLE),
}


def slot_label_for(phrase_shape: str, slot_in_phrase: int) -> str:
    """Return the slot label for *slot_in_phrase* inside the named shape.

    Patterns cycle when ``phrase_length_bars`` exceeds the pattern length:
    e.g. ``A_A_A_B`` at ``phrase_length_bars=8`` repeats over two cycles.
    Unknown shapes fall through to ``A`` (treated as flat).
    """
    pattern = _PATTERNS.get(phrase_shape)
    if not pattern:
        return A
    return pattern[slot_in_phrase % len(pattern)]


# --- Note pipeline type ----------------------------------------------------

_Note = tuple[int, int, int]  # (tick, scale_degree, base_velocity)


# --- Transforms ranked best→worst for acid / deep techno / psytrance leads.
# Each transform takes (notes, ctx_meta, rng) and returns transformed notes.

_TENSION_DEGREES: tuple[int, ...] = (-1, 4, 6)
"""Distant scale-degree offsets for B-section "tension transpose"."""


def apply_transforms_ranked(
    notes: list[_Note],
    *,
    depth: float,
    bar_ticks: int,
    rng: random.Random,
) -> list[_Note]:
    """Apply up to ``ceil(depth * 6)`` ranked transforms in order.

    Ranking (best→worst for acid/psy/deep-techno):
    1. transpose ±1 scale-step  (deg ± 1)
    2. octave shift ±12         (deg ± 7 in 7-note scales)
    3. density change           (drop a fraction of notes)
    4. rhythmic displacement    (shift ticks by ±1/16 of a bar)
    5. retrograde               (reverse order + flip ticks)
    6. gate stretch             (modeled via tick clustering — light no-op for
                                 the post-resolve durations; we approximate
                                 by *removing* every second note instead, since
                                 the algorithm derives duration from spacing.
                                 This is a stand-in until per-note duration
                                 carries through the pipeline.)
    """
    if depth <= 0 or not notes:
        return notes
    count = max(1, int(round(depth * 6)))
    # Cap at the actual list length.
    count = min(count, len(_TRANSFORMS))
    out = list(notes)
    for i in range(count):
        out = _TRANSFORMS[i](out, depth=depth, bar_ticks=bar_ticks, rng=rng)
    return out


def _t_transpose_step(
    notes: list[_Note], *, depth: float, bar_ticks: int, rng: random.Random
) -> list[_Note]:
    # depth scales the step magnitude (1 at depth>=0.3, 2 above 0.7).
    magnitude = 1 if depth < 0.7 else 2
    direction = 1 if rng.random() < 0.5 else -1
    delta = direction * magnitude
    return [(t, deg + delta, v) for t, deg, v in notes]


def _t_octave_shift(
    notes: list[_Note], *, depth: float, bar_ticks: int, rng: random.Random
) -> list[_Note]:
    # In a 7-note scale, +7 scale-steps = one octave. Approximate.
    direction = 1 if rng.random() < 0.5 else -1
    return [(t, deg + direction * 7, v) for t, deg, v in notes]


def _t_density_change(
    notes: list[_Note], *, depth: float, bar_ticks: int, rng: random.Random
) -> list[_Note]:
    drop_prob = 0.15 + 0.35 * depth  # 0.15..0.50
    return [n for n in notes if rng.random() >= drop_prob]


def _t_rhythmic_displace(
    notes: list[_Note], *, depth: float, bar_ticks: int, rng: random.Random
) -> list[_Note]:
    shift = max(1, bar_ticks // 16)  # one 16th-note worth of ticks
    direction = 1 if rng.random() < 0.5 else -1
    delta = direction * shift
    return [(max(0, min(bar_ticks - 1, t + delta)), deg, v) for t, deg, v in notes]


def _t_retrograde(
    notes: list[_Note], *, depth: float, bar_ticks: int, rng: random.Random
) -> list[_Note]:
    if not notes:
        return notes
    sorted_notes = sorted(notes, key=lambda n: n[0])
    ticks = [n[0] for n in sorted_notes]
    span_start = ticks[0]
    span_end = ticks[-1]
    return [(span_end - (t - span_start), deg, v) for t, deg, v in sorted_notes]


def _t_gate_stretch(
    notes: list[_Note], *, depth: float, bar_ticks: int, rng: random.Random
) -> list[_Note]:
    # Approximation: thin pairs to give an "every other note" stretched feel.
    if len(notes) <= 2:
        return notes
    sorted_notes = sorted(notes, key=lambda n: n[0])
    return [n for i, n in enumerate(sorted_notes) if i % 2 == 0]


_TRANSFORMS = (
    _t_transpose_step,
    _t_octave_shift,
    _t_density_change,
    _t_rhythmic_displace,
    _t_retrograde,
    _t_gate_stretch,
)


# --- Progression -----------------------------------------------------------

PROGRESSION_MODES: tuple[str, ...] = (
    "static",
    "fifths",
    "fourths",
    "climb_up",
    "climb_down",
    "random_scale_step",
)


def progression_offset_for(
    mode: str,
    slot_in_phrase: int,
    phrase_length_bars: int,
    progression_range: int,
    rng: random.Random,
) -> int:
    """Return the scale-step offset for this slot under *mode*.

    For ``random_scale_step`` the RNG should be the phrase-level RNG so
    the offset is stable across the phrase — motif_phrase passes
    ``content_rng`` here.
    """
    if mode == "static" or phrase_length_bars <= 1:
        return 0
    if mode == "fifths":
        return 4 if slot_in_phrase >= phrase_length_bars // 2 else 0
    if mode == "fourths":
        return 3 if slot_in_phrase >= phrase_length_bars // 2 else 0
    if mode == "climb_up":
        steps_per_slot = max(1, progression_range // max(1, phrase_length_bars - 1))
        return min(progression_range, slot_in_phrase * steps_per_slot)
    if mode == "climb_down":
        steps_per_slot = max(1, progression_range // max(1, phrase_length_bars - 1))
        return -min(progression_range, slot_in_phrase * steps_per_slot)
    if mode == "random_scale_step":
        return rng.randint(-progression_range, progression_range)
    return 0


# --- B-section helpers -----------------------------------------------------


@dataclass(frozen=True)
class BSectionStrategy:
    """How motif_phrase produces the B-bar motif relative to A."""

    kind: str  # "contour_swap" | "tension_transpose" | "fresh"
    tension_degree: int = 0
    """For ``tension_transpose``: scale-step offset to apply to A."""


def choose_b_strategy(b_section_difference: float, rng: random.Random) -> BSectionStrategy:
    """Map ``b_section_difference`` to a concrete B-strategy."""
    if b_section_difference < 0.34:
        return BSectionStrategy(kind="contour_swap")
    if b_section_difference < 0.68:
        return BSectionStrategy(
            kind="tension_transpose",
            tension_degree=rng.choice(_TENSION_DEGREES),
        )
    return BSectionStrategy(kind="fresh")
