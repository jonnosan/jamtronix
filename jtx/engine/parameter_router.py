"""Sink-side parameter router — rewrites function-tagged events.

The router sits between :func:`jtx.engine.feel.apply_feel` and the sink
in :class:`jtx.player.SongPlayer`. One instance per voice; constructed
in ``SongPlayer.__init__`` and **persistent across bars** so the MPE
channel allocator survives bar boundaries (notes can sustain across
bars under ``gate=0.95``).

For each function-tagged :class:`ControlChange` /
:class:`PitchBend` / :class:`ChannelPressure` event, the router looks up
the target in this order:

1. ``voice_slot.parameter_map[function]`` — per-voice override.
2. ``algorithm.DEFAULT_PARAM_MAP[function]`` — algorithm-level default.
3. None — event passes through unchanged.

For MPE voices (``voice_slot.mpe_mode == True``):

* NoteOns claim a channel from the voice's MPE block
  ``[midi_channel, midi_channel + mpe_channel_count - 1]`` round-robin.
* Steal-oldest when the block is full; the displaced note gets a
  synthetic NoteOff emitted on its (now reused) channel before the new
  NoteOn lands.
* Tagged events between a NoteOn and its NoteOff ride the same
  allocated channel. The associated-note rule uses a 2-tick lead window
  on the NoteOn side so ``acid_bass``'s leading ``PitchBend`` at
  ``tick - 1`` binds to the NoteOn at ``tick``.
* Trailing tagged events at ``NoteOff.tick`` still bind to the
  just-released note — pass 1 allocates all NoteOns/NoteOffs up-front,
  pass 2 routes tagged events against that completed view, and only
  *then* are ended notes swept from the active set. This is what stops
  ``acid_bass``'s trailing zero-bend leaking onto the next note's
  channel.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import cast

from jtx.engine.events import (
    ChannelPressure,
    ControlChange,
    Event,
    NoteOff,
    NoteOn,
    PitchBend,
)
from jtx.model.parameter_target import (
    CCTarget,
    MPEPitchBendTarget,
    MPEPressureTarget,
    MPETimbreTarget,
    ParameterTarget,
)
from jtx.model.setup import VoiceSlot

LEAD_WINDOW_TICKS = 2
"""How far ahead of a NoteOn a tagged event may sit and still bind to it.

Absorbs ``acid_bass``'s pre-bend at ``NoteOn.tick - 1`` and per-note
``glide`` CC at ``NoteOn.tick - 2``.
"""

_MPE_TIMBRE_CC = 74


@dataclass
class _NoteRecord:
    """One NoteOn allocation. Survives until the next route() sweep."""

    pitch: int
    src_channel: int
    out_channel: int
    on_tick: int
    off_tick: int | None  # None until the matching NoteOff is processed
    seq: int  # allocation order (router-wide monotonic counter)


class ParameterRouter:
    """Per-voice stateful event rewriter."""

    def __init__(
        self,
        slot: VoiceSlot,
        default_param_map: dict[str, ParameterTarget] | None = None,
    ) -> None:
        self._slot = slot
        self._defaults: dict[str, ParameterTarget] = dict(default_param_map or {})

        if slot.mpe_mode:
            self._block: list[int] = list(
                range(slot.midi_channel, slot.midi_channel + slot.mpe_channel_count)
            )
        else:
            self._block = []

        # Allocation order matters for steal-oldest; track explicitly.
        self._records: list[_NoteRecord] = []
        # Live notes — (pitch, src_channel) → record. Removed at sweep.
        self._active: dict[tuple[int, int], _NoteRecord] = {}
        # Allocation counter for record.seq (monotonic across bars).
        self._seq: int = 0
        # Most recently allocated channel — fallback for tagged events
        # with no binding note. Initialised to voice's main channel so
        # the first tagged event before any NoteOn has somewhere to go.
        self._last_allocated: int = self._block[0] if slot.mpe_mode else slot.midi_channel
        # Index into ``_block`` of the most recently used channel.
        # Round-robin starts from ``(last_used_idx + 1) % len(block)``.
        self._last_used_idx: int = -1

    # ------------------------------------------------------------ route

    def route(self, events: Iterable[Event]) -> list[Event]:
        """Rewrite *events* per parameter_map + MPE allocation.

        Input ticks are bar-relative; output ticks unchanged. Input is
        copied; the input list is not mutated.
        """
        sorted_events = sorted(events, key=lambda e: e.tick)
        if not sorted_events:
            return []

        # Pass 1 — allocate all NoteOns; record NoteOff ticks; emit
        # synthetic NoteOffs for steals into an interleaved buffer.
        # For each input event, record (event, channel_override) where
        # channel_override is the rewritten MIDI channel for
        # NoteOn/NoteOff (None for tagged events handled in pass 2).
        synthetic_offs: list[tuple[int, NoteOff]] = []  # (insert-before-idx, off)
        rewritten_channels: list[int | None] = [None] * len(sorted_events)

        for idx, ev in enumerate(sorted_events):
            if isinstance(ev, NoteOn):
                channel, synth = self._allocate(ev)
                for sof in synth:
                    synthetic_offs.append((idx, sof))
                rewritten_channels[idx] = channel
            elif isinstance(ev, NoteOff):
                channel = self._mark_off(ev)
                rewritten_channels[idx] = channel

        # Pass 2 — walk in original order, emitting routed events and
        # interleaving synthetic NoteOffs immediately before the NoteOn
        # that displaced them.
        out: list[Event] = []
        synth_cursor = 0
        for idx, ev in enumerate(sorted_events):
            while synth_cursor < len(synthetic_offs) and synthetic_offs[synth_cursor][0] == idx:
                out.append(synthetic_offs[synth_cursor][1])
                synth_cursor += 1

            if isinstance(ev, NoteOn):
                out.append(
                    NoteOn(
                        tick=ev.tick,
                        channel=cast("int", rewritten_channels[idx]),
                        note=ev.note,
                        velocity=ev.velocity,
                    )
                )
            elif isinstance(ev, NoteOff):
                out.append(
                    NoteOff(
                        tick=ev.tick,
                        channel=cast("int", rewritten_channels[idx]),
                        note=ev.note,
                        velocity=ev.velocity,
                    )
                )
            elif isinstance(ev, ControlChange | PitchBend | ChannelPressure):
                out.append(self._route_tagged(ev))
            else:
                out.append(ev)

        # Sweep notes whose NoteOff fell within this bar. Notes still
        # held (off_tick is None) stay in _active for the next bar.
        last_tick = sorted_events[-1].tick
        self._sweep(last_tick)
        return out

    # ----------------------------------------------------- allocation

    def _allocate(self, note: NoteOn) -> tuple[int, list[NoteOff]]:
        """Allocate a channel for *note* and return ``(channel, synthetic_offs)``.

        ``synthetic_offs`` is non-empty only when the MPE block is full
        and we have to steal the oldest live note's channel.
        """
        synthetic: list[NoteOff] = []
        if not self._slot.mpe_mode:
            channel = self._slot.midi_channel
            self._record_note(note, channel)
            return channel, synthetic

        block = self._block
        live_channels = {r.out_channel for r in self._active.values()}
        candidate_idx = -1
        for offset in range(1, len(block) + 1):
            idx = (self._last_used_idx + offset) % len(block)
            if block[idx] not in live_channels:
                candidate_idx = idx
                break

        if candidate_idx < 0:
            # Block full: steal the oldest live note.
            oldest_key, oldest_record = min(self._active.items(), key=lambda kv: kv[1].seq)
            stolen_channel = oldest_record.out_channel
            synthetic.append(
                NoteOff(
                    tick=note.tick,
                    channel=stolen_channel,
                    note=oldest_record.pitch,
                    velocity=0,
                )
            )
            oldest_record.off_tick = note.tick
            del self._active[oldest_key]
            candidate_idx = block.index(stolen_channel)

        channel = block[candidate_idx]
        self._last_used_idx = candidate_idx
        self._record_note(note, channel)
        return channel, synthetic

    def _record_note(self, note: NoteOn, channel: int) -> None:
        record = _NoteRecord(
            pitch=note.note,
            src_channel=note.channel,
            out_channel=channel,
            on_tick=note.tick,
            off_tick=None,
            seq=self._seq,
        )
        self._seq += 1
        self._records.append(record)
        self._active[(note.note, note.channel)] = record
        self._last_allocated = channel

    def _mark_off(self, off: NoteOff) -> int:
        key = (off.note, off.channel)
        record = self._active.get(key)
        if record is None:
            # Stray NoteOff — no matching live NoteOn for this voice.
            # Send on the voice's main channel (non-MPE) or
            # last-allocated (MPE).
            return self._last_allocated if self._slot.mpe_mode else self._slot.midi_channel
        record.off_tick = off.tick
        return record.out_channel

    def _sweep(self, last_tick: int) -> None:
        """Drop records whose NoteOff fell at or before *last_tick*.

        Notes still held at end of bar (off_tick is None) survive into
        the next bar so cross-bar tagged events still bind correctly.
        """
        kept: list[_NoteRecord] = []
        for r in self._records:
            if r.off_tick is None or r.off_tick > last_tick:
                kept.append(r)
        # Trim _records but keep allocation order so steal-oldest still
        # picks the genuinely oldest live note.
        self._records = kept

    # --------------------------------------------------- tagged route

    def _route_tagged(self, ev: ControlChange | PitchBend | ChannelPressure) -> Event:
        fn = ev.function
        if fn is None:
            return ev
        target = self._slot.parameter_map.get(fn) or self._defaults.get(fn)
        channel = self._channel_for_tagged(ev.tick)
        if target is None:
            # No mapping anywhere — pass through with channel rebind
            # for MPE voices (tagged events need to land on the right
            # note channel, even if the user hasn't picked an MPE
            # target type).
            if self._slot.mpe_mode and channel != ev.channel:
                return _rechannel(ev, channel)
            return ev

        if isinstance(target, CCTarget):
            value = _to_cc_value(ev)
            return ControlChange(
                tick=ev.tick,
                channel=channel,
                cc=target.cc,
                value=value,
                function=fn,
            )
        if isinstance(target, MPEPitchBendTarget):
            value = _to_pb_value(ev)
            return PitchBend(
                tick=ev.tick,
                channel=channel,
                value=value,
                function=fn,
            )
        if isinstance(target, MPEPressureTarget):
            value = _to_cc_value(ev)
            return ChannelPressure(
                tick=ev.tick,
                channel=channel,
                value=value,
                function=fn,
            )
        if isinstance(target, MPETimbreTarget):
            value = _to_cc_value(ev)
            return ControlChange(
                tick=ev.tick,
                channel=channel,
                cc=_MPE_TIMBRE_CC,
                value=value,
                function=fn,
            )
        raise TypeError(  # pragma: no cover — forwards-incompat target
            f"parameter router: unsupported target {type(target).__name__}"
        )

    def _channel_for_tagged(self, tick: int) -> int:
        """Pick the channel a tagged event at *tick* rides on.

        Non-MPE voices: voice's main channel.

        MPE voices: bind by three-tier priority so back-to-back notes
        (NoteOff and the next NoteOn at the same tick) split their
        tagged events correctly:

        1. **Leading bend** — a record whose ``on_tick`` is within the
           next ``LEAD_WINDOW`` ticks. Catches ``acid_bass``'s pre-bend
           at ``next_NoteOn.tick - 1`` and per-note glide CC at
           ``next_NoteOn.tick - 2``.
        2. **Trailing bend** — a record whose ``off_tick`` equals
           ``tick``. Catches ``acid_bass``'s zero-bend reset at
           ``NoteOff.tick``.
        3. **In-lifetime** — any record currently sounding at ``tick``.
           Catches the quarter-note CC74 LFO between notes.

        Within each tier, prefer the most-recently-allocated record
        (highest ``seq``). Falls back to ``_last_allocated`` if no
        record matches any tier.
        """
        if not self._slot.mpe_mode:
            return self._slot.midi_channel

        leading: _NoteRecord | None = None
        trailing: _NoteRecord | None = None
        in_life: _NoteRecord | None = None
        for r in self._records:
            if tick + 1 <= r.on_tick <= tick + LEAD_WINDOW_TICKS:
                if leading is None or r.seq > leading.seq:
                    leading = r
                continue
            if r.off_tick is not None and r.off_tick == tick:
                if trailing is None or r.seq > trailing.seq:
                    trailing = r
                continue
            if r.on_tick <= tick and (r.off_tick is None or tick <= r.off_tick):
                if in_life is None or r.seq > in_life.seq:
                    in_life = r
        for candidate in (leading, trailing, in_life):
            if candidate is not None:
                return candidate.out_channel
        return self._last_allocated


def _to_cc_value(ev: ControlChange | PitchBend | ChannelPressure) -> int:
    """Coerce an event's value to a 0..127 CC-shaped int."""
    if isinstance(ev, ControlChange | ChannelPressure):
        return max(0, min(127, ev.value))
    # PitchBend: -8192..8191 → 0..127 linear.
    scaled = round((ev.value + 8192) * 127 / 16383)
    return max(0, min(127, scaled))


def _to_pb_value(ev: ControlChange | PitchBend | ChannelPressure) -> int:
    """Coerce an event's value to a -8192..8191 pitchwheel int."""
    if isinstance(ev, PitchBend):
        return max(-8192, min(8191, ev.value))
    # CC / ChannelPressure 0..127 → pitchwheel.
    scaled = round(ev.value * 16383 / 127) - 8192
    return max(-8192, min(8191, scaled))


def _rechannel(
    ev: ControlChange | PitchBend | ChannelPressure, channel: int
) -> ControlChange | PitchBend | ChannelPressure:
    """Return *ev* with ``channel`` swapped; preserves the function tag."""
    return replace(ev, channel=channel)
