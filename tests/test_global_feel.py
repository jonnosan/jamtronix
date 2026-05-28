"""Tests for :mod:`jtx.engine.global_feel`.

Pump is the only song-wide feel knob that compiles to synthetic
per-voice mix knobs. Groove / Drive / Wander are handled by the
post-emit feel pass; Tension is applied directly in SongPlayer.
"""

from __future__ import annotations

from jtx.engine.global_feel import (
    PUMP_SOURCE_INSTRUMENT,
    compile_global_feel,
    merge_synthetic_into_mix,
)
from jtx.model.setup import KitPiece, VoiceSlot


def _kit_slot(name: str = "kit") -> VoiceSlot:
    return VoiceSlot(
        name=name,
        type="drum_kit",
        default_role="drum_kit",
        midi_channel=10,
        kit_map={
            "kick": KitPiece(note=36, channel=10),
            "snare": KitPiece(note=38, channel=10),
        },
    )


def _mono_slot(name: str, channel: int = 2) -> VoiceSlot:
    return VoiceSlot(name=name, type="mono", default_role="bass", midi_channel=channel)


def _kick_slot(name: str = "kick") -> VoiceSlot:
    return VoiceSlot(
        name=name,
        type="drum",
        default_role="drum",
        midi_channel=10,
        note=36,
    )


# ---------------------------------------------------------- compile_global_feel


def test_pump_zero_synthesizes_nothing() -> None:
    out = compile_global_feel(
        {"pump": 0.0, "groove": 0.5, "drive": 0.5},
        [("kit", _kit_slot()), ("acid", _mono_slot("acid"))],
    )
    assert out == {}


def test_pump_above_zero_synthesizes_sidechain_for_non_kit_voices() -> None:
    out = compile_global_feel(
        {"pump": 0.5},
        [("kit", _kit_slot()), ("acid", _mono_slot("acid"))],
    )
    assert "kit" not in out  # drum_kit voice is skipped
    assert "acid" in out
    knobs = out["acid"]
    assert knobs["sidechain_from"] == [PUMP_SOURCE_INSTRUMENT]
    assert knobs["sidechain_release_beats"] == 0.5
    # pump=0.5 → floor = 127 - 40 = 87
    assert knobs["sidechain_floor"] == 87


def test_pump_one_pushes_floor_to_minimum() -> None:
    out = compile_global_feel(
        {"pump": 1.0},
        [("bass", _mono_slot("bass"))],
    )
    # pump=1.0 → floor = 127 - 80 = 47
    assert out["bass"]["sidechain_floor"] == 47


def test_pump_skips_standalone_kick_voice() -> None:
    """A voice literally named ``kick`` is its own trigger — can't sidechain itself."""
    out = compile_global_feel(
        {"pump": 0.5},
        [
            ("kick", _kick_slot()),
            ("acid", _mono_slot("acid")),
        ],
    )
    assert "kick" not in out
    assert "acid" in out


def test_pump_clamps_negative_and_super_unit_values() -> None:
    """song_feel values should always be in [0,1], but if not, behave sanely."""
    assert compile_global_feel({"pump": -0.5}, [("v", _mono_slot("v"))]) == {}
    out = compile_global_feel({"pump": 2.0}, [("v", _mono_slot("v"))])
    # Clamped to 1.0 → floor = 47
    assert out["v"]["sidechain_floor"] == 47


def test_pump_missing_in_song_feel_is_no_op() -> None:
    assert compile_global_feel({"groove": 0.5}, [("v", _mono_slot("v"))]) == {}


def test_pump_handles_empty_voice_list() -> None:
    assert compile_global_feel({"pump": 0.7}, []) == {}


# ---------------------------------------------------------- merge_synthetic_into_mix


def test_explicit_user_value_wins_over_synthetic() -> None:
    explicit = {
        "sidechain_from": ["snare"],  # user override
        "fade_in_at_bar": 2,  # untouched by Pump
    }
    synthetic = {
        "sidechain_from": ["kick"],
        "sidechain_floor": 60,
        "sidechain_release_beats": 0.5,
    }
    merged = merge_synthetic_into_mix(explicit, synthetic)
    # User's "snare" sidechain wins.
    assert merged["sidechain_from"] == ["snare"]
    # User didn't set floor / release, so synthetic fills them in.
    assert merged["sidechain_floor"] == 60
    assert merged["sidechain_release_beats"] == 0.5
    # Unrelated keys untouched.
    assert merged["fade_in_at_bar"] == 2


def test_merge_returns_same_dict_for_chaining() -> None:
    explicit: dict = {}
    out = merge_synthetic_into_mix(explicit, {"a": 1})
    assert out is explicit
    assert explicit == {"a": 1}


# ---------------------------------------------------------- end-to-end via SongPlayer


def test_song_player_applies_synthetic_pump_to_voice_mix_knobs() -> None:
    """Compile is invoked during ``events_for_bar`` so the mix pass sees Pump."""
    from jtx.engine.events import NoteOn
    from jtx.model.setup import Setup
    from jtx.model.song import ChordProgression, Key, Part, Song, VoiceConfig
    from jtx.player import SongPlayer

    setup = Setup(
        id="t",
        name="t",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(name="kick", type="drum", default_role="drum", midi_channel=10, note=36),
            VoiceSlot(name="acid", type="mono", default_role="bass", midi_channel=2),
        ],
    )

    def _song(pump: float) -> Song:
        return Song(
            title="Pump Test",
            setup_ref="t",
            key=Key("A", "minor"),
            tempo=124,
            chord_progression=ChordProgression(degrees=["i"], bars_per_chord=4),
            voices={
                "kick": VoiceConfig(
                    algorithm="drum_pattern", pattern={"style": "four_floor"}
                ),
                "acid": VoiceConfig(
                    algorithm="acid_bass",
                    pattern={"drop_prob": 0.0, "bend": 0, "cycle": 0},
                ),
            },
            parts={"drop": Part(bars=4)},
            arrangement=["drop"],
            feel={"pump": pump},
        )

    no_pump = SongPlayer(_song(0.0), setup, "drop").events_for_bar(0)
    full_pump = SongPlayer(_song(1.0), setup, "drop").events_for_bar(0)

    # Acid NoteOns should be quieter (on average) under Pump=1 than Pump=0
    # because Pump synthesizes sidechain_from=["kick"]. The mix pass
    # (still keyed by voice name in v3.0) sees a voice literally named
    # "kick" and ducks acid NoteOns near each kick. Under task #6 this
    # will become instrument-name lookup; today it only ducks when a
    # voice happens to be named "kick".
    acid_pumped = [
        e.velocity for e in full_pump if isinstance(e, NoteOn) and e.channel == 2
    ]
    acid_dry = [
        e.velocity for e in no_pump if isinstance(e, NoteOn) and e.channel == 2
    ]
    assert acid_dry, "expected acid bass notes in dry render"
    assert acid_pumped, "expected acid bass notes in pumped render"
    assert sum(acid_pumped) < sum(acid_dry)


def test_song_player_user_sidechain_override_wins_over_pump() -> None:
    """An explicit ``sidechain_from`` on a voice's mix dict is preserved."""
    from jtx.engine.events import NoteOn
    from jtx.model.setup import Setup
    from jtx.model.song import (
        ChordProgression,
        Key,
        Part,
        Song,
        VoiceConfig,
    )
    from jtx.player import SongPlayer

    setup = Setup(
        id="t",
        name="t",
        default_midi_port="IAC",
        voices=[
            VoiceSlot(name="kick", type="drum", default_role="drum", midi_channel=10, note=36),
            VoiceSlot(name="snare", type="drum", default_role="drum", midi_channel=10, note=38),
            VoiceSlot(name="acid", type="mono", default_role="bass", midi_channel=2),
        ],
    )
    song = Song(
        title="Override Test",
        setup_ref="t",
        key=Key("A", "minor"),
        tempo=124,
        chord_progression=ChordProgression(degrees=["i"], bars_per_chord=4),
        voices={
            "kick": VoiceConfig(algorithm="drum_pattern", pattern={"style": "four_floor"}),
            "snare": VoiceConfig(
                algorithm="drum_pattern",
                pattern={"style": "euclid", "pulses": 2, "offset": 4},
            ),
            "acid": VoiceConfig(
                algorithm="acid_bass",
                pattern={"drop_prob": 0.0, "bend": 0, "cycle": 0},
                # User explicitly opts out of kick-side sidechain by
                # routing sidechain_from to an empty source list.
                mix={"sidechain_from": []},
            ),
        },
        parts={"drop": Part(bars=4)},
        arrangement=["drop"],
        feel={"pump": 1.0},
    )
    player = SongPlayer(song, setup, "drop")
    # No ducking on acid because user's explicit empty list wins.
    events = player.events_for_bar(0)
    acid_ons = [e for e in events if isinstance(e, NoteOn) and e.channel == 2]
    # Velocities should match the raw algorithm output (not pulled toward the
    # synthesized sidechain floor of 47).
    assert all(v.velocity > 50 for v in acid_ons), [v.velocity for v in acid_ons]
