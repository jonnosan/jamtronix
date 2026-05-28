"""Compile song-wide feel knobs into synthetic per-voice mix knobs.

Schema v3 moved the bar-internal feel knobs (humanize / swing / accent /
mute_prob / octave_jump) off the per-voice surface and replaced them with
five song-wide :attr:`jtx.model.song.Song.feel` knobs (``pump``,
``groove``, ``drive``, ``tension``, ``wander``). Most of those translate
into the post-emit :mod:`jtx.engine.feel` pass or are read directly by
algorithms via :attr:`BarContext.song_feel`. ``pump`` is different — it's
a sidechain instruction, and the mix pass is where sidechains live.

Rather than teach the mix pass about a new knob shape, this module
*compiles* ``pump`` into the same ``sidechain_from`` / ``sidechain_floor``
/ ``sidechain_release_beats`` knobs the user can already set explicitly.
The SongPlayer merges the synthesized knobs into each voice's
``mix_knobs`` between LFO application and the mix pass, with **explicit
user values winning on key collision**.

The Pump convention assumes the kick instrument is named ``"kick"``.
A voice (or kit piece) carrying that instrument name acts as the duck
trigger; voices that don't emit a ``"kick"`` Hit are unaffected. See
``docs/SPEC.md`` §Global Feel for the full semantics.
"""

from __future__ import annotations

from collections.abc import Iterable

from jtx.model.setup import VoiceSlot
from jtx.model.song import KnobDict

PUMP_SOURCE_INSTRUMENT = "kick"
"""Instrument name whose Hit events trigger Pump ducking."""

_PUMP_FLOOR_BASE = 127
_PUMP_FLOOR_RANGE = 80
"""At ``pump=0`` the synthesized floor is 127 (no duck). At ``pump=1``
it's ``127 - 80 = 47`` — strong but not silencing."""

_PUMP_RELEASE_BEATS = 0.5
"""Quarter-note release. Long enough for a four-on-the-floor kick to
keep the duck open across consecutive kicks at 120–140 BPM."""


def compile_global_feel(
    song_feel: dict[str, float],
    voices: Iterable[tuple[str, VoiceSlot]],
) -> dict[str, KnobDict]:
    """Translate song-wide feel knobs into synthetic per-voice mix knobs.

    Returns a dict ``{voice_name: partial_mix_knobs}``. The caller merges
    these into each voice's resolved ``mix_knobs`` such that any explicit
    user value (from ``VoiceConfig.mix`` or ``VoiceOverride.mix``) wins
    on key collision.

    Currently only Pump produces output. Groove / Drive / Wander live in
    the post-emit feel pass; Tension is handled directly in SongPlayer.
    """
    pump = max(0.0, min(1.0, float(song_feel.get("pump", 0.0))))
    if pump <= 0.0:
        return {}

    floor = max(0, min(127, _PUMP_FLOOR_BASE - int(round(pump * _PUMP_FLOOR_RANGE))))
    synthetic: dict[str, KnobDict] = {}
    for name, slot in voices:
        # The kit itself contains the kick — sidechaining it from its
        # own kick would duck the kit (including the kick). Skip.
        if slot.type == "drum_kit":
            continue
        # A standalone voice that *is* the kick can't sidechain itself.
        if name == PUMP_SOURCE_INSTRUMENT:
            continue
        synthetic[name] = {
            "sidechain_from": [PUMP_SOURCE_INSTRUMENT],
            "sidechain_floor": floor,
            "sidechain_release_beats": _PUMP_RELEASE_BEATS,
        }
    return synthetic


def merge_synthetic_into_mix(
    explicit: KnobDict,
    synthetic: KnobDict,
) -> KnobDict:
    """Merge synthetic mix knobs into an explicit dict in place.

    Synthetic values fill in keys the user didn't set; explicit values
    are never overwritten. Returns the same ``explicit`` dict for
    chaining convenience.
    """
    for key, value in synthetic.items():
        explicit.setdefault(key, value)
    return explicit
