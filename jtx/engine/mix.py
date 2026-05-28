"""Mix pass — fade-in/out envelopes + sidechain ducking.

Schema v3: operates on **abstract events** (``Hit`` / ``Note`` /
``Param`` / ``PolyAftertouch``) emitted by algorithms — before the
voicing stage translates them to MIDI. Sidechain matches by
``Hit.instrument`` directly; fade + evolution scale the
``.velocity`` field on both Hit and Note.

Knobs live in each voice's ``mix`` dict because they shape *how*
notes are emitted, not *what* notes:

**Fade envelope** (ADSR-flavoured):

* ``fade_in_at_bar`` (None) — bar within the part at which the
  fade-in ramp begins. ``None`` = no fade-in.
* ``fade_in_beats`` (0) — duration of the fade-in ramp, in quarter
  notes. ``0`` with a non-None ``fade_in_at_bar`` = instant on.
* ``fade_out_at_bar`` (None) / ``fade_out_beats`` (0) — same for
  fade-out.
* ``fade_sustain_level`` (1.0) — velocity multiplier once the
  fade-in has completed.
* ``fade_shape`` (``"linear"`` | ``"exp"``) — shape of the ramp.
* ``fade_min_velocity`` (5) — if the post-fade velocity falls below
  this, drop the event entirely.

**Sidechain ducking**:

* ``sidechain_from`` (None | str | list[str]) — **instrument name(s)**
  whose Hit events trigger ducking. A Hit with ``.instrument``
  matching any source acts as a trigger — works uniformly for a
  stand-alone ``kick`` voice (whose Hits all carry
  ``instrument="kick"`` via the SongPlayer ``instrument_name``
  thread) or a ``kick`` piece inside a ``drum_kit``.
* ``sidechain_floor`` (60) — target velocity when fully ducked.
* ``sidechain_release_beats`` (1.0) — how long the duck takes to
  recover, in quarter notes.

Multiple sources are unioned (strongest duck wins). Triggers from
the previous bar carry over via negative-tick anchoring.

**Evolution** (slow velocity ramp across the *part*):

* ``evolution_start`` (1.0) / ``evolution_end`` (1.0) — velocity
  multiplier at bar 0 / last bar of the part. Linear interpolation
  in between.
"""

from __future__ import annotations

from typing import Any

from jtx.model.events import AbstractEvent, Hit, Note
from jtx.model.song import KnobDict


def apply_mix_pass(
    voice_events: dict[str, list[AbstractEvent]],
    prev_voice_events: dict[str, list[AbstractEvent]],
    mix_knobs_by_voice: dict[str, KnobDict],
    bar_index: int,
    ticks_per_bar: int,
    ppq: int,
    part_bars: int = 1,
) -> dict[str, list[AbstractEvent]]:
    """Apply sidechain ducking + fade envelope + evolution ramp.

    Returns a fresh dict; input collections are not mutated. The order
    of voices in the returned dict matches *voice_events*.

    ``part_bars`` is the total bar count of the active part; used by
    the evolution ramp to compute progress (0..1) across the part.

    ``mix_knobs_by_voice`` is the per-voice mix-pass knob dict
    (sidechain / fade / evolution). Schema v3 — global feel knobs
    live on the song-level :attr:`jtx.model.song.Song.feel`.
    """
    out: dict[str, list[AbstractEvent]] = {}
    for voice_name, events in voice_events.items():
        knobs = mix_knobs_by_voice.get(voice_name, {})
        ducked = _apply_sidechain(
            events, knobs, voice_events, prev_voice_events, ticks_per_bar, ppq
        )
        faded = _apply_fade(ducked, knobs, bar_index, ticks_per_bar, ppq)
        evolved = _apply_evolution(faded, knobs, bar_index, part_bars)
        out[voice_name] = evolved
    return out


# ---------------------------------------------------------- sidechain


def _apply_sidechain(
    events: list[AbstractEvent],
    knobs: KnobDict,
    all_curr: dict[str, list[AbstractEvent]],
    all_prev: dict[str, list[AbstractEvent]],
    ticks_per_bar: int,
    ppq: int,
) -> list[AbstractEvent]:
    raw_sources = knobs.get("sidechain_from")
    if not raw_sources:
        return events
    sources: set[str]
    if isinstance(raw_sources, str):
        sources = {raw_sources}
    elif isinstance(raw_sources, list):
        sources = {str(s) for s in raw_sources}
    else:
        return events

    floor = int(knobs.get("sidechain_floor", 60))
    release_beats = float(knobs.get("sidechain_release_beats", 1.0))
    release_ticks = max(1, int(release_beats * ppq))

    triggers: list[int] = []
    for voice_events in all_curr.values():
        for ev in voice_events:
            if isinstance(ev, Hit) and ev.instrument in sources:
                triggers.append(ev.tick)
    # Previous-bar triggers translate to negative tick (they fired
    # before bar 0 of the current bar).
    for voice_events in all_prev.values():
        for ev in voice_events:
            if isinstance(ev, Hit) and ev.instrument in sources:
                triggers.append(ev.tick - ticks_per_bar)
    triggers.sort()
    if not triggers:
        return events

    out: list[AbstractEvent] = []
    for ev in events:
        if not isinstance(ev, Hit | Note):
            out.append(ev)
            continue
        best_duck = 0.0
        for t in triggers:
            if t > ev.tick:
                break
            distance = ev.tick - t
            if distance < release_ticks:
                duck = 1.0 - (distance / release_ticks)
                if duck > best_duck:
                    best_duck = duck
        if best_duck <= 0:
            out.append(ev)
            continue
        new_vel = int(round(ev.velocity * (1 - best_duck) + floor * best_duck))
        new_vel = max(1, min(127, new_vel))
        out.append(_with_velocity(ev, new_vel))
    return out


def _with_velocity(ev: Hit | Note, velocity: int) -> Hit | Note:
    """Return a copy of *ev* with ``velocity`` swapped in. Hit/Note are
    frozen dataclasses, so we rebuild rather than mutate."""
    if isinstance(ev, Hit):
        return Hit(
            instrument=ev.instrument,
            velocity=velocity,
            duration_ticks=ev.duration_ticks,
            tick=ev.tick,
        )
    return Note(
        pitch=ev.pitch,
        velocity=velocity,
        duration_ticks=ev.duration_ticks,
        tick=ev.tick,
    )


# --------------------------------------------------------------- fade


def _apply_fade(
    events: list[AbstractEvent],
    knobs: KnobDict,
    bar_index: int,
    ticks_per_bar: int,
    ppq: int,
) -> list[AbstractEvent]:
    fade_in_at_bar = knobs.get("fade_in_at_bar")
    fade_in_beats = float(knobs.get("fade_in_beats", 0))
    fade_out_at_bar = knobs.get("fade_out_at_bar")
    fade_out_beats = float(knobs.get("fade_out_beats", 0))
    sustain = float(knobs.get("fade_sustain_level", 1.0))
    shape = str(knobs.get("fade_shape", "linear"))
    min_vel = int(knobs.get("fade_min_velocity", 5))

    if fade_in_at_bar is None and fade_out_at_bar is None and sustain == 1.0:
        return events

    out: list[AbstractEvent] = []
    for ev in events:
        if not isinstance(ev, Hit | Note):
            out.append(ev)
            continue
        beat_position = bar_index * (ticks_per_bar / ppq) + ev.tick / ppq
        scale = _fade_scale_at_beat(
            beat_position,
            fade_in_at_bar=_as_optional_int(fade_in_at_bar),
            fade_in_beats=fade_in_beats,
            fade_out_at_bar=_as_optional_int(fade_out_at_bar),
            fade_out_beats=fade_out_beats,
            sustain=sustain,
            shape=shape,
            beats_per_bar=ticks_per_bar / ppq,
        )
        new_vel_f = ev.velocity * scale
        if new_vel_f < min_vel:
            continue  # drop event entirely
        new_vel = max(1, min(127, int(round(new_vel_f))))
        out.append(_with_velocity(ev, new_vel))
    return out


def _as_optional_int(v: Any) -> int | None:
    if v is None:
        return None
    return int(v)


def _fade_scale_at_beat(
    beat_position: float,
    *,
    fade_in_at_bar: int | None,
    fade_in_beats: float,
    fade_out_at_bar: int | None,
    fade_out_beats: float,
    sustain: float,
    shape: str,
    beats_per_bar: float,
) -> float:
    """Return the velocity multiplier (0..sustain) for a given beat position.

    Curve:
        [0 .. fade_in_at_bar*beats):                 0
        [fade_in_at_bar*beats .. +fade_in_beats):    0 → sustain   (ramp)
        [.. fade_out_at_bar*beats):                  sustain
        [fade_out_at_bar*beats .. +fade_out_beats):  sustain → 0   (ramp)
        [.. ∞):                                       0
    """
    fade_in_start = None if fade_in_at_bar is None else fade_in_at_bar * beats_per_bar
    fade_out_start = None if fade_out_at_bar is None else fade_out_at_bar * beats_per_bar

    if fade_in_start is not None and beat_position < fade_in_start:
        return 0.0

    if fade_out_start is not None and beat_position >= fade_out_start:
        if beat_position >= fade_out_start + fade_out_beats:
            return 0.0
        progress = (beat_position - fade_out_start) / max(fade_out_beats, 1e-9)
        return sustain * (1.0 - _ramp(progress, shape))

    if fade_in_start is not None and beat_position < fade_in_start + fade_in_beats:
        progress = (beat_position - fade_in_start) / max(fade_in_beats, 1e-9)
        return sustain * _ramp(progress, shape)

    return sustain


def _apply_evolution(
    events: list[AbstractEvent],
    knobs: KnobDict,
    bar_index: int,
    part_bars: int,
) -> list[AbstractEvent]:
    """Linear velocity ramp from ``evolution_start`` (at bar 0) to
    ``evolution_end`` (at the last bar of the part).

    Defaults to (1.0, 1.0) which is a no-op. Hit + Note velocities are
    scaled; other events pass through. Velocities clamp to 1..127.
    """
    start = float(knobs.get("evolution_start", 1.0))
    end = float(knobs.get("evolution_end", 1.0))
    if start == 1.0 and end == 1.0:
        return events

    if part_bars <= 1:
        progress = 1.0
    else:
        progress = bar_index / (part_bars - 1)
    progress = max(0.0, min(1.0, progress))
    scale = start + (end - start) * progress
    if scale == 1.0:
        return events

    out: list[AbstractEvent] = []
    for ev in events:
        if isinstance(ev, Hit | Note):
            new_vel = max(1, min(127, int(round(ev.velocity * scale))))
            out.append(_with_velocity(ev, new_vel))
        else:
            out.append(ev)
    return out


def _ramp(progress: float, shape: str) -> float:
    """Apply the configured ramp shape to a 0..1 progress value."""
    progress = max(0.0, min(1.0, progress))
    if shape == "exp":
        return progress * progress
    return progress  # linear default
