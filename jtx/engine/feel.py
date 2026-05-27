"""Post-emit feel knob pass.

Algorithms emit "ideal" events. The scheduler-level pass implemented
here applies the universal feel knobs from ``docs/SPEC.md`` §Pattern
vs Feel Knobs:

* ``humanize`` — ±N tick jitter on every event.
* ``vel_jitter`` — ±N velocity jitter on note-ons.
* ``gate_jitter`` — ±fraction of duration jitter on note-off timing.
* ``swing`` — delay every other 16th. ``swing=0`` straight; ``swing=1.0``
  lands the odd 16th exactly on the 2/3 (triplet) position of the
  containing 8th, giving full 16th-note triplet feel; intermediate
  values interpolate shuffle character (≈0.5 = classic MPC swing).
* ``accent`` — velocity boost on configured beat steps.
* ``accent_beats`` — list of step indices (16th positions) that get
  the accent boost. Default ``[0, 8]`` (downbeats of beats 1 and 3).
* ``mute_prob`` — per-bar roll; on hit, drop every event in the bar.
* ``octave_jump`` — per-event ±12 semitone chance.

Each knob's default is 0 (no effect), so passing an empty feel-knob
dict is a no-op. Same RNG drives all knobs so determinism is
preserved when the caller passes a bar-seeded ``random.Random``.

Knobs not in v1 scope:
* ``evolution`` — wants part-level info (total bars) the bar-by-bar
  caller doesn't have here. Deferred.
* ``passing_tones`` — algorithm-specific; ``MelodicLine`` already
  exposes ``passing_prob`` directly.
"""

from __future__ import annotations

import random

from jtx.algorithms._steps import step_ticks
from jtx.engine.events import ControlChange, Event, NoteOff, NoteOn, PitchBend
from jtx.model.song import KnobDict


def apply_feel(
    events: list[Event],
    feel_knobs: KnobDict,
    ppq: int,
    rng: random.Random,
) -> list[Event]:
    """Return a new event list with feel knobs applied.

    Tick fields are bar-relative on the way in and on the way out;
    swing/humanize may push events slightly negative — they're clamped
    at 0 before return.
    """
    mute_prob = float(feel_knobs.get("mute_prob", 0.0))
    if mute_prob > 0 and rng.random() < mute_prob:
        return []

    swing = float(feel_knobs.get("swing", 0.0))
    humanize = int(feel_knobs.get("humanize", 0))
    vel_jitter = int(feel_knobs.get("vel_jitter", 0))
    gate_jitter = float(feel_knobs.get("gate_jitter", 0.0))
    accent = int(feel_knobs.get("accent", 0))
    octave_jump = float(feel_knobs.get("octave_jump", 0.0))

    raw_accent_beats = feel_knobs.get("accent_beats", [0, 8])
    if isinstance(raw_accent_beats, list):
        accent_beats = {int(b) for b in raw_accent_beats}
    else:
        accent_beats = {0, 8}

    s_ticks = step_ticks(ppq)
    # swing=1.0 → odd-16th lands at 2/3 of the containing 8th, i.e.
    # spacing s_ticks*4/3 (= 160 ticks at PPQ=480). That's the triplet
    # position, so max-shift = s_ticks/3. Linear interpolation in between.
    swing_offset = int(round(s_ticks * swing / 3.0))

    # Pair up notes for gate_jitter / octave_jump handling. NoteOn ↔
    # NoteOff pairing is by (channel, note) — first-in-first-out.
    on_to_off: dict[tuple[int, int, int], int] = {}
    # We'll process by event index so we can mutate paired NoteOff
    # ticks + notes together with their NoteOn.

    out: list[Event] = []
    # First pass: NoteOn-driven changes (vel jitter, accent, octave jump).
    # Track NoteOn → octave shift so we can apply the same shift to the
    # matching NoteOff.
    octave_shifts: dict[tuple[int, int, int], int] = {}

    for ev in events:
        new_ev: Event
        new_tick = ev.tick

        # Humanize.
        if humanize > 0:
            new_tick += rng.randint(-humanize, humanize)

        # Swing — delay odd-numbered 16ths.
        if swing_offset != 0 and s_ticks > 0:
            step = ev.tick // s_ticks
            if step % 2 == 1:
                new_tick += swing_offset

        new_tick = max(0, new_tick)

        if isinstance(ev, NoteOn):
            new_vel = ev.velocity
            if vel_jitter > 0:
                new_vel += rng.randint(-vel_jitter, vel_jitter)
            if accent > 0 and s_ticks > 0 and (ev.tick // s_ticks) in accent_beats:
                new_vel += accent
            new_vel = max(1, min(127, new_vel))

            new_note = ev.note
            if octave_jump > 0 and rng.random() < octave_jump:
                jump = 12 if rng.random() < 0.5 else -12
                shifted = ev.note + jump
                if 0 <= shifted <= 127:
                    new_note = shifted
                    octave_shifts[(ev.channel, ev.note, id(ev))] = jump

            new_ev = NoteOn(
                tick=new_tick,
                channel=ev.channel,
                note=new_note,
                velocity=new_vel,
            )
            # Record so the matching NoteOff can find it.
            on_to_off[(ev.channel, ev.note, id(ev))] = new_tick
        elif isinstance(ev, NoteOff):
            # Match by channel + original note; pick the most recent
            # NoteOn we recorded for this (channel, note) and pop it.
            key = next(
                (k for k in reversed(on_to_off) if k[0] == ev.channel and k[1] == ev.note),
                None,
            )
            new_note = ev.note
            if key is not None:
                shift = octave_shifts.pop(key, 0)
                if shift:
                    new_note = ev.note + shift
                on_to_off.pop(key)

            if gate_jitter > 0:
                # Reduce or extend duration by ±gate_jitter fraction of
                # the on→off distance.
                # We approximate by jittering the off tick directly:
                #   delta = ±gate_jitter * (off.tick - on.tick).
                # For a clean impl we'd need to know the matching on
                # tick; for v1 we apply a relative ±gate_jitter * s_ticks
                # which is the typical 16th-note duration.
                delta = int(s_ticks * gate_jitter * (rng.random() * 2 - 1))
                new_tick = max(0, new_tick + delta)

            new_ev = NoteOff(
                tick=new_tick,
                channel=ev.channel,
                note=new_note,
                velocity=ev.velocity,
            )
        elif isinstance(ev, ControlChange):
            new_ev = ControlChange(
                tick=new_tick,
                channel=ev.channel,
                cc=ev.cc,
                value=ev.value,
            )
        elif isinstance(ev, PitchBend):
            new_ev = PitchBend(
                tick=new_tick,
                channel=ev.channel,
                value=ev.value,
            )
        else:  # pragma: no cover — exhaustive over Event union
            new_ev = ev

        out.append(new_ev)
    return out
