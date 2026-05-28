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
    DrumKit,
    DrumOneShot,
    DrumPattern,
    MelodicLine,
    MotifPhrase,
    NoiseRiser,
    ReeseBass,
    RootPulse,
    StepCC,
    SubDrone,
    SustainedChord,
    VoiceFollower,
)
from jtx.engine.algorithm import Algorithm
from jtx.engine.context import BarContext
from jtx.engine.events import Event
from jtx.engine.feel import apply_feel
from jtx.engine.global_feel import compile_global_feel, merge_synthetic_into_mix
from jtx.engine.lfo import apply_lfos_to_bar
from jtx.engine.meter import ticks_per_bar
from jtx.engine.mix import apply_mix_pass
from jtx.engine.osc_client import OscClientProtocol
from jtx.engine.parameter_router import ParameterRouter
from jtx.engine.root_provider import ProgressionRootProvider, RootProvider
from jtx.engine.voicing import translate_abstract_events
from jtx.model.parameter_target import OscTarget
from jtx.model.setup import Setup, VoiceSlot
from jtx.model.song import KnobDict, Song, VoiceConfig, VoiceOverride
from jtx.seed import derive_bar_seed, derive_part_voice_seed, seed_from_title


def _setup_uses_osc(setup: Setup) -> bool:
    """Return True iff any voice in *setup* has an :class:`OscTarget`.

    Drives lazy construction of the real OSC client — no UDP socket is
    opened for setups that don't need one.
    """
    for slot in setup.voices:
        for target in slot.parameter_map.values():
            if isinstance(target, OscTarget):
                return True
    return False


def instantiate_algorithm(algorithm_name: str, voice_slot: VoiceSlot) -> Algorithm:
    """Build the right :class:`Algorithm` subclass for *algorithm_name*.

    Drum + drum_kit voices have distinct identity:

    * ``drum`` voice + ``drum_pattern`` / ``drum_one_shot`` algorithm:
      single MIDI note. The note lives on ``slot.note``; the algorithm
      itself still emits concrete MIDI (legacy protocol — refactored
      to emit ``Hit`` events later).
    * ``drum_kit`` voice + ``drum_kit`` algorithm: emits abstract
      :class:`Hit` events keyed by instrument name. The voicing stage
      downstream resolves each instrument to ``(channel, note)`` via
      ``slot.kit_map``.
    """
    ch = voice_slot.midi_channel
    if algorithm_name == "drum_kit":
        return DrumKit(kit_map=dict(voice_slot.kit_map))
    if algorithm_name == "drum_pattern":
        return DrumPattern(
            piece=voice_slot.name,
            midi_channel=ch,
            midi_note=voice_slot.note,
        )
    if algorithm_name == "drum_one_shot":
        return DrumOneShot(
            midi_channel=ch,
            midi_note=voice_slot.note,
        )
    if algorithm_name == "acid_bass":
        return AcidBass(midi_channel=ch)
    if algorithm_name == "sub_drone":
        return SubDrone(midi_channel=ch)
    if algorithm_name == "melodic_line":
        return MelodicLine(midi_channel=ch)
    if algorithm_name == "motif_phrase":
        return MotifPhrase(midi_channel=ch)
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
    if algorithm_name == "step_cc":
        return StepCC(midi_channel=ch)
    if algorithm_name == "noise_riser":
        return NoiseRiser(midi_channel=ch)
    if algorithm_name == "reese_bass":
        return ReeseBass(midi_channel=ch)
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
        osc_client: OscClientProtocol | None = None,
    ) -> None:
        if part_name not in song.parts:
            raise ValueError(f"part {part_name!r} not in song {song.title!r}")

        self.song = song
        self.setup = setup
        self.part_name = part_name
        self.part = song.parts[part_name]
        self.ppq = ppq
        # Part may override the meter; otherwise inherit from the song.
        effective_meter = self.part.meter or song.meter
        self.ticks_per_bar = ticks_per_bar(effective_meter, ppq)

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

        # OSC client — lazily constructed if any voice's parameter_map
        # references an OscTarget. Tests inject a MemoryOscClient via
        # the ``osc_client=`` constructor arg.
        self._osc_client: OscClientProtocol | None
        if osc_client is not None:
            self._osc_client = osc_client
        elif _setup_uses_osc(setup):
            from jtx.engine.osc_client import OscClient

            self._osc_client = OscClient(host=setup.osc_host, port=setup.osc_port)
        else:
            self._osc_client = None

        # Per-voice parameter routers. Stateful across bars so MPE
        # channel allocations + most-recently-allocated tracking
        # survive bar boundaries (notes can sustain across bars).
        self._routers: dict[str, ParameterRouter] = {
            v.name: ParameterRouter(
                v.slot,
                v.algorithm.DEFAULT_PARAM_MAP,
                osc_client=self._osc_client,
            )
            for v in self._voices
        }

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

    def close(self) -> None:
        """Release the OSC UDP socket (if any).

        Idempotent; safe to call when no OSC client was constructed.
        Tests inject a ``MemoryOscClient`` which also accepts ``close``.
        """
        if self._osc_client is not None:
            self._osc_client.close()
            self._osc_client = None

    def events_for_bar(self, bar_idx: int) -> list[Event]:
        chord_root = self.root_provider.root_semitones_for_bar(bar_idx)

        # Compute part-level progress + intensity (Tension-scaled).
        # Shared between all voices for this bar.
        part_bars = max(1, self.part.bars)
        if part_bars > 1:
            part_progress = (bar_idx % part_bars) / (part_bars - 1)
        else:
            part_progress = 1.0
        intensity_raw = self.part.intensity_start + (
            self.part.intensity_end - self.part.intensity_start
        ) * part_progress
        tension = float(self.song.feel.get("tension", 0.0))
        part_intensity = max(
            0.0,
            min(1.0, 0.5 + (intensity_raw - 0.5) * (0.5 + tension * 1.5)),
        )
        # Single shared dict so LFO global_feel: mutations broadcast to
        # every voice for this bar.
        shared_song_feel: dict[str, float] = {k: float(v) for k, v in self.song.feel.items()}

        # Build BarContext per voice + collect for LFO application.
        contexts: dict[str, BarContext] = {}
        for v in self._voices:
            pv_seed = derive_part_voice_seed(self.song_seed, self.part_name, v.name)
            bar_seed = derive_bar_seed(pv_seed, bar_idx)
            import random as _r

            song_voice = self.song.voices[v.name]
            pattern_knobs, mix_knobs = self._resolve_knobs(v.name, song_voice)
            # ``follow_progression`` lets a voice opt out of the chord
            # progression resolver — useful for sub bass that drones
            # on the root while pads/stabs cycle through changes.
            follow = bool(pattern_knobs.get("follow_progression", True))
            voice_chord_root = chord_root if follow else 0
            contexts[v.name] = BarContext(
                bar_index=bar_idx,
                tick_offset=bar_idx * self.ticks_per_bar,
                ticks_per_bar=self.ticks_per_bar,
                tempo_bpm=self.song.tempo,
                ppq=self.ppq,
                key=self.song.key,
                chord_root_semitones=voice_chord_root,
                pattern_knobs=pattern_knobs,
                mix_knobs=mix_knobs,
                song_feel=shared_song_feel,
                part_progress=part_progress,
                part_intensity=part_intensity,
                rng=_r.Random(bar_seed),
                part_voice_seed=pv_seed,
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

        # Compile song-wide feel knobs (Pump) into per-voice mix knobs.
        # Runs after LFOs so global_feel: LFO targets are reflected in
        # the snapshot. Explicit user values in ``ctx.mix_knobs`` win on
        # key collision — synthetic Pump only fills in unset keys.
        synthetic_mix = compile_global_feel(
            shared_song_feel,
            [(v.name, v.slot) for v in self._voices],
        )
        for v in self._voices:
            voice_synthetic = synthetic_mix.get(v.name)
            if voice_synthetic:
                merge_synthetic_into_mix(contexts[v.name].mix_knobs, voice_synthetic)

        # Did the caller request consecutive bars? Only then does the
        # cached previous bar count as "history" for cross-bar lookback.
        # If they jumped (e.g. asked for bar 5 cold), prev = empty.
        expected_prev = (bar_idx - 1) % self.part.bars if self.part.bars > 0 else None
        if self._last_bar is not None and self._last_bar == expected_prev:
            prev_voice_events = self._prev_voice_events
        else:
            prev_voice_events = {}

        # Run algorithms in topological order; feed follower source_events.
        # The voicing stage immediately translates abstract events
        # (Hit/Note/Param/PolyAftertouch) to concrete MIDI so the mix
        # pass and feel pass can operate on a uniform representation.
        # Legacy algorithms that emit concrete MIDI directly pass
        # through unchanged.
        raw_voice_events: dict[str, list[Event]] = {}
        for v in self._voices:
            ctx = contexts[v.name]
            if v.algorithm_name == "voice_follower":
                src = self.song.voices[v.name].pattern.get("source")
                if isinstance(src, str):
                    ctx.source_events = raw_voice_events.get(src, [])
                    ctx.prev_source_events = prev_voice_events.get(src)
            algo_out = v.algorithm.generate_bar(ctx)
            raw_voice_events[v.name] = translate_abstract_events(algo_out, v.slot)

        # Mix pass — sidechain ducking (cross-voice, cross-bar) +
        # fade-in/out envelope per voice. Runs before the per-voice
        # feel pass so jitter / accent layer on top of the ducked /
        # faded velocities.
        mix_knobs_by_voice = {v.name: contexts[v.name].mix_knobs for v in self._voices}
        mixed_voice_events = apply_mix_pass(
            raw_voice_events,
            prev_voice_events,
            mix_knobs_by_voice,
            bar_idx,
            self.ticks_per_bar,
            self.ppq,
            part_bars=self.part.bars,
        )

        # Feel post-emit pass per voice (bar-internal jitter/accent/swing).
        # Then route through the parameter router for CC remapping +
        # MPE channel allocation.
        voice_events: dict[str, list[Event]] = {}
        for v in self._voices:
            ctx = contexts[v.name]
            shaped = apply_feel(mixed_voice_events[v.name], ctx.mix_knobs, self.ppq, ctx.rng)
            voice_events[v.name] = self._routers[v.name].route(shaped)

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
        """Return (pattern, mix) merged with any part override.

        Resolution order: part override > song-level > algorithm default.
        Algorithm defaults are baked into algorithm code (each
        ``knobs.get(name, default)``), so this method only handles the
        explicit-override layer.
        """
        override: VoiceOverride | None = self.part.voice_overrides.get(voice_name)
        pattern: dict[str, Any] = dict(song_voice.pattern)
        mix: dict[str, Any] = dict(song_voice.mix)
        if override is not None:
            pattern.update(override.pattern)
            mix.update(override.mix)
        return pattern, mix
