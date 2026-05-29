"""LFO sampling + per-bar application.

A song-level LFO is a named time-varying source (see :mod:`jtx.model.lfo`);
applications bind it to a target inside a part. This module provides the
*runtime* side: a sampler that gives the LFO's value at a given bar
position, a target parser, and an applier that either mutates per-voice
``BarContext`` knobs (for ``pattern:`` / ``mix:`` / ``global_feel:`` /
``root:`` targets), emits MIDI ``ControlChange`` events (for ``midi:``
targets), or emits abstract :class:`Param` events into a named voice's
stream (for ``voice:`` targets — routed through the voice's
``parameter_map`` downstream).

Sampling is deterministic from the per-bar seed for ``random`` LFOs;
for the other shapes it's a pure function of the bar position. Both
properties are required by :mod:`jtx.seed`'s reproducibility contract.

Target string grammar (see ``docs/SPEC.md`` §LFOs):

* ``pattern:<voice>:<knob>`` — overwrite a pattern knob value in that
  voice's BarContext. The applier writes the unit-range LFO value;
  algorithms cast/scale as needed.
* ``mix:<voice>:<knob>`` — same but in the per-voice mix knob dict
  (sidechain / fade / evolution). Replaces the old ``feel:`` target
  prefix that was removed in schema v3.
* ``global_feel:<knob>`` — overwrite a value in the song-wide feel
  dict (``pump`` / ``groove`` / ``drive`` / ``tension`` / ``wander``).
  Broadcasts to every voice's ``BarContext.song_feel`` since they
  share the same backing dict.
* ``voice:<voice>:<function>`` — emit :class:`Param` events into the
  named voice's stream tagged with ``function`` (``"cutoff"`` /
  ``"resonance"`` / ``"bend"`` / …). The parameter_router resolves
  the function via ``slot.parameter_map`` / algorithm
  ``DEFAULT_PARAM_MAP`` — so a single LFO config drives the right
  CC / OSC destination regardless of voice routing. Sub-bar
  sampled per ``lfo.samples_per_bar``.
* ``midi:ch<N>:cc<M>`` — emit a CC event on channel N, controller M,
  at value ``int(lfo_value * 127)``. Sub-bar sampled per
  ``lfo.samples_per_bar``.
* ``root:<voice>`` — set ``chord_root_semitones`` on that voice's
  BarContext, scaled into ``[-depth, depth]`` semitones (so a depth-1
  LFO swings root ±1 semitone). Use sparingly — for any non-trivial
  root automation, the :class:`RootProvider` (issue #16) is the right
  surface.

Knob-writing targets (``pattern:`` / ``mix:`` / ``global_feel:`` /
``root:``) always sample once per bar at tick 0; sub-bar sampling on
them would just overwrite the dict between algorithm reads with no
effect.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Literal

from jtx.engine.context import BarContext
from jtx.engine.events import ControlChange, Event
from jtx.model.events import Param
from jtx.model.lfo import LFO, LFOApplication

TargetKind = Literal["pattern", "mix", "global_feel", "voice", "midi", "root"]


@dataclass(frozen=True)
class ParsedTarget:
    """Decoded form of an :class:`LFOApplication.target` string."""

    kind: TargetKind
    voice: str | None = None  # for pattern / mix / voice / root
    knob: str | None = None  # for pattern / mix / global_feel / voice
    midi_channel: int | None = None  # for midi
    midi_cc: int | None = None  # for midi


@dataclass
class LFOEmissions:
    """Return value of :func:`apply_lfos_to_bar`.

    Split into two channels because ``midi:`` targets emit standalone
    bar-level events (no voice routing) while ``voice:`` targets emit
    :class:`Param` events into a specific voice's stream — they need
    to ride that voice's voicing → parameter_router pipeline.
    """

    events: list[Event] = field(default_factory=list)
    """``midi:`` target events. Prepended/appended directly to bar output."""

    voice_params: dict[str, list[Param]] = field(default_factory=dict)
    """``voice:`` target emissions, keyed by voice name. Merged into
    each voice's algorithm output before the voicing stage."""


_MIDI_RE = re.compile(r"^ch(?P<ch>\d+):cc(?P<cc>\d+)$")


def parse_target(target: str) -> ParsedTarget:
    """Parse a target string. Raises ``ValueError`` on unrecognised forms."""
    if target.startswith("pattern:"):
        _, voice, knob = target.split(":", 2)
        return ParsedTarget(kind="pattern", voice=voice, knob=knob)
    if target.startswith("mix:"):
        _, voice, knob = target.split(":", 2)
        return ParsedTarget(kind="mix", voice=voice, knob=knob)
    if target.startswith("global_feel:"):
        knob = target[len("global_feel:") :]
        if not knob:
            raise ValueError(
                f"LFO target {target!r}: expected 'global_feel:<knob>' "
                f"(pump / groove / drive / tension / wander)"
            )
        return ParsedTarget(kind="global_feel", knob=knob)
    if target.startswith("voice:"):
        parts = target.split(":", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            raise ValueError(
                f"LFO target {target!r}: expected 'voice:<voice>:<function>'"
            )
        return ParsedTarget(kind="voice", voice=parts[1], knob=parts[2])
    if target.startswith("feel:"):
        raise ValueError(
            f"LFO target {target!r}: 'feel:' targets were removed in schema v3 — "
            f"use 'global_feel:<knob>' for the song-wide feel knobs or "
            f"'mix:<voice>:<knob>' for per-voice mix-pass knobs"
        )
    if target.startswith("midi:"):
        m = _MIDI_RE.match(target[len("midi:") :])
        if not m:
            raise ValueError(f"LFO target {target!r}: expected 'midi:ch<N>:cc<M>'")
        return ParsedTarget(
            kind="midi",
            midi_channel=int(m["ch"]),
            midi_cc=int(m["cc"]),
        )
    if target.startswith("root:"):
        return ParsedTarget(kind="root", voice=target[len("root:") :])
    raise ValueError(
        f"LFO target {target!r}: expected pattern:.. / mix:.. / global_feel:.. / "
        f"voice:.. / midi:.. / root:.."
    )


def sample_lfo(
    lfo: LFO,
    bar_index: int,
    tick_in_bar: int,
    ticks_per_bar: int,
    rng: random.Random | None = None,
) -> float:
    """Return the LFO value in ``[0, 1]`` at bar position ``bar_index +
    tick_in_bar/ticks_per_bar``.

    For the ``random`` LFO shape, *rng* must be supplied; the same
    ``(bar_index, tick_in_bar)`` must map to the same random number
    across runs, so callers seed the RNG from
    :func:`jtx.seed.derive_bar_seed` upstream.
    """
    within_bar = tick_in_bar / ticks_per_bar
    absolute = (bar_index + within_bar) / lfo.period_bars + lfo.phase
    phase = absolute - math.floor(absolute)
    raw = _wave_sample(lfo.shape, phase, rng)
    # Apply depth around 0.5 centre. depth=1 → full [0,1] swing;
    # depth=0.5 → [0.25, 0.75].
    return max(0.0, min(1.0, 0.5 + (raw - 0.5) * lfo.depth))


def _wave_sample(shape: str, phase: float, rng: random.Random | None) -> float:
    if shape == "sine":
        return (math.sin(2 * math.pi * phase) + 1.0) / 2.0
    if shape == "tri":
        return 1.0 - 2.0 * abs(phase - 0.5)
    if shape == "saw":
        return phase
    if shape == "ramp":
        # Synonym for saw — distinct from "saw" in some traditions but
        # we treat them identically for v1.
        return phase
    if shape == "square":
        return 1.0 if phase < 0.5 else 0.0
    if shape in ("random", "sh"):
        # sh = sample-and-hold; for a per-bar sampler that's identical
        # to plain random (one sample per evaluation).
        return (rng or random.Random()).random()
    raise ValueError(
        f"LFO shape {shape!r}: expected sine | tri | saw | ramp | square | random | sh"
    )


def applications_for_part(
    lfos: list[LFO], part_name: str
) -> list[tuple[LFO, LFOApplication, ParsedTarget]]:
    """Collect every LFO×application×parsed-target tuple active in *part_name*."""
    out: list[tuple[LFO, LFOApplication, ParsedTarget]] = []
    for lfo in lfos:
        for app in lfo.applications:
            if app.part != part_name:
                continue
            out.append((lfo, app, parse_target(app.target)))
    return out


def apply_lfos_to_bar(
    lfos: list[LFO],
    part_name: str,
    voice_contexts: dict[str, BarContext],
    bar_index: int,
    ticks_per_bar: int,
    rng: random.Random,
) -> LFOEmissions:
    """Apply per-bar LFO sampling and return any emitted events.

    Knob-writing targets (``pattern:`` / ``mix:`` / ``global_feel:`` /
    ``root:``) sample once at tick 0 and mutate the relevant BarContext
    dict in place — callers construct contexts first, then pass them
    through this function before handing them to algorithms'
    ``generate_bar``.

    Event-emitting targets (``midi:`` / ``voice:``) sample
    ``lfo.samples_per_bar`` times across the bar so the receiving CC
    sweeps smoothly. ``midi:`` events go into
    :attr:`LFOEmissions.events`; ``voice:`` events go into
    :attr:`LFOEmissions.voice_params` keyed by voice name (the
    SongPlayer merges them into the voice's algorithm output before
    the voicing stage).
    """
    out = LFOEmissions()
    for lfo, _app, target in applications_for_part(lfos, part_name):
        if target.kind in ("midi", "voice"):
            _apply_event_target(
                lfo, target, bar_index, ticks_per_bar, rng, out
            )
            continue
        # Knob-writing / root targets — one sample at tick 0.
        value = sample_lfo(lfo, bar_index, 0, ticks_per_bar, rng)
        if target.kind == "pattern":
            ctx = voice_contexts.get(target.voice or "")
            if ctx is not None and target.knob is not None:
                ctx.pattern_knobs[target.knob] = value
        elif target.kind == "mix":
            ctx = voice_contexts.get(target.voice or "")
            if ctx is not None and target.knob is not None:
                ctx.mix_knobs[target.knob] = value
        elif target.kind == "global_feel":
            if target.knob is not None:
                for ctx in voice_contexts.values():
                    ctx.song_feel[target.knob] = value
                    break  # shared dict; one mutation reaches all voices
        elif target.kind == "root":
            ctx = voice_contexts.get(target.voice or "")
            if ctx is not None:
                ctx.chord_root_semitones = int(round((value - 0.5) * 2 * lfo.depth))
    return out


def _apply_event_target(
    lfo: LFO,
    target: ParsedTarget,
    bar_index: int,
    ticks_per_bar: int,
    rng: random.Random,
    out: LFOEmissions,
) -> None:
    """Emit one event per sub-bar sample for event-emitting LFO targets."""
    samples = max(1, lfo.samples_per_bar)
    # Anchor samples to a coarse grid so the very-first sample lands on
    # tick 0 and the last sample lands strictly before ticks_per_bar.
    sample_stride = max(1, ticks_per_bar // samples)
    for i in range(samples):
        tick = i * sample_stride
        value = sample_lfo(lfo, bar_index, tick, ticks_per_bar, rng)
        if target.kind == "midi":
            assert target.midi_channel is not None and target.midi_cc is not None
            out.events.append(
                ControlChange(
                    tick=tick,
                    channel=target.midi_channel,
                    cc=target.midi_cc,
                    value=int(round(value * 127)),
                )
            )
        elif target.kind == "voice":
            assert target.voice is not None and target.knob is not None
            out.voice_params.setdefault(target.voice, []).append(
                Param(name=target.knob, value=value, tick=tick)
            )
