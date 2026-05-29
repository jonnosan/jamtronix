"""JSON round-trip tests for songs and setups.

Builds a non-trivial Song + Setup, writes them to a tempfile, reads them
back, and asserts byte-for-byte equality of the in-memory objects. Also
covers validation: invalid songs must be rejected at load time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.model import (
    LFO,
    SCHEMA_VERSION,
    ChordProgression,
    Key,
    LFOApplication,
    MoodSpec,
    Part,
    Setup,
    Song,
    ValidationError,
    VoiceConfig,
    VoiceOverride,
    VoiceSlot,
)
from jtx.model.setup import KitPiece
from jtx.persist import load_setup, load_song, save_setup, save_song
from jtx.persist.json_io import song_from_dict


def _sample_setup() -> Setup:
    return Setup(
        id="iac-default",
        name="IAC Bus 1",
        default_midi_port="IAC Bus 1",
        daw_template_path=None,
        voices=[
            VoiceSlot(
                name="kit",
                type="drum_kit",
                default_role="drum_kit",
                midi_channel=10,
                kit_map={
                    "kick": KitPiece(note=36, channel=10),
                    "snare": KitPiece(note=38, channel=10),
                    "hat": KitPiece(note=42, channel=10),
                },
            ),
            VoiceSlot(name="kick", type="drum", default_role="drum", midi_channel=10, note=36),
            VoiceSlot(name="acid", type="mono", default_role="bass", midi_channel=2),
            VoiceSlot(name="organ", type="poly", default_role="stab", midi_channel=3),
            VoiceSlot(name="filt", type="modulator", default_role="modulator", midi_channel=2),
            VoiceSlot(name="echo", type="follower", default_role="follower", midi_channel=4),
        ],
    )


def _sample_song() -> Song:
    return Song(
        title="Phuture Test",
        setup_ref="iac-default",
        key=Key(tonic="A", scale="minor"),
        meter="4/4",
        tempo=122,
        chord_progression=ChordProgression(degrees=["i", "VI", "III", "VII"], bars_per_chord=4),
        voices={
            "kick": VoiceConfig(algorithm="drum_pattern", pattern={"style": "four_floor"}),
            "acid": VoiceConfig(
                algorithm="acid_bass",
                pattern={"slide_prob": 0.4, "octave": 2},
                mix={"sidechain_floor": 80},
            ),
            "organ": VoiceConfig(algorithm="chord_stab", pattern={"steps": [4, 12]}),
            "filt": VoiceConfig(algorithm="cc_lfo", pattern={"cc": 74, "rate_beats": 4}),
            "echo": VoiceConfig(
                algorithm="voice_follower",
                pattern={"source": "acid", "transpose_semitones": 12, "latch": "first_per_bar"},
            ),
        },
        parts={
            "intro": Part(bars=16),
            "drop": Part(
                bars=32,
                voice_overrides={
                    "acid": VoiceOverride(pattern={"slide_prob": 0.8}),
                },
            ),
        },
        arrangement=["intro", "drop", "drop"],
        lfos=[
            LFO(
                name="slow_sweep",
                shape="sine",
                period_bars=8.0,
                depth=0.6,
                applications=[LFOApplication(part="drop", target="midi:ch2:cc74")],
            )
        ],
    )


def test_setup_roundtrip(tmp_path: Path) -> None:
    setup = _sample_setup()
    path = tmp_path / "iac.jtx-setup"
    save_setup(setup, path)
    loaded = load_setup(path)
    assert loaded == setup


def test_song_roundtrip(tmp_path: Path) -> None:
    song = _sample_song()
    path = tmp_path / "phuture.jtx"
    save_song(song, path)
    loaded = load_song(path)
    assert loaded == song


def test_song_mood_format_round_trip(tmp_path: Path) -> None:
    """Mood (MoodSpec) and format (Literal) survive save → load."""
    song = _sample_song()
    song.mood = MoodSpec(valence=0.42, energy=-0.31, chaos=0.7)
    song.format = "anthem"
    path = tmp_path / "moody.jtx"
    save_song(song, path)
    loaded = load_song(path)
    assert loaded.mood == MoodSpec(valence=0.42, energy=-0.31, chaos=0.7)
    assert loaded.format == "anthem"
    assert loaded == song


def test_song_default_mood_format_round_trip(tmp_path: Path) -> None:
    """A song without explicit mood/format round-trips with defaults."""
    song = _sample_song()
    path = tmp_path / "default.jtx"
    save_song(song, path)
    loaded = load_song(path)
    assert loaded.mood == MoodSpec(valence=0.0, energy=0.0, chaos=0.0)
    assert loaded.format == "song"


def test_song_texture_motion_round_trip(tmp_path: Path) -> None:
    """Texture + motion floats survive save → load."""
    song = _sample_song()
    song.texture = 0.73
    song.motion = 0.18
    path = tmp_path / "textured.jtx"
    save_song(song, path)
    loaded = load_song(path)
    assert loaded.texture == 0.73
    assert loaded.motion == 0.18
    assert loaded == song


def test_song_default_texture_motion_round_trip(tmp_path: Path) -> None:
    """A song without explicit texture/motion round-trips at the (0.5, 0.5) centre."""
    song = _sample_song()
    path = tmp_path / "default-tm.jtx"
    save_song(song, path)
    loaded = load_song(path)
    assert loaded.texture == 0.5
    assert loaded.motion == 0.5


def test_song_load_rejects_older_schema_version() -> None:
    """A song dict at the previous SCHEMA_VERSION is rejected (no migration path)."""
    payload = {
        "title": "Old",
        "setup_ref": "iac",
        "key": {"tonic": "A", "scale": "minor"},
        "voices": {},
        "parts": {},
        "arrangement": [],
        "schema_version": SCHEMA_VERSION - 1,
    }
    with pytest.raises(ValidationError, match="schema_version"):
        song_from_dict(payload)


def test_song_load_rejects_texture_out_of_range() -> None:
    payload = {
        "title": "Bad",
        "setup_ref": "iac",
        "key": {"tonic": "A", "scale": "minor"},
        "voices": {},
        "parts": {},
        "arrangement": [],
        "texture": 1.5,
        "schema_version": SCHEMA_VERSION,
    }
    with pytest.raises(ValidationError, match="texture"):
        song_from_dict(payload)


def test_song_load_rejects_motion_out_of_range() -> None:
    payload = {
        "title": "Bad",
        "setup_ref": "iac",
        "key": {"tonic": "A", "scale": "minor"},
        "voices": {},
        "parts": {},
        "arrangement": [],
        "motion": -0.2,
        "schema_version": SCHEMA_VERSION,
    }
    with pytest.raises(ValidationError, match="motion"):
        song_from_dict(payload)


def test_song_load_rejects_unknown_format() -> None:
    payload = {
        "title": "Bogus",
        "setup_ref": "iac",
        "key": {"tonic": "A", "scale": "minor"},
        "voices": {},
        "parts": {},
        "arrangement": [],
        "format": "epic_jam",
        "schema_version": SCHEMA_VERSION,
    }
    with pytest.raises(ValidationError, match="format 'epic_jam'"):
        song_from_dict(payload)


def test_song_validation_rejects_unknown_arrangement_part() -> None:
    song = _sample_song()
    song.arrangement.append("missing")
    with pytest.raises(ValidationError, match="unknown part 'missing'"):
        save_song(song, "/tmp/should-never-write.jtx")


def test_song_validation_rejects_follower_missing_source() -> None:
    song = _sample_song()
    song.voices["echo"].pattern.pop("source")
    with pytest.raises(ValidationError, match="missing 'source'"):
        save_song(song, "/tmp/should-never-write.jtx")


def test_song_validation_rejects_follower_cycle() -> None:
    song = _sample_song()
    # echo follows acid; make acid follow echo too.
    song.voices["acid"] = VoiceConfig(
        algorithm="voice_follower",
        pattern={"source": "echo"},
    )
    with pytest.raises(ValidationError, match="cycle"):
        save_song(song, "/tmp/should-never-write.jtx")


def test_song_validation_rejects_self_follower() -> None:
    song = _sample_song()
    song.voices["echo"].pattern["source"] = "echo"
    with pytest.raises(ValidationError, match="cannot be self"):
        save_song(song, "/tmp/should-never-write.jtx")


def test_song_validation_rejects_unknown_override_voice() -> None:
    song = _sample_song()
    song.parts["drop"].voice_overrides["ghost"] = VoiceOverride(pattern={"x": 1})
    with pytest.raises(ValidationError, match="overrides unknown voice 'ghost'"):
        save_song(song, "/tmp/should-never-write.jtx")


def test_setup_validation_rejects_bad_role_for_type() -> None:
    setup = _sample_setup()
    setup.voices.append(VoiceSlot(name="bad", type="drum", default_role="bass", midi_channel=11))
    with pytest.raises(ValidationError, match="not valid for type 'drum'"):
        save_setup(setup, "/tmp/should-never-write.jtx-setup")


def test_setup_validation_rejects_bad_midi_channel() -> None:
    setup = _sample_setup()
    setup.voices[0].midi_channel = 17
    with pytest.raises(ValidationError, match="midi_channel 17"):
        save_setup(setup, "/tmp/should-never-write.jtx-setup")


def test_load_setup_iac_validates() -> None:
    """The bundled IAC setup loads cleanly."""
    setup = load_setup("setups/iac.jtx-setup")
    assert setup.voices


def test_setup_osc_host_port_round_trip(tmp_path: Path) -> None:
    """osc_host + osc_port round-trip through save_setup / load_setup."""
    setup = _sample_setup()
    setup.osc_host = "192.168.1.50"
    setup.osc_port = 9000
    p = tmp_path / "osc.jtx-setup"
    save_setup(setup, p)
    reloaded = load_setup(p)
    assert reloaded.osc_host == "192.168.1.50"
    assert reloaded.osc_port == 9000


def test_osc_target_round_trips_through_parameter_map(tmp_path: Path) -> None:
    """OscTarget survives the dict-discriminated serializer."""
    from jtx.model import OscTarget

    setup = _sample_setup()
    setup.voices[0].parameter_map["cutoff"] = OscTarget("/jtx/test/cutoff")
    p = tmp_path / "osc-target.jtx-setup"
    save_setup(setup, p)
    reloaded = load_setup(p)
    assert reloaded.voices[0].parameter_map["cutoff"] == OscTarget("/jtx/test/cutoff")


def test_setup_validation_rejects_invalid_osc_port() -> None:
    """osc_port outside 1..65535 is rejected at validate()."""
    setup = _sample_setup()
    setup.osc_port = 0
    with pytest.raises(ValidationError, match="osc_port 0"):
        save_setup(setup, "/tmp/should-never-write.jtx-setup")
