"""Post-emit feel pass — global feel knobs → per-event shaping.

Schema v3: operates on **abstract events** (``Hit`` / ``Note`` /
``Param`` / ``PolyAftertouch``). Translates four of the five song-wide
:class:`Song.feel` knobs into bar-internal event shaping; the voicing
stage converts the result to MIDI downstream.

* **Groove** — swing, humanize, accent (beats 2 & 4).
  - Swing only fires on events that "should swing" — Hit events whose
    ``instrument`` is a hat name (``chh``/``hh``/``ohh``/``hat``/…),
    or Note events on lead / stab / chord voices. Kicks, snares,
    bass don't swing.
  - Humanize applies universally — small per-event tick jitter.
  - Accent boosts Hit/Note velocity on the 16th-note steps that fall
    on beats 2 & 4 (steps 4 + 12 in 4/4).

* **Drive** — global +N velocity boost on every Hit + Note, plus a
  "cutoff push" that shifts every ``Param(name="cutoff")`` upward.
  At ``drive=1.0`` cutoff values get +0.2 in their normalised [0, 1]
  range (clamped at 1.0). Pairs with the velocity boost for the
  classic "push the mix harder" feel: louder + brighter at the same
  time. The drum_kit algorithm separately reads
  ``song_feel["drive"]`` to add ghost notes / roll-fill probability —
  that's pattern-shaping, this is post-emit shaping.

* **Wander** — per-bar mute probability + per-Note octave-jump
  probability. Octave jump only fires on melodic voices
  (lead / bass / pad / stab / chord) — shifting a kick by ±12 is
  musically silly. Hits don't carry pitch and never octave-jump.

* **Pump** — NOT handled here. Pump compiles to mix-pass sidechain
  knobs in :mod:`jtx.engine.global_feel`.

* **Tension** — NOT handled here. Reshapes the part-intensity
  envelope directly in :class:`jtx.player.SongPlayer`.

The bar RNG (seeded by :func:`jtx.seed.derive_bar_seed`) drives every
random draw so playback is reproducible across runs.
"""

from __future__ import annotations

import random
from dataclasses import replace

from jtx.algorithms._steps import step_ticks
from jtx.model.events import AbstractEvent, Hit, Note, Param, PolyAftertouch
from jtx.model.setup import VoiceSlot

# How song-feel knobs (0..1) scale into low-level shaping amounts.
GROOVE_HUMANIZE_TICKS = 8  # ±ticks at groove=1.0
GROOVE_ACCENT_VELOCITY = 14  # vel boost on beats 2/4 at groove=1.0
DRIVE_VELOCITY_BOOST = 15  # global vel boost at drive=1.0
DRIVE_CUTOFF_PUSH = 0.2  # added to every Param(name="cutoff").value at drive=1.0
WANDER_MUTE_PROB = 0.1  # chance to drop the whole bar at wander=1.0
WANDER_OCTAVE_PROB = 0.15  # chance per Note at wander=1.0

# Param function names that Drive's cutoff-push targets. ``"cutoff"``
# is the v1 vocab; algorithms use it for filter cutoff regardless of
# the concrete CC / OSC / MPE target. Extend cautiously — anything
# in here gets bias-shifted on every event, which is musical for a
# filter sweep but probably wrong for, e.g., glide or detune.
_DRIVE_PUSH_FUNCTIONS = frozenset({"cutoff"})

# 16th-note positions of beats 2 + 4 in 4/4 (the classic backbeat accents).
_BACKBEAT_STEPS = frozenset({4, 12})

# Hat-like piece names that swing under Groove.
_HAT_INSTRUMENT_NAMES = frozenset(
    {"chh", "hh", "ohh", "hat", "shaker", "tick", "tambo"}
)

# Voice roles whose pitched Notes swing under Groove.
_SWUNG_NOTE_ROLES = frozenset({"lead", "stab", "chord"})

# Voice roles eligible for Wander's octave-jump per-Note shift.
# Drum / drum_kit voices skip — jumping a kick ±12 is musical garbage.
_MELODIC_ROLES = frozenset({"bass", "lead", "pad", "stab", "chord"})


def apply_feel(
    events: list[AbstractEvent],
    song_feel: dict[str, float],
    voice_slot: VoiceSlot,
    ppq: int,
    rng: random.Random,
) -> list[AbstractEvent]:
    """Return a new event list with global feel knobs applied.

    Tick fields are bar-relative on the way in and on the way out;
    swing/humanize may push events slightly negative — they're clamped
    at 0 before return.
    """
    groove = max(0.0, min(1.0, float(song_feel.get("groove", 0.0))))
    drive = max(0.0, min(1.0, float(song_feel.get("drive", 0.0))))
    wander = max(0.0, min(1.0, float(song_feel.get("wander", 0.0))))

    # Per-bar mute roll — drops every event in the bar if it fires.
    mute_prob = wander * WANDER_MUTE_PROB
    if mute_prob > 0 and rng.random() < mute_prob:
        return []

    humanize = int(round(groove * GROOVE_HUMANIZE_TICKS))
    accent_boost = int(round(groove * GROOVE_ACCENT_VELOCITY))
    drive_boost = int(round(drive * DRIVE_VELOCITY_BOOST))
    octave_prob = wander * WANDER_OCTAVE_PROB

    s_ticks = step_ticks(ppq)
    # swing=1.0 → odd-16th lands at 2/3 of the containing 8th, i.e.
    # max shift = s_ticks/3.
    swing_offset = int(round(s_ticks * groove / 3.0))

    swing_predicate = _build_swing_predicate(voice_slot)
    octave_eligible = voice_slot.default_role in _MELODIC_ROLES

    out: list[AbstractEvent] = []
    for ev in events:
        if isinstance(ev, Hit):
            out.append(
                _shape_hit(
                    ev,
                    rng=rng,
                    humanize=humanize,
                    swing_offset=swing_offset,
                    s_ticks=s_ticks,
                    swing_predicate=swing_predicate,
                    accent_boost=accent_boost,
                    drive_boost=drive_boost,
                )
            )
        elif isinstance(ev, Note):
            out.append(
                _shape_note(
                    ev,
                    rng=rng,
                    humanize=humanize,
                    swing_offset=swing_offset,
                    s_ticks=s_ticks,
                    swing_predicate=swing_predicate,
                    accent_boost=accent_boost,
                    drive_boost=drive_boost,
                    octave_prob=octave_prob if octave_eligible else 0.0,
                )
            )
        elif isinstance(ev, Param):
            new_tick = ev.tick
            if humanize > 0:
                new_tick = max(0, new_tick + rng.randint(-humanize, humanize))
            new_value = ev.value
            if drive > 0 and ev.name in _DRIVE_PUSH_FUNCTIONS:
                # Bias the cutoff sweep upward by drive * 0.2; clamp at
                # 1.0 so an already-fully-open cutoff stays open rather
                # than saturating past the normalised range.
                new_value = min(1.0, ev.value + drive * DRIVE_CUTOFF_PUSH)
            out.append(replace(ev, tick=new_tick, value=new_value))
        elif isinstance(ev, PolyAftertouch):
            # Tick humanize only — no velocity or pitch concept.
            new_tick = ev.tick
            if humanize > 0:
                new_tick = max(0, new_tick + rng.randint(-humanize, humanize))
            out.append(replace(ev, tick=new_tick))
        else:  # pragma: no cover — exhaustive over AbstractEvent
            out.append(ev)
    return out


def _shape_hit(
    ev: Hit,
    *,
    rng: random.Random,
    humanize: int,
    swing_offset: int,
    s_ticks: int,
    swing_predicate,
    accent_boost: int,
    drive_boost: int,
) -> Hit:
    new_tick = ev.tick
    if humanize > 0:
        new_tick += rng.randint(-humanize, humanize)
    if swing_offset != 0 and s_ticks > 0 and swing_predicate(ev):
        step = ev.tick // s_ticks
        if step % 2 == 1:
            new_tick += swing_offset
    new_tick = max(0, new_tick)

    new_vel = ev.velocity
    if accent_boost > 0 and s_ticks > 0 and (ev.tick // s_ticks) in _BACKBEAT_STEPS:
        new_vel += accent_boost
    if drive_boost > 0:
        new_vel += drive_boost
    new_vel = max(1, min(127, new_vel))

    return Hit(
        instrument=ev.instrument,
        velocity=new_vel,
        duration_ticks=ev.duration_ticks,
        tick=new_tick,
    )


def _shape_note(
    ev: Note,
    *,
    rng: random.Random,
    humanize: int,
    swing_offset: int,
    s_ticks: int,
    swing_predicate,
    accent_boost: int,
    drive_boost: int,
    octave_prob: float,
) -> Note:
    new_tick = ev.tick
    if humanize > 0:
        new_tick += rng.randint(-humanize, humanize)
    if swing_offset != 0 and s_ticks > 0 and swing_predicate(ev):
        step = ev.tick // s_ticks
        if step % 2 == 1:
            new_tick += swing_offset
    new_tick = max(0, new_tick)

    new_vel = ev.velocity
    if accent_boost > 0 and s_ticks > 0 and (ev.tick // s_ticks) in _BACKBEAT_STEPS:
        new_vel += accent_boost
    if drive_boost > 0:
        new_vel += drive_boost
    new_vel = max(1, min(127, new_vel))

    new_pitch = ev.pitch
    if octave_prob > 0 and rng.random() < octave_prob:
        jump = 12 if rng.random() < 0.5 else -12
        shifted = ev.pitch + jump
        if 0 <= shifted <= 127:
            new_pitch = shifted

    return Note(
        pitch=new_pitch,
        velocity=new_vel,
        duration_ticks=ev.duration_ticks,
        tick=new_tick,
    )


def _build_swing_predicate(voice_slot: VoiceSlot):
    """Return a predicate ``(AbstractEvent) -> bool`` selecting events that swing.

    Under the abstract-event protocol the slot's structure is largely
    irrelevant — Hits carry their instrument name directly, and Notes
    rely on the voice's role. The slot is only consulted for the role.
    """
    role = voice_slot.default_role
    voice_type = voice_slot.type
    if voice_type in ("drum", "drum_kit"):
        # Drum-typed voices swing only on hat-instrument Hits.
        return lambda ev: (
            isinstance(ev, Hit) and ev.instrument in _HAT_INSTRUMENT_NAMES
        )
    if role in _SWUNG_NOTE_ROLES:
        # Melodic / pad voices that swing — every Note.
        return lambda ev: isinstance(ev, Note)
    return lambda ev: False
