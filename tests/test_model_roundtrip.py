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
    ChordProgression,
    Key,
    LFOApplication,
    Part,
    Setup,
    Song,
    ValidationError,
    VoiceConfig,
    VoiceOverride,
    VoiceSlot,
)
from jtx.persist import load_setup, load_song, save_setup, save_song


def _sample_setup() -> Setup:
    return Setup(
        id="iac-default",
        name="IAC Bus 1",
        default_midi_port="IAC Bus 1",
        daw_template_path=None,
        voices=[
            VoiceSlot(
                name="kick",
                type="drum",
                default_role="drum",
                midi_channel=10,
                kit_map={"kick": 36, "snare": 38, "hat": 42},
            ),
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
                feel={"swing": 6},
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
