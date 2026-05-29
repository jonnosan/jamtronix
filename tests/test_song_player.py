"""End-to-end tests for SongPlayer — Song + Setup → BarGenerator."""

from __future__ import annotations

from jtx.engine.events import ControlChange, NoteOn
from jtx.engine.scheduler import Scheduler
from jtx.engine.sink import MemorySink
from jtx.model.events import Hit, Note, Param
from jtx.model.lfo import LFO, LFOApplication
from jtx.model.setup import Setup, VoiceSlot
from jtx.model.song import (
    ChordProgression,
    Key,
    Part,
    Song,
    VoiceConfig,
    VoiceOverride,
)
from jtx.player import SongPlayer


def _basic_setup() -> Setup:
    return Setup(
        id="iac",
        name="IAC test",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(
                name="kick",
                type="drum",
                default_role="drum",
                midi_channel=10,
                kit_map={"kick": 36},
            ),
            VoiceSlot(name="acid", type="mono", default_role="bass", midi_channel=2),
            VoiceSlot(name="echo", type="follower", default_role="follower", midi_channel=4),
        ],
    )


def _basic_song() -> Song:
    return Song(
        title="Phuture Test",
        setup_ref="iac",
        key=Key(tonic="A", scale="minor"),
        tempo=124,
        meter="4/4",
        chord_progression=ChordProgression(degrees=["i", "VI", "III", "VII"], bars_per_chord=4),
        voices={
            "kick": VoiceConfig(algorithm="drum_pattern", pattern={"style": "four_floor"}),
            "acid": VoiceConfig(
                algorithm="acid_bass",
                pattern={"drop_prob": 0.0, "bend": 0, "cycle": 0},
            ),
            "echo": VoiceConfig(
                algorithm="voice_follower",
                pattern={"source": "acid", "transpose_octaves": 1},
            ),
        },
        parts={
            "drop": Part(bars=4),
        },
        arrangement=["drop"],
    )


def test_song_player_emits_events_for_bar() -> None:
    player = SongPlayer(_basic_song(), _basic_setup(), "drop")
    events = player.events_for_bar(0)
    assert events  # something gets emitted
    # Kick should fire 4-on-floor (4 NoteOns on channel 10).
    kick_ons = [e for e in events if isinstance(e, NoteOn) and e.channel == 10]
    assert len(kick_ons) == 4


def test_song_player_is_deterministic_across_runs() -> None:
    """Same song + setup + part + bar → identical events.

    This is the v1 reproducibility contract: a (title, seed, song state)
    triple always plays the same way.
    """
    p1 = SongPlayer(_basic_song(), _basic_setup(), "drop")
    p2 = SongPlayer(_basic_song(), _basic_setup(), "drop")
    for bar in range(4):
        assert p1.events_for_bar(bar) == p2.events_for_bar(bar)


def test_song_player_follower_derives_from_source() -> None:
    """The follower (echo, +1 octave) should mirror the acid bass's notes."""
    player = SongPlayer(_basic_song(), _basic_setup(), "drop")
    events = player.events_for_bar(0)
    acid_ons = sorted(
        (e for e in events if isinstance(e, NoteOn) and e.channel == 2),
        key=lambda e: e.tick,
    )
    echo_ons = sorted(
        (e for e in events if isinstance(e, NoteOn) and e.channel == 4),
        key=lambda e: e.tick,
    )
    # Same count (passthrough latch by default).
    assert len(echo_ons) == len(acid_ons)
    # Same ticks; pitches +12.
    for a, e in zip(acid_ons, echo_ons, strict=True):
        assert e.tick == a.tick
        assert e.note == a.note + 12


def test_song_player_chord_progression_drives_chord_root() -> None:
    """Bar 4 sits on VI (=+8 semitones in A minor), so acid root rises."""
    player = SongPlayer(_basic_song(), _basic_setup(), "drop")
    bar0 = [e for e in player.events_for_bar(0) if isinstance(e, NoteOn) and e.channel == 2]
    bar4 = [e for e in player.events_for_bar(4) if isinstance(e, NoteOn) and e.channel == 2]
    # Bar 0 chord_root=0 → acid plays A2=45 (root) / A3=57 (octave) / C3=48 (m3).
    # Bar 4 chord_root=8 → acid plays F3=53 / F4=65 / Ab3=56.
    assert all(n.note in {45, 48, 57} for n in bar0)
    assert all(n.note in {53, 56, 65} for n in bar4)


def test_song_player_voice_override_applies_per_part() -> None:
    song = _basic_song()
    song.parts["drop"] = Part(
        bars=4,
        voice_overrides={
            "acid": VoiceOverride(pattern={"drop_prob": 1.0}),  # silence the bass
        },
    )
    player = SongPlayer(song, _basic_setup(), "drop")
    events = player.events_for_bar(0)
    acid_ons = [e for e in events if isinstance(e, NoteOn) and e.channel == 2]
    assert acid_ons == []
    # Kick should still fire.
    kick_ons = [e for e in events if isinstance(e, NoteOn) and e.channel == 10]
    assert kick_ons


def test_song_player_emits_lfo_midi_cc_events() -> None:
    song = _basic_song()
    song.lfos = [
        LFO(
            name="sweep",
            shape="square",
            period_bars=1.0,
            depth=1.0,
            applications=[LFOApplication(part="drop", target="midi:ch2:cc74")],
        )
    ]
    player = SongPlayer(song, _basic_setup(), "drop")
    events = player.events_for_bar(0)
    lfo_ccs = [e for e in events if isinstance(e, ControlChange) and e.cc == 74 and e.tick == 0]
    # square wave at phase 0 = high → CC value 127.
    assert lfo_ccs and lfo_ccs[0].value == 127


def test_song_player_rejects_unknown_part() -> None:
    import pytest

    with pytest.raises(ValueError, match="not in song"):
        SongPlayer(_basic_song(), _basic_setup(), "ghost")


def test_song_player_rejects_voice_missing_from_setup() -> None:
    import pytest

    song = _basic_song()
    song.voices["ghost"] = VoiceConfig(algorithm="acid_bass")
    with pytest.raises(ValueError, match="not in setup"):
        SongPlayer(song, _basic_setup(), "drop")


def test_song_player_drives_scheduler_into_memory_sink() -> None:
    """Full integration: SongPlayer.bar_generator → Scheduler.run → MemorySink."""

    class FakeClock:
        ppq = 480

        def tempo_bpm(self) -> float:
            return 124.0

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def now_tick(self) -> int:
            return 0

        def wait_until(self, target_tick: int) -> None:
            pass

    sink = MemorySink()
    player = SongPlayer(_basic_song(), _basic_setup(), "drop")
    Scheduler(FakeClock(), sink).run(
        bar_count=4, ticks_per_bar=1920, bar_generator=player.bar_generator()
    )
    assert sink.events  # at least one event emitted
    note_ons = [e for e in sink.events if isinstance(e, NoteOn)]
    # 4 bars × 4 kicks = at least 16 kick note-ons.
    kick_ons = [e for e in note_ons if e.channel == 10]
    assert len(kick_ons) >= 16


def test_song_player_chained_followers_order() -> None:
    """Follower B sourced from Follower A: A must run before B."""
    setup = _basic_setup()
    setup.voices.append(
        VoiceSlot(name="echo2", type="follower", default_role="follower", midi_channel=5)
    )
    song = _basic_song()
    song.voices["echo2"] = VoiceConfig(
        algorithm="voice_follower",
        pattern={"source": "echo", "transpose_octaves": -1},
    )
    player = SongPlayer(song, setup, "drop")
    events = player.events_for_bar(0)
    # echo2 = echo - 12 = acid + 0. So echo2 ticks should match acid.
    acid_ticks = sorted(e.tick for e in events if isinstance(e, NoteOn) and e.channel == 2)
    echo2_ticks = sorted(e.tick for e in events if isinstance(e, NoteOn) and e.channel == 5)
    assert acid_ticks == echo2_ticks


def test_song_player_routes_osc_target_via_injected_client() -> None:
    """A voice with an OscTarget produces no MIDI CC; the injected client sees it."""
    from jtx.engine.osc_client import MemoryOscClient
    from jtx.model.parameter_target import OscTarget

    setup = Setup(
        id="osc-test",
        name="OSC test",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(
                name="acid",
                type="mono",
                default_role="bass",
                midi_channel=2,
                parameter_map={"cutoff": OscTarget("/jtx/acid/cutoff")},
            ),
        ],
    )
    song = Song(
        title="OSC Probe",
        setup_ref="osc-test",
        key=Key(tonic="A", scale="minor"),
        tempo=120,
        meter="4/4",
        voices={
            "acid": VoiceConfig(
                algorithm="acid_bass",
                pattern={"drop_prob": 0.0, "cycle": 2, "bend": 0},
            ),
        },
        parts={"main": Part(bars=1)},
        arrangement=["main"],
    )
    osc = MemoryOscClient()
    player = SongPlayer(song, setup, "main", osc_client=osc)
    events = player.events_for_bar(0)
    # The cutoff LFO is OSC-routed, so no CC 74 events should land in MIDI.
    assert all(not (isinstance(e, ControlChange) and e.function == "cutoff") for e in events)
    # And the OSC client captured the messages.
    assert any(addr == "/jtx/acid/cutoff" for addr, _ in osc.sent)
    # Values stay in the 0..1 normalised range.
    assert all(0.0 <= v <= 1.0 for _, v in osc.sent)
    player.close()


def test_song_player_renders_song_with_rest_voice() -> None:
    """A voice declaring algorithm='rest' contributes no events but
    doesn't break the rest of the song. Other voices still play."""
    setup = _basic_setup()
    song = _basic_song()
    # Swap the follower voice to a rest — it should silently drop out
    # without affecting kick / acid playback.
    song.voices["echo"] = VoiceConfig(algorithm="rest")
    player = SongPlayer(song, setup, "drop")
    try:
        events = player.events_for_bar(0)
    finally:
        player.close()
    # Kick should still fire 4-on-floor.
    kick_ons = [e for e in events if isinstance(e, NoteOn) and e.channel == 10]
    assert len(kick_ons) == 4
    # Echo (was channel 4) should produce no NoteOns now that it's rest.
    echo_ons = [e for e in events if isinstance(e, NoteOn) and e.channel == 4]
    assert echo_ons == []


def test_song_player_routes_lfo_voice_target_to_phantom_slot() -> None:
    """A song-level LFO with voice:<slot>:<fn> can drive a setup slot
    that has no song-level VoiceConfig — the phantom slot acts as a
    routing destination only.
    """
    from jtx.model import CCTarget

    setup = Setup(
        id="t",
        name="t",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(name="acid", type="mono", default_role="bass", midi_channel=2),
            # Phantom modulator slot — no song.voices entry, but has a
            # parameter_map so the voice:filter:cutoff LFO routes to CC74.
            VoiceSlot(
                name="filter",
                type="modulator",
                default_role="modulator",
                midi_channel=5,
                parameter_map={"cutoff": CCTarget(74)},
            ),
        ],
    )
    song = Song(
        title="Phantom Filter",
        setup_ref="t",
        key=Key(tonic="A", scale="minor"),
        chord_progression=ChordProgression(degrees=["i"], bars_per_chord=1),
        voices={
            "acid": VoiceConfig(
                algorithm="acid_bass",
                pattern={"drop_prob": 1.0, "bend": 0, "cycle": 0},
            ),
        },
        parts={"main": Part(bars=1)},
        arrangement=["main"],
        lfos=[
            LFO(
                name="filt_sweep",
                shape="saw",
                period_bars=4.0,
                samples_per_bar=8,
                applications=[LFOApplication(part="main", target="voice:filter:cutoff")],
            )
        ],
    )
    player = SongPlayer(song, setup, "main")
    events = player.events_for_bar(0)
    # Eight CC events on the filter slot's channel routed to CC 74.
    filter_ccs = [
        e for e in events if isinstance(e, ControlChange) and e.channel == 5 and e.cc == 74
    ]
    assert len(filter_ccs) == 8
    player.close()


def test_abstract_events_for_bar_returns_per_voice_semantic_events() -> None:
    """The evaluation tap point: abstract events grouped by voice,
    carrying semantic instrument and parameter-function names.
    """
    player = SongPlayer(_basic_song(), _basic_setup(), "drop")
    abstract = player.abstract_events_for_bar(0)

    # Voice grouping matches the song.
    assert set(abstract.keys()) == {"kick", "acid", "echo"}

    # Kick voice (drum_pattern) emits Hit events instrument-tagged.
    kick_hits = [e for e in abstract["kick"] if isinstance(e, Hit)]
    assert kick_hits, "kick should emit Hit events"
    assert all(h.instrument == "kick" for h in kick_hits)

    # Acid voice emits Note events (pitched, MIDI-naive — no channel).
    acid_notes = [e for e in abstract["acid"] if isinstance(e, Note)]
    assert acid_notes, "acid_bass should emit Note events"
    for n in acid_notes:
        assert 0 <= n.pitch <= 127
        assert 1 <= n.velocity <= 127

    # Acid voice may also emit Param events with semantic function names
    # (e.g. "cutoff", "resonance"). They must not be pre-resolved to CC#.
    params = [e for e in abstract["acid"] if isinstance(e, Param)]
    for p in params:
        assert isinstance(p.name, str) and p.name
        assert not p.name.startswith("cc")  # function name, not CC number


def test_abstract_events_for_bar_is_deterministic() -> None:
    """Same song + setup + bar → identical abstract events across runs."""
    p1 = SongPlayer(_basic_song(), _basic_setup(), "drop")
    p2 = SongPlayer(_basic_song(), _basic_setup(), "drop")
    a1 = p1.abstract_events_for_bar(0)
    a2 = p2.abstract_events_for_bar(0)
    assert a1 == a2


def test_abstract_events_for_bar_matches_events_for_bar_algo_phase() -> None:
    """The new tap returns the same per-voice algorithm output that
    feeds into events_for_bar's mix/feel/voicing pipeline. We can't
    compare directly to events_for_bar's MIDI output (different shape),
    but we can verify that the abstract-events Note pitches are present
    in the MIDI NoteOns for the same bar on a different player instance.
    """
    p_abstract = SongPlayer(_basic_song(), _basic_setup(), "drop")
    abstract = p_abstract.abstract_events_for_bar(0)
    acid_pitches = sorted(n.pitch for n in abstract["acid"] if isinstance(n, Note))

    p_midi = SongPlayer(_basic_song(), _basic_setup(), "drop")
    events = p_midi.events_for_bar(0)
    # acid is on channel 2 (per _basic_setup).
    midi_acid_pitches = sorted(
        e.note for e in events if isinstance(e, NoteOn) and e.channel == 2
    )
    assert acid_pitches == midi_acid_pitches
