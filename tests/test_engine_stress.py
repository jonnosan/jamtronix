"""The bundled engine-stress-test song hits every channel in the
``ableton`` setup so users can verify their Live wiring end-to-end.

This pins the song's channel coverage: every musical voice (bass /
sub / lead / pad / chord / arp / stabs / fx + drum-kit groups), the
filter modulator's CC74 stream, and both pitch-follower references
must produce at least one event per loop. If a composer change ever
silences one of these channels, this test catches it.
"""

from __future__ import annotations

from pathlib import Path

from jtx.engine.events import ControlChange, NoteOn
from jtx.persist import load_setup, load_song
from jtx.player import SongPlayer

REPO_ROOT = Path(__file__).resolve().parent.parent
SONG_PATH = REPO_ROOT / "examples" / "engine-stress-test.jtx"
SETUP_PATH = REPO_ROOT / "setups" / "ableton.jtx-setup"

# Every channel the ableton setup uses for note traffic.
_EXPECTED_NOTE_CHANNELS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 16}


def test_engine_stress_song_exercises_every_note_channel() -> None:
    """Across one full loop, every voice's channel must see at least one NoteOn."""
    song = load_song(SONG_PATH)
    setup = load_setup(SETUP_PATH)
    part_name = song.arrangement[0]
    bars = song.parts[part_name].bars

    player = SongPlayer(song, setup, part_name)
    try:
        seen: set[int] = set()
        for bar in range(bars):
            for ev in player.events_for_bar(bar):
                if isinstance(ev, NoteOn):
                    seen.add(ev.channel)
    finally:
        player.close()

    missing = _EXPECTED_NOTE_CHANNELS - seen
    assert not missing, f"channels with no NoteOn over the full loop: {sorted(missing)}"


def test_engine_stress_song_filter_modulator_emits_cc74() -> None:
    """The filter utility voice must stream CC74 on its channel (12)."""
    song = load_song(SONG_PATH)
    setup = load_setup(SETUP_PATH)
    filter_slot = setup.voice("filter")
    assert filter_slot is not None

    part_name = song.arrangement[0]
    bars = song.parts[part_name].bars

    player = SongPlayer(song, setup, part_name)
    try:
        cc74_count = 0
        for bar in range(bars):
            for ev in player.events_for_bar(bar):
                if (
                    isinstance(ev, ControlChange)
                    and ev.cc == 74
                    and ev.channel == filter_slot.midi_channel
                ):
                    cc74_count += 1
    finally:
        player.close()

    assert cc74_count > 0, (
        f"no CC74 on filter ch{filter_slot.midi_channel} — the modulator is silent"
    )
