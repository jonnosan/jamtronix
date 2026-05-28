"""``noise_riser`` — long crescendo voice for transitions / build-ups.

Every dance track needs the swelling riser into the drop. ``noise_riser``
emits a held note retriggered each bar inside a *riser window* with:

* CC74 cutoff ramping from ``cutoff_start`` → ``cutoff_end``;
* per-bar NoteOn velocity ramping from ``vel_start`` → ``vel_end``;
* optional pitch-bend rise sweeping from 0 → ``pitch_rise_cents`` over
  the riser window.

The note is retriggered at every bar boundary so the receiving patch
re-gates its amp envelope. CC74 + pitch-bend ramps run as ~16 samples
per bar so the receiving filter / pitch moves smoothly.

Bar-by-bar regen contract: ``noise_riser`` decides whether the current
``ctx.bar_index`` is inside a riser window based on the trigger mode.
Outside the window: emits nothing.

Knobs:

* ``trigger`` — when the riser fires.
  * ``"once"`` — fires bars 0..``duration_bars``-1 of the part once.
  * ``"every"`` — fires the last ``duration_bars`` of every
    ``cycle_bars`` (default 16). Use for repeated build-ups.
  * ``"last_bar_of_4"`` / ``"last_bar_of_8"`` / ``"last_bar_of_16"`` —
    fires only the single specified bar; ``duration_bars`` is forced
    to 1 in those modes.
* ``duration_bars`` (4) — riser window length in bars (``"once"`` /
  ``"every"`` only).
* ``cycle_bars`` (16) — repeat period for ``"every"`` trigger.
* ``base_note`` (``"A4"``) — pitch of the held note.
* ``cutoff_start`` (30), ``cutoff_end`` (120) — CC74 ramp endpoints.
* ``vel_start`` (40), ``vel_end`` (120) — per-bar velocity ramp.
* ``pitch_rise_cents`` (0) — total pitch-bend rise across the riser
  window. 0 = no pitch movement; 1200 ≈ one octave (synth-pitchbend-
  range dependent).
* ``curve`` (``"exp"``) — shape of the rise. ``"linear"`` / ``"exp"``
  (slow start, fast finish — the conventional "build" feel) /
  ``"s_curve"`` (slow start, slow finish, fast middle).
* ``samples_per_bar`` (16) — CC density inside the bar.

The cutoff CC routing is now handled by the voice slot's
``parameter_map`` (function ``"cutoff"``) rather than a per-knob
``cutoff_cc`` override.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._theory import note_to_midi
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note, Param
from jtx.model.parameter_target import CCTarget, ParameterTarget

_CURVES = ("linear", "exp", "s_curve")
_TRIGGERS = ("once", "every", "last_bar_of_4", "last_bar_of_8", "last_bar_of_16")


class NoiseRiser(Algorithm):
    """Crescendo voice — retriggers + cutoff ramp + optional pitch rise.

    MIDI-naive: emits :class:`Note` for the held tone and :class:`Param`
    for the cutoff sweep / bend rise.
    """

    name: ClassVar[str] = "noise_riser"
    DEFAULT_PARAM_MAP: ClassVar[dict[str, ParameterTarget]] = {
        "cutoff": CCTarget(74),
    }

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs

        trigger = str(knobs.get("trigger", "every"))
        duration_bars = max(1, int(knobs.get("duration_bars", 4)))
        cycle_bars = max(1, int(knobs.get("cycle_bars", 16)))

        in_riser, position = _riser_position(trigger, ctx.bar_index, duration_bars, cycle_bars)
        if not in_riser:
            return []

        base_note = str(knobs.get("base_note", "A4"))
        cutoff_start = _clamp_cc(int(knobs.get("cutoff_start", 30)))
        cutoff_end = _clamp_cc(int(knobs.get("cutoff_end", 120)))
        vel_start = _clamp_vel(int(knobs.get("vel_start", 40)))
        vel_end = _clamp_vel(int(knobs.get("vel_end", 120)))
        pitch_rise_cents = int(knobs.get("pitch_rise_cents", 0))
        curve = str(knobs.get("curve", "exp"))
        samples_per_bar = max(2, int(knobs.get("samples_per_bar", 16)))

        if curve not in _CURVES:
            raise ValueError(f"noise_riser: unknown curve {curve!r} (expected one of {_CURVES})")

        pitch = _resolve_base_note(base_note)

        # Position spans 0..1 across the riser window. ``position`` is
        # the fraction at the START of this bar; bar_progress(fraction)
        # below maps a within-bar fraction to the full-window progress.
        bar_span = 1.0 / max(1, duration_bars)

        def progress_at(frac_in_bar: float) -> float:
            return min(1.0, max(0.0, position + frac_in_bar * bar_span))

        # Per-bar NoteOn velocity uses progress at this bar's START.
        bar_vel = vel_start + (vel_end - vel_start) * _shape(curve, position)
        velocity = _clamp_vel(int(round(bar_vel)))

        held_duration = max(1, ctx.ticks_per_bar - 1)
        events: list[AbstractEvent] = [
            Note(pitch=pitch, velocity=velocity, duration_ticks=held_duration, tick=0)
        ]

        sample_ticks = max(1, ctx.ticks_per_bar // samples_per_bar)
        for i in range(samples_per_bar):
            tick = i * sample_ticks
            frac = i / samples_per_bar
            prog = _shape(curve, progress_at(frac))
            cutoff = int(round(cutoff_start + (cutoff_end - cutoff_start) * prog))
            events.append(Param(name="cutoff", value=_clamp_cc(cutoff) / 127.0, tick=tick))
            if pitch_rise_cents > 0:
                # Assume ±2 semitones (±200 cents) on the synth's bend.
                # Normalised to ±1 — voicing maps to the 14-bit PitchBend
                # range (1.0 → 8191).
                bend_cents = pitch_rise_cents * prog
                bend_norm = max(-1.0, min(1.0, bend_cents / 200.0))
                events.append(Param(name="bend", value=bend_norm, tick=tick))

        return events


def _riser_position(
    trigger: str, bar_index: int, duration_bars: int, cycle_bars: int
) -> tuple[bool, float]:
    """Return ``(in_riser, progress_at_bar_start)``.

    ``progress_at_bar_start`` is the riser-window fraction (0..1) at the
    start of this bar; only meaningful when ``in_riser`` is true.
    """
    if trigger == "once":
        if 0 <= bar_index < duration_bars:
            return True, bar_index / duration_bars
        return False, 0.0
    if trigger == "every":
        if cycle_bars <= 0:
            return False, 0.0
        position_in_cycle = bar_index % cycle_bars
        riser_start = cycle_bars - duration_bars
        if position_in_cycle >= riser_start:
            return True, (position_in_cycle - riser_start) / duration_bars
        return False, 0.0
    if trigger == "last_bar_of_4":
        return (bar_index % 4 == 3, 0.0)
    if trigger == "last_bar_of_8":
        return (bar_index % 8 == 7, 0.0)
    if trigger == "last_bar_of_16":
        return (bar_index % 16 == 15, 0.0)
    raise ValueError(f"noise_riser: unknown trigger {trigger!r} (expected one of {_TRIGGERS})")


def _shape(curve: str, x: float) -> float:
    """Map ``x`` ∈ [0,1] through *curve* to a [0,1] crescendo shape."""
    x = max(0.0, min(1.0, x))
    if curve == "linear":
        return x
    if curve == "exp":
        # exp shape: slow start, fast finish.
        return x * x
    if curve == "s_curve":
        # Sigmoid-ish: smoothstep.
        return x * x * (3 - 2 * x)
    raise ValueError(f"noise_riser: unknown curve {curve!r}")


def _resolve_base_note(spec: str) -> int:
    """Parse "A4", "C#3", "Bb2" → MIDI note number."""
    if not spec:
        return 69
    # Last char is the octave digit (or sign+digit), rest is the note.
    for split_idx in range(len(spec) - 1, -1, -1):
        if spec[split_idx].isdigit() or spec[split_idx] == "-":
            try:
                octave = int(spec[split_idx:])
                tonic = spec[:split_idx]
                return note_to_midi(tonic, octave)
            except (ValueError, KeyError):
                continue
    raise ValueError(f"noise_riser: cannot parse base_note {spec!r}")


def _clamp_cc(v: int) -> int:
    return max(0, min(127, v))


def _clamp_vel(v: int) -> int:
    return max(1, min(127, v))
