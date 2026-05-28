"""Post-emit feel pass — global feel knobs → per-event shaping.

Schema v3: the per-voice "feel" grab-bag (humanize / swing / accent /
mute_prob / octave_jump) is gone; algorithms see the song-wide
:class:`Song.feel` knobs (pump / groove / drive / tension / wander)
instead. This pass translates four of those into bar-internal MIDI
shaping:

* **Groove** — swing, humanize, accent (beats 2 & 4).
  - Swing only fires on events that "should swing" — hat-like pieces
    inside a drum_kit voice (``chh``/``hh``/``ohh``/``hat``/...), or
    every NoteOn on lead/stab/chord voices. Kicks, snares, bass don't
    swing.
  - Humanize applies universally — small per-event tick jitter.
  - Accent boosts NoteOn velocity on the 16th-note steps that fall on
    beats 2 & 4 (steps 4 + 12 in 4/4).

* **Drive** — global +N velocity boost on every NoteOn. The drum_kit
  algorithm already reads ``song_feel["drive"]`` separately to add
  ghost notes / roll-fill probability; that's pattern-shaping, this is
  velocity-shaping.

* **Wander** — per-bar mute probability + per-NoteOn octave-jump
  probability. Octave jump only fires on melodic voices (lead / bass /
  pad / stab / chord) — shifting a kick by ±12 is musically silly.

* **Pump** — NOT handled here. Pump compiles to mix-pass sidechain
  knobs in :mod:`jtx.engine.global_feel`. It's a velocity envelope
  driven by kick triggers, which the mix pass handles.

* **Tension** — NOT handled here. Tension reshapes the part-intensity
  envelope directly in :class:`jtx.player.SongPlayer`.

The bar RNG (seeded by :func:`jtx.seed.derive_bar_seed`) drives every
random draw so playback is reproducible across runs.
"""

from __future__ import annotations

import random

from jtx.algorithms._steps import step_ticks
from jtx.engine.events import (
    ChannelPressure,
    ControlChange,
    Event,
    NoteOff,
    NoteOn,
    PitchBend,
)
from jtx.model.setup import VoiceSlot

# How song-feel knobs (0..1) scale into low-level shaping amounts.
# Keep modest — feel is seasoning, not the main course.
GROOVE_HUMANIZE_TICKS = 8  # ±ticks at groove=1.0
GROOVE_ACCENT_VELOCITY = 14  # vel boost on beats 2/4 at groove=1.0
DRIVE_VELOCITY_BOOST = 15  # global vel boost at drive=1.0
WANDER_MUTE_PROB = 0.1  # chance to drop the whole bar at wander=1.0
WANDER_OCTAVE_PROB = 0.15  # chance per NoteOn at wander=1.0

# 16th-note positions of beats 2 + 4 in 4/4 (the classic backbeat accents).
_BACKBEAT_STEPS = frozenset({4, 12})

# Hat-like piece names inside a drum_kit voice — these swing under
# Groove. Other kit pieces (kick, snare, clap, perc, tom, ...) stay
# on the grid.
_HAT_INSTRUMENT_NAMES = frozenset(
    {"chh", "hh", "ohh", "hat", "shaker", "tick", "tambo"}
)

# Voice roles whose pitched Notes always swing under Groove.
_SWUNG_NOTE_ROLES = frozenset({"lead", "stab", "chord"})

# Voice roles eligible for Wander's octave-jump per-NoteOn shift.
# Drum / drum_kit voices skip — jumping a kick ±12 is musical garbage.
_MELODIC_ROLES = frozenset({"bass", "lead", "pad", "stab", "chord"})


def apply_feel(
    events: list[Event],
    song_feel: dict[str, float],
    voice_slot: VoiceSlot,
    ppq: int,
    rng: random.Random,
) -> list[Event]:
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
    # spacing s_ticks*4/3 (= 160 ticks at PPQ=480). Max shift = s_ticks/3.
    swing_offset = int(round(s_ticks * groove / 3.0))

    # Resolve "this NoteOn should swing" predicate once for the voice.
    swing_predicate = _build_swing_predicate(voice_slot)

    out: list[Event] = []
    # Track octave shifts so the matching NoteOff lands at the same pitch.
    octave_shifts: dict[tuple[int, int, int], int] = {}

    for ev in events:
        new_tick = ev.tick

        # Humanize — universal ±ticks jitter.
        if humanize > 0:
            new_tick += rng.randint(-humanize, humanize)

        # Swing — delay odd-numbered 16th steps for swung events only.
        if swing_offset != 0 and s_ticks > 0 and swing_predicate(ev):
            step = ev.tick // s_ticks
            if step % 2 == 1:
                new_tick += swing_offset

        new_tick = max(0, new_tick)

        if isinstance(ev, NoteOn):
            new_vel = ev.velocity
            if accent_boost > 0 and s_ticks > 0 and (ev.tick // s_ticks) in _BACKBEAT_STEPS:
                new_vel += accent_boost
            if drive_boost > 0:
                new_vel += drive_boost
            new_vel = max(1, min(127, new_vel))

            new_note = ev.note
            if (
                octave_prob > 0
                and voice_slot.default_role in _MELODIC_ROLES
                and rng.random() < octave_prob
            ):
                jump = 12 if rng.random() < 0.5 else -12
                shifted = ev.note + jump
                if 0 <= shifted <= 127:
                    new_note = shifted
                    octave_shifts[(ev.channel, ev.note, id(ev))] = jump

            out.append(
                NoteOn(
                    tick=new_tick,
                    channel=ev.channel,
                    note=new_note,
                    velocity=new_vel,
                )
            )
        elif isinstance(ev, NoteOff):
            # Mirror any octave shift applied to the matching NoteOn.
            key = next(
                (k for k in reversed(octave_shifts) if k[0] == ev.channel and k[1] == ev.note),
                None,
            )
            new_note = ev.note
            if key is not None:
                shift = octave_shifts.pop(key, 0)
                if shift:
                    new_note = ev.note + shift
            out.append(
                NoteOff(
                    tick=new_tick,
                    channel=ev.channel,
                    note=new_note,
                    velocity=ev.velocity,
                )
            )
        elif isinstance(ev, ControlChange):
            out.append(
                ControlChange(
                    tick=new_tick,
                    channel=ev.channel,
                    cc=ev.cc,
                    value=ev.value,
                    function=ev.function,
                )
            )
        elif isinstance(ev, PitchBend):
            out.append(
                PitchBend(
                    tick=new_tick,
                    channel=ev.channel,
                    value=ev.value,
                    function=ev.function,
                )
            )
        elif isinstance(ev, ChannelPressure):
            out.append(
                ChannelPressure(
                    tick=new_tick,
                    channel=ev.channel,
                    value=ev.value,
                    function=ev.function,
                )
            )
        else:  # pragma: no cover — exhaustive over Event union
            out.append(ev)
    return out


def _build_swing_predicate(voice_slot: VoiceSlot):
    """Return a predicate ``(Event) -> bool`` selecting events that swing.

    For a ``drum_kit`` voice, hat-like pieces swing (matched by
    ``slot.kit_map`` entry's ``(channel, note)``). For ``drum`` voices,
    the voice swings if its own name is hat-like. For melodic voices
    (``lead`` / ``stab`` / ``chord`` roles), every NoteOn swings.
    Everything else stays on the grid.
    """
    if voice_slot.type == "drum_kit":
        hat_pairs = {
            (piece.channel, piece.note)
            for name, piece in voice_slot.kit_map.items()
            if name in _HAT_INSTRUMENT_NAMES
        }
        if not hat_pairs:
            return lambda ev: False
        return lambda ev: (
            isinstance(ev, NoteOn | NoteOff) and (ev.channel, ev.note) in hat_pairs
        )
    if voice_slot.type == "drum":
        if voice_slot.name in _HAT_INSTRUMENT_NAMES:
            return lambda ev: isinstance(ev, NoteOn | NoteOff)
        return lambda ev: False
    if voice_slot.default_role in _SWUNG_NOTE_ROLES:
        return lambda ev: isinstance(ev, NoteOn | NoteOff)
    return lambda ev: False
