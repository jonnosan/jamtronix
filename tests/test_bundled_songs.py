"""Integration tests: every bundled .jtx + .jtx-setup pair renders cleanly.

Covers the regression risk that the recent cc_lfo retirement + LFO
sub-bar sampling + voice:<v>:<fn> target migration breaks the filter
sweep that the bundled starter / demo songs rely on. Each test loads
the song, instantiates a SongPlayer for the first part, renders bar 0,
and asserts that:

* No exceptions during construction or rendering.
* The filter voice receives CC74 events on its configured channel —
  the new voice:filter:cutoff LFO target routes through the slot's
  parameter_map["cutoff"] = CCTarget(74).
* The song produces at least one pitched NoteOn (i.e. it actually plays).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.engine.events import ControlChange, NoteOn
from jtx.persist.json_io import load_setup, load_song
from jtx.player import SongPlayer

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every bundled .jtx + sibling .jtx-setup pair shipped in examples/.
BUNDLED_SONGS = [
    "acid-starter",
    "deep_techno-starter",
    "psytrance-starter",
    "acid-demo",
    "deep-techno-demo",
]


@pytest.mark.parametrize("stem", BUNDLED_SONGS)
def test_bundled_song_renders_bar0(stem: str) -> None:
    song = load_song(REPO_ROOT / "examples" / f"{stem}.jtx")
    setup = load_setup(REPO_ROOT / "examples" / f"{stem}.jtx-setup")
    part = song.arrangement[0] if song.arrangement else next(iter(song.parts))
    player = SongPlayer(song, setup, part)
    try:
        events = player.events_for_bar(0)
    finally:
        player.close()
    # The song actually plays something — at least one pitched NoteOn.
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert note_ons, f"{stem}: bar 0 emitted no NoteOns"


@pytest.mark.parametrize("stem", BUNDLED_SONGS)
def test_bundled_song_filter_lfo_routes_to_cc74(stem: str) -> None:
    """Every bundled song's filter LFO should produce CC74 events on the
    filter slot's MIDI channel — the migration from cc_lfo voices to
    song-level voice:filter:cutoff LFOs preserves the sweep."""
    song = load_song(REPO_ROOT / "examples" / f"{stem}.jtx")
    setup = load_setup(REPO_ROOT / "examples" / f"{stem}.jtx-setup")
    filter_slot = setup.voice("filter")
    assert filter_slot is not None, f"{stem}: no filter voice in setup"

    part = song.arrangement[0] if song.arrangement else next(iter(song.parts))
    player = SongPlayer(song, setup, part)
    try:
        events = player.events_for_bar(0)
    finally:
        player.close()

    filter_cc74 = [
        e
        for e in events
        if isinstance(e, ControlChange)
        and e.cc == 74
        and e.channel == filter_slot.midi_channel
    ]
    assert filter_cc74, (
        f"{stem}: no CC74 events on filter channel {filter_slot.midi_channel}; "
        f"the voice:filter:cutoff LFO is not reaching the wire"
    )


@pytest.mark.parametrize("stem", BUNDLED_SONGS)
def test_bundled_song_renders_full_arrangement_first_bars(stem: str) -> None:
    """Sanity: the SongPlayer produces events for the first bar of every
    part in the arrangement without raising. Catches part-specific
    voice-override mistakes (e.g. a part overriding a voice the song
    doesn't declare)."""
    song = load_song(REPO_ROOT / "examples" / f"{stem}.jtx")
    setup = load_setup(REPO_ROOT / "examples" / f"{stem}.jtx-setup")
    for part_name in dict.fromkeys(song.arrangement):  # unique, preserve order
        player = SongPlayer(song, setup, part_name)
        try:
            events = player.events_for_bar(0)
        finally:
            player.close()
        # Could legitimately be empty for a "moment of silence" override
        # — but the call must not raise.
        assert isinstance(events, list)
