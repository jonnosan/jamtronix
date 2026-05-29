"""Sink-side parameter router — rewrites function-tagged events.

The router sits between :func:`jtx.engine.feel.apply_feel` and the sink
in :class:`jtx.player.SongPlayer`. One instance per voice.

For each function-tagged :class:`ControlChange` /
:class:`PitchBend` / :class:`ChannelPressure` event, the router looks up
the target in this order:

1. ``voice_slot.parameter_map[function]`` — per-voice override.
2. ``algorithm.DEFAULT_PARAM_MAP[function]`` — algorithm-level default.
3. None — event passes through unchanged.

Tagged events ride the voice's single MIDI channel; per-note pitch
bend (e.g. ``acid_bass``'s wobble, ``noise_riser``'s sweep) is
emitted on that same channel as monophonic articulation.
"""

from __future__ import annotations

from collections.abc import Iterable

from jtx.engine.events import (
    ChannelPressure,
    ControlChange,
    Event,
    PitchBend,
)
from jtx.engine.osc_client import OscClientProtocol
from jtx.model.parameter_target import (
    CCTarget,
    OscTarget,
    ParameterTarget,
)
from jtx.model.setup import VoiceSlot


class ParameterRouter:
    """Per-voice event rewriter."""

    def __init__(
        self,
        slot: VoiceSlot,
        default_param_map: dict[str, ParameterTarget] | None = None,
        *,
        osc_client: OscClientProtocol | None = None,
    ) -> None:
        self._slot = slot
        self._defaults: dict[str, ParameterTarget] = dict(default_param_map or {})
        self._osc_client = osc_client

    # ------------------------------------------------------------ route

    def route(self, events: Iterable[Event]) -> list[Event]:
        """Rewrite *events* per parameter_map.

        Input ticks are bar-relative; output ticks unchanged. Input is
        copied; the input list is not mutated.
        """
        out: list[Event] = []
        for ev in sorted(events, key=lambda e: e.tick):
            if isinstance(ev, ControlChange | PitchBend | ChannelPressure):
                routed = self._route_tagged(ev)
                # ``None`` means the source was OSC-routed — no MIDI
                # event is emitted for it. The OSC client has already
                # been called out-of-band inside ``_route_tagged``.
                if routed is not None:
                    out.append(routed)
            else:
                out.append(ev)
        return out

    # --------------------------------------------------- tagged route

    def _route_tagged(self, ev: ControlChange | PitchBend | ChannelPressure) -> Event | None:
        """Rewrite *ev* per the resolved target.

        Returns the rewritten event, or ``None`` if the target is OSC
        (the OSC client has been called out-of-band and no MIDI event
        is emitted for this source).
        """
        fn = ev.function
        if fn is None:
            return ev
        target = self._slot.parameter_map.get(fn) or self._defaults.get(fn)
        if target is None:
            return ev

        if isinstance(target, OscTarget):
            if self._osc_client is None:
                raise RuntimeError(
                    f"voice {self._slot.name!r}: function {fn!r} maps to OscTarget "
                    f"{target.address!r} but no OSC client was configured on the "
                    "ParameterRouter. Configure setup.osc_host / osc_port and run "
                    "via SongPlayer, or pass osc_client= to ParameterRouter()."
                )
            value = _to_osc_value(ev)
            self._osc_client.send(target.address, value)
            return None

        if isinstance(target, CCTarget):
            value = _to_cc_value(ev)
            return ControlChange(
                tick=ev.tick,
                channel=self._slot.midi_channel,
                cc=target.cc,
                value=value,
                function=fn,
            )
        raise TypeError(  # pragma: no cover — forwards-incompat target
            f"parameter router: unsupported target {type(target).__name__}"
        )


def _to_cc_value(ev: ControlChange | PitchBend | ChannelPressure) -> int:
    """Coerce an event's value to a 0..127 CC-shaped int."""
    if isinstance(ev, ControlChange | ChannelPressure):
        return max(0, min(127, ev.value))
    # PitchBend: -8192..8191 → 0..127 linear.
    scaled = round((ev.value + 8192) * 127 / 16383)
    return max(0, min(127, scaled))


def _to_osc_value(ev: ControlChange | PitchBend | ChannelPressure) -> float:
    """Coerce an event's value to the OSC float range for its kind.

    PitchBend (a ``"bend"``-like function) lands in ``[-1, 1]``; CC and
    ChannelPressure (``"cutoff"`` / ``"resonance"`` / etc.) land in
    ``[0, 1]``. Receivers can scale to whatever range suits the
    destination param.
    """
    if isinstance(ev, PitchBend):
        return max(-1.0, min(1.0, ev.value / 8192.0))
    return max(0.0, min(1.0, ev.value / 127.0))
