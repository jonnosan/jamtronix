"""Mix pass — fade-in/out envelopes + sidechain ducking.

Runs at the :class:`jtx.player.SongPlayer` level *after* algorithms
have generated their events and *before* the per-voice feel pass.
Sees every voice's current-bar events plus the previous bar's events
(cached by the SongPlayer) so cross-voice sidechain ducking can look
back across the bar boundary.

Knobs live in each voice's ``feel`` dict because they shape *how*
notes are emitted, not *what* notes:

**Fade envelope** (ADSR-flavoured):

* ``fade_in_at_bar`` (None) — bar within the part at which the
  fade-in ramp begins. ``None`` = no fade-in (voice plays at full
  velocity from bar 0).
* ``fade_in_beats`` (0) — duration of the fade-in ramp, in quarter
  notes. ``0`` with a non-None ``fade_in_at_bar`` = instant on.
* ``fade_out_at_bar`` (None) — bar within the part at which the
  fade-out ramp begins. ``None`` = no fade-out.
* ``fade_out_beats`` (0) — duration of the fade-out ramp.
* ``fade_sustain_level`` (1.0) — velocity multiplier once the
  fade-in has completed. Drop below 1.0 to keep the voice
  permanently quieter than its raw velocity.
* ``fade_shape`` (``"linear"`` | ``"exp"``) — shape of the ramp.
  Linear is the default; exp uses a quadratic curve (slow start,
  fast finish) for a more "fader-feel" sweep.
* ``fade_min_velocity`` (5) — if the post-fade velocity falls below
  this, drop the NoteOn (and its matching NoteOff) entirely. Avoids
  emitting near-silent notes that some synths still trigger audibly.

**Sidechain ducking**:

* ``sidechain_from`` (None | str | list[str]) — name(s) of the voice(s)
  whose NoteOns trigger ducking. None = no sidechain.
* ``sidechain_floor`` (60) — target velocity when fully ducked. The
  voice's velocity interpolates linearly between its raw value and
  this floor based on how recent the trigger was.
* ``sidechain_release_beats`` (1.0) — how long the duck takes to
  recover, in quarter notes.

Multiple sources are unioned (strongest duck wins). Triggers from the
previous bar carry over: a kick on tick 1840 of bar N still ducks the
first events of bar N+1 if the release window extends that far.

**Evolution** (slow velocity ramp across the *part*):

* ``evolution_start`` (1.0) — velocity multiplier at bar 0 of the part.
* ``evolution_end`` (1.0) — velocity multiplier at the last bar of
  the part. Linear interpolation in between.

Used to bake "this voice builds intensity across the section" into a
single voice config without needing explicit fade boundaries. Defaults
to a no-op (1.0 → 1.0). Applied after the fade pass.
"""

from __future__ import annotations

from typing import Any

from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend
from jtx.model.song import KnobDict

# Beats per quarter note — fixed. The "beat" unit in fade/sidechain
# knobs is the quarter note regardless of meter (so fade_in_beats=8
# means 8 quarter notes = 2 bars in 4/4, but ~2.28 bars in 7/8).
# This matches how a producer counts fade-in time on a mixer.


def apply_mix_pass(
    voice_events: dict[str, list[Event]],
    prev_voice_events: dict[str, list[Event]],
    feel_knobs_by_voice: dict[str, KnobDict],
    bar_index: int,
    ticks_per_bar: int,
    ppq: int,
    part_bars: int = 1,
) -> dict[str, list[Event]]:
    """Apply sidechain ducking + fade envelope + evolution ramp.

    Returns a fresh dict; input collections are not mutated. The order
    of voices in the returned dict matches *voice_events*.

    ``part_bars`` is the total bar count of the active part; used by
    the evolution ramp to compute progress (0..1) across the part.
    """
    out: dict[str, list[Event]] = {}
    for voice_name, events in voice_events.items():
        knobs = feel_knobs_by_voice.get(voice_name, {})
        ducked = _apply_sidechain(
            events, knobs, voice_events, prev_voice_events, ticks_per_bar, ppq
        )
        faded = _apply_fade(ducked, knobs, bar_index, ticks_per_bar, ppq)
        evolved = _apply_evolution(faded, knobs, bar_index, part_bars)
        out[voice_name] = evolved
    return out


# ---------------------------------------------------------- sidechain


def _apply_sidechain(
    events: list[Event],
    knobs: KnobDict,
    all_curr: dict[str, list[Event]],
    all_prev: dict[str, list[Event]],
    ticks_per_bar: int,
    ppq: int,
) -> list[Event]:
    raw_sources = knobs.get("sidechain_from")
    if not raw_sources:
        return events
    sources: list[str]
    if isinstance(raw_sources, str):
        sources = [raw_sources]
    elif isinstance(raw_sources, list):
        sources = [str(s) for s in raw_sources]
    else:
        return events

    floor = int(knobs.get("sidechain_floor", 60))
    release_beats = float(knobs.get("sidechain_release_beats", 1.0))
    release_ticks = max(1, int(release_beats * ppq))

    triggers: list[int] = []
    for src in sources:
        for ev in all_curr.get(src, []):
            if isinstance(ev, NoteOn):
                triggers.append(ev.tick)
        # Previous-bar triggers translate to negative tick (they fired
        # before bar 0 of the current bar).
        for ev in all_prev.get(src, []):
            if isinstance(ev, NoteOn):
                triggers.append(ev.tick - ticks_per_bar)
    triggers.sort()
    if not triggers:
        return events

    out: list[Event] = []
    for ev in events:
        if not isinstance(ev, NoteOn):
            out.append(ev)
            continue
        # Strongest duck among triggers that fall within
        # (ev.tick - release_ticks, ev.tick].
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
        out.append(NoteOn(tick=ev.tick, channel=ev.channel, note=ev.note, velocity=new_vel))
    return out


# --------------------------------------------------------------- fade


def _apply_fade(
    events: list[Event],
    knobs: KnobDict,
    bar_index: int,
    ticks_per_bar: int,
    ppq: int,
) -> list[Event]:
    fade_in_at_bar = knobs.get("fade_in_at_bar")
    fade_in_beats = float(knobs.get("fade_in_beats", 0))
    fade_out_at_bar = knobs.get("fade_out_at_bar")
    fade_out_beats = float(knobs.get("fade_out_beats", 0))
    sustain = float(knobs.get("fade_sustain_level", 1.0))
    shape = str(knobs.get("fade_shape", "linear"))
    min_vel = int(knobs.get("fade_min_velocity", 5))

    # Fast path: if neither fade is configured, the multiplier is the
    # sustain level for every tick — usually 1.0 (= no-op).
    if fade_in_at_bar is None and fade_out_at_bar is None and sustain == 1.0:
        return events

    # Cache fade decision per (tick within bar) — typically dozens of
    # NoteOns per bar but only a handful of distinct ticks.
    dropped_keys: set[tuple[int, int]] = set()  # (channel, note) of dropped NoteOns
    out: list[Event] = []
    for ev in events:
        if isinstance(ev, NoteOn):
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
                dropped_keys.add((ev.channel, ev.note))
                continue
            new_vel = max(1, min(127, int(round(new_vel_f))))
            out.append(NoteOn(tick=ev.tick, channel=ev.channel, note=ev.note, velocity=new_vel))
        elif isinstance(ev, NoteOff):
            key = (ev.channel, ev.note)
            if key in dropped_keys:
                # Pair one dropped NoteOff with the dropped NoteOn.
                # Multiple NoteOns of the same (ch, note) within the
                # bar are rare; for the common case the first NoteOff
                # is the matching one. Remove the key so subsequent
                # NoteOffs for the same pitch pass through.
                dropped_keys.discard(key)
                continue
            out.append(ev)
        elif isinstance(ev, ControlChange | PitchBend):
            # CC + pitchwheel always pass through — the fade only
            # affects pitched events. Modulators (filter sweeps,
            # portamento toggles) should still reach the synth even
            # during a fade-in so the timbre is set correctly when
            # the first audible note arrives.
            out.append(ev)
        else:  # pragma: no cover - exhaustive over Event union
            out.append(ev)
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
    """Return the velocity multiplier (0..sustain) for a given beat position
    inside the part.

    Curve:
        [0 .. fade_in_at_bar*beats):                 0
        [fade_in_at_bar*beats .. +fade_in_beats):    0 → sustain   (ramp)
        [.. fade_out_at_bar*beats):                  sustain
        [fade_out_at_bar*beats .. +fade_out_beats):  sustain → 0   (ramp)
        [.. ∞):                                       0
    """
    fade_in_start = None if fade_in_at_bar is None else fade_in_at_bar * beats_per_bar
    fade_out_start = None if fade_out_at_bar is None else fade_out_at_bar * beats_per_bar

    # Pre-fade-in silence.
    if fade_in_start is not None and beat_position < fade_in_start:
        return 0.0

    # During fade-out ramp / after fade-out finishes.
    if fade_out_start is not None and beat_position >= fade_out_start:
        if beat_position >= fade_out_start + fade_out_beats:
            return 0.0
        progress = (beat_position - fade_out_start) / max(fade_out_beats, 1e-9)
        return sustain * (1.0 - _ramp(progress, shape))

    # During fade-in ramp.
    if fade_in_start is not None and beat_position < fade_in_start + fade_in_beats:
        progress = (beat_position - fade_in_start) / max(fade_in_beats, 1e-9)
        return sustain * _ramp(progress, shape)

    # Sustain plateau (no fade configured or between fade-in and fade-out).
    return sustain


def _apply_evolution(
    events: list[Event],
    knobs: KnobDict,
    bar_index: int,
    part_bars: int,
) -> list[Event]:
    """Linear velocity ramp from ``evolution_start`` (at bar 0) to
    ``evolution_end`` (at the last bar of the part).

    Defaults to (1.0, 1.0) which is a no-op. NoteOn velocities are
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

    out: list[Event] = []
    for ev in events:
        if isinstance(ev, NoteOn):
            new_vel = max(1, min(127, int(round(ev.velocity * scale))))
            out.append(NoteOn(tick=ev.tick, channel=ev.channel, note=ev.note, velocity=new_vel))
        else:
            out.append(ev)
    return out


def _ramp(progress: float, shape: str) -> float:
    """Apply the configured ramp shape to a 0..1 progress value."""
    progress = max(0.0, min(1.0, progress))
    if shape == "exp":
        # Quadratic ease-in (slow start, fast finish) — a producer's
        # "mixer fader feel". Inverse for fade-out is handled by
        # 1-_ramp at the call site.
        return progress * progress
    return progress  # linear default
