"""SongPlayer — orchestrates the engine to produce a BarGenerator.

This is the glue layer that connects a :class:`jtx.model.Song` plus its
:class:`jtx.model.Setup` to the :class:`jtx.engine.Scheduler`'s callable
``BarGenerator`` contract. Per-bar pipeline:

1. Derive a per-(song, part, voice) seed via :func:`jtx.seed.derive_part_voice_seed`
   plus the per-bar seed via :func:`jtx.seed.derive_bar_seed`.
2. Resolve effective pattern + feel knobs for each voice
   (part override → song-level → algorithm default).
3. Query the :class:`jtx.engine.RootProvider` for this bar's
   chord root.
4. Build a :class:`jtx.engine.BarContext` per voice.
5. Apply LFO bindings to the bar contexts + collect any
   ``midi:`` target ControlChange events.
6. Topologically run non-follower algorithms first, then followers
   (with ``ctx.source_events`` populated from their source voice's
   bar output).
7. Run the feel post-emit pass per voice.
8. Concatenate and return.

The scheduler then sorts + dispatches the events.

Deferred to future work:
* Multi-part arrangements (the GUI's Live view will pass the active
  part name; this player handles only one part at a time).
* Tempo + meter from anywhere other than the song header (per-part
  overrides for tempo / meter exist in the model but aren't wired
  into the player yet).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jtx.algorithms import (
    CCLFO,
    AcidBass,
    Arp,
    CCEnvelope,
    ChordStab,
    DrumOneShot,
    DrumPattern,
    MelodicLine,
    RootPulse,
    SubDrone,
    SustainedChord,
    VoiceFollower,
)
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event
from jtx.engine.feel import apply_feel
from jtx.engine.lfo import apply_lfos_to_bar
from jtx.engine.meter import ticks_per_bar
from jtx.engine.mix import apply_mix_pass
from jtx.engine.root_provider import ProgressionRootProvider, RootProvider
from jtx.model.setup import Setup, VoiceSlot
from jtx.model.song import KnobDict, Song, VoiceConfig, VoiceOverride
from jtx.seed import derive_bar_seed, derive_part_voice_seed, seed_from_title

_GM_DRUM_DEFAULT = 36  # GM kick — last-resort fallback when no kit_map entry.


def instantiate_algorithm(algorithm_name: str, voice_slot: VoiceSlot) -> Algorithm:
    """Build the right :class:`Algorithm` subclass for *algorithm_name*.

    For drum algorithms the voice's name doubles as the kit-piece key
    into ``voice_slot.kit_map`` (so a voice called ``kick`` with
    ``kit_map={"kick": 36}`` plays note 36).
    """
    ch = voice_slot.midi_channel
    if algorithm_name == "drum_pattern":
        return DrumPattern(
            piece=voice_slot.name,
            midi_channel=ch,
            midi_note=voice_slot.kit_map.get(voice_slot.name, _GM_DRUM_DEFAULT),
        )
    if algorithm_name == "drum_one_shot":
        return DrumOneShot(
            midi_channel=ch,
            midi_note=voice_slot.kit_map.get(voice_slot.name, _GM_DRUM_DEFAULT),
        )
    if algorithm_name == "acid_bass":
        return AcidBass(midi_channel=ch)
    if algorithm_name == "sub_drone":
        return SubDrone(midi_channel=ch)
    if algorithm_name == "melodic_line":
        return MelodicLine(midi_channel=ch)
    if algorithm_name == "arp":
        return Arp(midi_channel=ch)
    if algorithm_name == "sustained_chord":
        return SustainedChord(midi_channel=ch)
    if algorithm_name == "chord_stab":
        return ChordStab(midi_channel=ch)
    if algorithm_name == "cc_lfo":
        return CCLFO(midi_channel=ch)
    if algorithm_name == "cc_envelope":
        return CCEnvelope(midi_channel=ch)
    if algorithm_name == "voice_follower":
        return VoiceFollower(midi_channel=ch)
    if algorithm_name == "root_pulse":
        return RootPulse(midi_channel=ch)
    raise ValueError(f"unknown algorithm: {algorithm_name!r}")


@dataclass
class _ResolvedVoice:
    """Per-voice runtime data pre-resolved at SongPlayer construction."""

    name: str
    slot: VoiceSlot
    algorithm: Algorithm
    algorithm_name: str  # for follower-source lookup


class SongPlayer:
    """Glue between a Song/Setup and a Scheduler's ``BarGenerator`` callable.

    Construct once per (song, setup, part_name); call
    :meth:`bar_generator` to get the callable to hand the Scheduler.
    """

    def __init__(
        self,
        song: Song,
        setup: Setup,
        part_name: str,
        *,
        ppq: int = 480,
        root_provider: RootProvider | None = None,
    ) -> None:
        if part_name not in song.parts:
            raise ValueError(f"part {part_name!r} not in song {song.title!r}")

        self.song = song
        self.setup = setup
        self.part_name = part_name
        self.part = song.parts[part_name]
        self.ppq = ppq
        self.ticks_per_bar = ticks_per_bar(song.meter, ppq)

        self.song_seed: int = (
            song.seed_override if song.seed_override is not None else seed_from_title(song.title)
        )

        self.root_provider: RootProvider = root_provider or ProgressionRootProvider(
            song.key, song.chord_progression
        )

        # Resolve every song-level voice to its algorithm instance.
        # We honour ``voices`` ordering for stable bar-generator output.
        self._voices: list[_ResolvedVoice] = []
        for vname, vconfig in song.voices.items():
            slot = setup.voice(vname)
            if slot is None:
                raise ValueError(f"voice {vname!r} not in setup {setup.id!r}")
            algo = instantiate_algorithm(vconfig.algorithm, slot)
            self._voices.append(
                _ResolvedVoice(
                    name=vname,
                    slot=slot,
                    algorithm=algo,
                    algorithm_name=vconfig.algorithm,
                )
            )

        # Topological order: non-followers first, then followers in
        # dependency order. Cycle-free by validation.
        self._run_order = self._topo_sort()

        # Previous-bar event cache for cross-bar sidechain lookback
        # and (later) follower lookback. Updated at the end of every
        # ``events_for_bar``. Initially empty (the part's bar 0 has
        # no history); after a full pass through the part it
        # naturally provides modular wraparound when the CLI loops.
        self._last_bar: int | None = None
        self._prev_voice_events: dict[str, list[Event]] = {}

    def _topo_sort(self) -> list[_ResolvedVoice]:
        # Sources first, followers after. For followers, the source
        # must precede them — recurse if a follower's source is itself
        # a follower (chained followers).
        by_name = {v.name: v for v in self._voices}
        ordered: list[_ResolvedVoice] = []
        seen: set[str] = set()

        def visit(v: _ResolvedVoice) -> None:
            if v.name in seen:
                return
            if v.algorithm_name == "voice_follower":
                vc = self.song.voices[v.name]
                src = vc.pattern.get("source")
                if isinstance(src, str) and src in by_name:
                    visit(by_name[src])
            seen.add(v.name)
            ordered.append(v)

        for v in self._voices:
            visit(v)
        return ordered

    def bar_generator(self) -> Callable[[int], list[Event]]:
        """Return a callable suitable for :meth:`Scheduler.run`."""

        def gen(bar_idx: int) -> list[Event]:
            return self.events_for_bar(bar_idx)

        return gen

    def events_for_bar(self, bar_idx: int) -> list[Event]:
        chord_root = self.root_provider.root_semitones_for_bar(bar_idx)

        # Build BarContext per voice + collect for LFO application.
        contexts: dict[str, BarContext] = {}
        for v in self._voices:
            pv_seed = derive_part_voice_seed(self.song_seed, self.part_name, v.name)
            bar_seed = derive_bar_seed(pv_seed, bar_idx)
            import random as _r

            song_voice = self.song.voices[v.name]
            pattern_knobs, feel_knobs = self._resolve_knobs(v.name, song_voice)
            contexts[v.name] = BarContext(
                bar_index=bar_idx,
                tick_offset=bar_idx * self.ticks_per_bar,
                ticks_per_bar=self.ticks_per_bar,
                tempo_bpm=self.song.tempo,
                ppq=self.ppq,
                key=self.song.key,
                chord_root_semitones=chord_root,
                pattern_knobs=pattern_knobs,
                feel_knobs=feel_knobs,
                rng=_r.Random(bar_seed),
            )

        # LFO application — runs on a song-level RNG so its randomness
        # doesn't depend on which voice happens to be running.
        import random as _r

        lfo_seed = derive_bar_seed(self.song_seed, bar_idx)
        lfo_events = apply_lfos_to_bar(
            self.song.lfos,
            self.part_name,
            contexts,
            bar_idx,
            self.ticks_per_bar,
            _r.Random(lfo_seed),
        )

        # Did the caller request consecutive bars? Only then does the
        # cached previous bar count as "history" for cross-bar lookback.
        # If they jumped (e.g. asked for bar 5 cold), prev = empty.
        expected_prev = (bar_idx - 1) % self.part.bars if self.part.bars > 0 else None
        if self._last_bar is not None and self._last_bar == expected_prev:
            prev_voice_events = self._prev_voice_events
        else:
            prev_voice_events = {}

        # Run algorithms in topological order; feed follower source_events.
        raw_voice_events: dict[str, list[Event]] = {}
        for v in self._voices:
            ctx = contexts[v.name]
            if v.algorithm_name == "voice_follower":
                src = self.song.voices[v.name].pattern.get("source")
                if isinstance(src, str):
                    ctx.source_events = raw_voice_events.get(src, [])
                    ctx.prev_source_events = prev_voice_events.get(src)
            raw_voice_events[v.name] = v.algorithm.generate_bar(ctx)

        # Mix pass — sidechain ducking (cross-voice, cross-bar) +
        # fade-in/out envelope per voice. Runs before the per-voice
        # feel pass so jitter / accent layer on top of the ducked /
        # faded velocities.
        feel_knobs_by_voice = {v.name: contexts[v.name].feel_knobs for v in self._voices}
        mixed_voice_events = apply_mix_pass(
            raw_voice_events,
            prev_voice_events,
            feel_knobs_by_voice,
            bar_idx,
            self.ticks_per_bar,
            self.ppq,
        )

        # Feel post-emit pass per voice (bar-internal jitter/accent/swing).
        voice_events: dict[str, list[Event]] = {}
        for v in self._voices:
            ctx = contexts[v.name]
            shaped = apply_feel(mixed_voice_events[v.name], ctx.feel_knobs, self.ppq, ctx.rng)
            voice_events[v.name] = shaped

        # Cache for next bar's lookback. We cache the *post-mix* events
        # because that's what next-bar sidechain triggers reference —
        # ducking a voice that itself got ducked is musically sane.
        self._last_bar = bar_idx
        self._prev_voice_events = {n: list(es) for n, es in mixed_voice_events.items()}

        all_events: list[Event] = list(lfo_events)
        for v in self._voices:
            all_events.extend(voice_events[v.name])
        return all_events

    def _resolve_knobs(self, voice_name: str, song_voice: VoiceConfig) -> tuple[KnobDict, KnobDict]:
        """Return (pattern, feel) merged with any part override.

        Resolution order: part override > song-level > algorithm default.
        Algorithm defaults are baked into algorithm code (each
        ``knobs.get(name, default)``), so this method only handles the
        explicit-override layer.
        """
        override: VoiceOverride | None = self.part.voice_overrides.get(voice_name)
        pattern: dict[str, Any] = dict(song_voice.pattern)
        feel: dict[str, Any] = dict(song_voice.feel)
        if override is not None:
            pattern.update(override.pattern)
            feel.update(override.feel)
        return pattern, feel
