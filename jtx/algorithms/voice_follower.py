"""``voice_follower`` — fixed-pipeline derivation of another voice.

The follower listens to one *source* voice (named in the song-level
voice config) and runs the source's events through a fixed pipeline:

::

    source → latch → pattern_transform → transpose → chord → quantize_to_scale → ratchet → output

Each step is purely knob-driven, in this order. To get a different
ordering, *chain* followers: follower B can take follower A as its
source. Cycles are detected at song load (see :mod:`jtx.model.validate`).

The engine glue layer (later milestone) is responsible for setting
``ctx.source_events`` to the source voice's bar events. For algorithm
unit tests we construct ``BarContext`` with ``source_events`` directly.

Knobs:

* ``source`` — name of the source voice (validation-only here; the
  glue layer reads it).
* ``latch`` — ``all`` (default) / ``first_per_bar`` /
  ``every_nth=N`` (use ``every_nth`` int knob) / ``accent_only``
  (use ``accent_threshold`` int knob, default 100).
* ``every_nth`` — N for ``every_nth`` latch (default 2).
* ``accent_threshold`` — velocity threshold for ``accent_only`` (100).
* ``transform`` — ``none`` (default) / ``invert`` / ``retrograde`` /
  ``thin`` (drop fraction ``thin_prob``).
* ``thin_prob`` — drop probability for ``thin`` transform (0.5).
* ``invert_axis`` — pitch axis to mirror around for ``invert`` (60).
* ``transpose_semitones`` (0) — added to every output pitch.
* ``transpose_octaves`` (0) — added to every output pitch ×12.
* ``chord`` — list of semitone offsets; default ``[0]`` (no chord).
  Setting ``[0, 4, 7]`` plays a major triad off every incoming note;
  ``[0, 3, 7]`` minor; ``[0, 5]`` power chord.
* ``quantize`` — ``off`` (default) / ``nearest`` / ``up`` / ``down``.
* ``quantize_scale`` — override scale; default = ``ctx.key.scale``.
* ``ratchet`` (1) — base number of evenly-spaced retriggers per output
  note. Setting ``ratchet=3`` turns each output note into an
  8th-note triplet (or 16th-triplet on shorter notes) — the
  triplet-fill primitive.
* ``ratchet_curve`` (``"flat"``) — how the ratchet count varies across
  the bar. ``flat`` (every note uses base ``ratchet``); ``ramp_up``
  (ratchet grows linearly from 1 to base across the bar); ``last_beat``
  (notes inside beat 4 use base ratchet, earlier notes use 1);
  ``pulse`` (notes on the downbeat of each beat use base ratchet, all
  others use 1). Build triplet fills by setting ``ratchet=3`` +
  ``ratchet_curve="last_beat"``.
* ``shift_bars`` (0) — read the source from N bars in the past instead of
  the current bar. ``shift_bars=1`` produces a one-bar echo: bar N
  outputs whatever the source did in bar N-1. v1 supports values 0 and
  1 (the SongPlayer caches only the immediately previous bar); values
  >1 silently fall back to using whatever history is available
  (typically none, so the follower emits nothing).

The first bar of a part with ``shift_bars > 0`` is silent (no history
yet); subsequent bars echo. Under the CLI's ``--loop``, wraparound
after a full pass restores history so the loop is seamless.
"""

from __future__ import annotations

from typing import ClassVar

from jtx.algorithms._theory import note_to_midi, scale_intervals
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.model.events import AbstractEvent, Note
from jtx.model.song import KnobDict


class VoiceFollower(Algorithm):
    """Fixed-pipeline follower; reads ``ctx.source_events`` set by the glue.

    Schema v3: consumes the source voice's abstract event stream
    (pre-voicing) — :class:`Note` events come through with their
    pitch + duration intact, no NoteOn/NoteOff pairing needed.
    Emits abstract :class:`Note` events; the voicing stage adds the
    follower voice's channel downstream.
    """

    name: ClassVar[str] = "voice_follower"

    def __init__(self) -> None:
        pass

    def generate_bar(self, ctx: BarContext) -> list[AbstractEvent]:
        knobs = ctx.pattern_knobs
        rng = ctx.rng

        shift_bars = int(knobs.get("shift_bars", 0))
        if shift_bars < 0:
            raise ValueError(f"voice_follower: 'shift_bars' must be >= 0, got {shift_bars}")
        if shift_bars == 0:
            chosen_source = ctx.source_events
        elif shift_bars == 1:
            # One-bar echo: read from the cached previous-bar events.
            chosen_source = ctx.prev_source_events
        else:
            # v1 only caches one bar of history; deeper shifts return
            # nothing rather than silently using the wrong source.
            chosen_source = None

        if not chosen_source:
            return []

        notes = _pair_notes(chosen_source)
        notes = _latch(notes, knobs)
        notes = _pattern_transform(notes, knobs, ctx.ticks_per_bar, rng)
        notes = _transpose(notes, knobs)
        notes = _chord(notes, knobs)
        notes = _quantize(notes, knobs, ctx)
        notes = _ratchet(notes, knobs, ctx)

        events: list[AbstractEvent] = []
        for tick, pitch, velocity, duration in notes:
            pitch = max(0, min(127, pitch))
            events.append(
                Note(
                    pitch=pitch,
                    velocity=max(1, min(127, velocity)),
                    duration_ticks=max(1, duration),
                    tick=tick,
                )
            )
        return events


# A note in pipeline form: (tick, pitch, velocity, duration).
_Note = tuple[int, int, int, int]


def _pair_notes(events) -> list[_Note]:
    """Project abstract :class:`Note` events into (tick, pitch, vel, dur) tuples.

    Hit / Param / PolyAftertouch events are ignored — the follower's
    pipeline operates on pitched material only.
    """
    paired: list[_Note] = [
        (n.tick, n.pitch, n.velocity, max(1, n.duration_ticks))
        for n in events
        if isinstance(n, Note)
    ]
    paired.sort(key=lambda nt: nt[0])
    return paired


def _latch(notes: list[_Note], knobs: KnobDict) -> list[_Note]:
    mode = str(knobs.get("latch", "all"))
    if mode == "all":
        return notes
    if mode == "first_per_bar":
        return notes[:1]
    if mode == "every_nth":
        n = max(1, int(knobs.get("every_nth", 2)))
        return notes[::n]
    if mode == "accent_only":
        thr = int(knobs.get("accent_threshold", 100))
        return [n for n in notes if n[2] >= thr]
    raise ValueError(
        f"voice_follower: unknown latch {mode!r} "
        "(expected all | first_per_bar | every_nth | accent_only)"
    )


def _pattern_transform(
    notes: list[_Note],
    knobs: KnobDict,
    ticks_per_bar: int,
    rng: object,
) -> list[_Note]:
    import random as _random

    mode = str(knobs.get("transform", "none"))
    if mode == "none":
        return notes
    if mode == "invert":
        axis = int(knobs.get("invert_axis", 60))
        return [(t, axis * 2 - p, v, d) for t, p, v, d in notes]
    if mode == "retrograde":
        # Reverse order and flip ticks within the bar.
        return [(ticks_per_bar - t - d, p, v, d) for t, p, v, d in reversed(notes)]
    if mode == "thin":
        prob = float(knobs.get("thin_prob", 0.5))
        rng_random = rng if isinstance(rng, _random.Random) else _random.Random()
        return [n for n in notes if rng_random.random() >= prob]
    raise ValueError(
        f"voice_follower: unknown transform {mode!r} (expected none | invert | retrograde | thin)"
    )


def _transpose(notes: list[_Note], knobs: KnobDict) -> list[_Note]:
    semitones = int(knobs.get("transpose_semitones", 0))
    octaves = int(knobs.get("transpose_octaves", 0))
    shift = semitones + 12 * octaves
    if shift == 0:
        return notes
    return [(t, p + shift, v, d) for t, p, v, d in notes]


def _chord(notes: list[_Note], knobs: KnobDict) -> list[_Note]:
    from jtx.algorithms._chords import intervals_for

    quality = str(knobs.get("quality", "unison"))
    intervals = intervals_for(quality)
    if intervals == (0,):
        return notes
    chorded: list[_Note] = []
    for t, p, v, d in notes:
        for interval in intervals:
            chorded.append((t, p + interval, v, d))
    return chorded


def _quantize(notes: list[_Note], knobs: KnobDict, ctx: BarContext) -> list[_Note]:
    mode = str(knobs.get("quantize", "off"))
    if mode == "off":
        return notes
    scale_name = str(knobs.get("quantize_scale", ctx.key.scale))
    intervals = scale_intervals(scale_name)
    tonic_pc = note_to_midi(ctx.key.tonic, 0) % 12
    return [(t, _snap(p, tonic_pc, intervals, mode), v, d) for t, p, v, d in notes]


def _ratchet(notes: list[_Note], knobs: KnobDict, ctx: BarContext) -> list[_Note]:
    base_count = max(1, int(knobs.get("ratchet", 1)))
    curve = str(knobs.get("ratchet_curve", "flat"))
    if base_count == 1 and curve == "flat":
        return notes

    if curve not in _RATCHET_CURVES:
        raise ValueError(
            f"voice_follower: unknown ratchet_curve {curve!r} (expected one of {_RATCHET_CURVES})"
        )

    out: list[_Note] = []
    for t, p, v, d in notes:
        count = _ratchet_count_for(curve, base_count, t, ctx)
        if count <= 1:
            out.append((t, p, v, d))
            continue
        sub_dur = max(1, d // count)
        for i in range(count):
            out.append((t + i * sub_dur, p, v, max(1, sub_dur - 1)))
    return out


_RATCHET_CURVES = ("flat", "ramp_up", "last_beat", "pulse")


def _ratchet_count_for(curve: str, base_count: int, tick: int, ctx: BarContext) -> int:
    if curve == "flat":
        return base_count
    if curve == "ramp_up":
        progress = tick / max(1, ctx.ticks_per_bar - 1)
        return max(1, int(round(1 + (base_count - 1) * progress)))
    if curve == "last_beat":
        beats_per_bar = max(1, ctx.ticks_per_bar // ctx.ppq)
        last_beat_start = (beats_per_bar - 1) * ctx.ppq
        return base_count if tick >= last_beat_start else 1
    if curve == "pulse":
        return base_count if tick % ctx.ppq == 0 else 1
    raise ValueError(f"voice_follower: unknown ratchet_curve {curve!r}")


def _snap(pitch: int, tonic_pc: int, intervals: tuple[int, ...], mode: str) -> int:
    """Snap *pitch* to the nearest / next-up / next-down scale degree."""
    # Build the chromatic membership of the scale: a 12-tuple where
    # index i is True if pitch class i is in the scale.
    scale_pcs = {(tonic_pc + iv) % 12 for iv in intervals}

    if pitch % 12 in scale_pcs:
        return pitch

    if mode == "up":
        for delta in range(1, 13):
            if (pitch + delta) % 12 in scale_pcs:
                return pitch + delta
        return pitch
    if mode == "down":
        for delta in range(1, 13):
            if (pitch - delta) % 12 in scale_pcs:
                return pitch - delta
        return pitch
    if mode == "nearest":
        for delta in range(1, 7):
            if (pitch + delta) % 12 in scale_pcs:
                return pitch + delta
            if (pitch - delta) % 12 in scale_pcs:
                return pitch - delta
        return pitch
    raise ValueError(
        f"voice_follower: unknown quantize mode {mode!r} (expected off | nearest | up | down)"
    )
