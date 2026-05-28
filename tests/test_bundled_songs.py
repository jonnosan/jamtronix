"""Integration test: the bundled test-fixture song renders cleanly.

Covers the regression risk that the recent cc_lfo retirement + LFO
sub-bar sampling + voice:<v>:<fn> target migration breaks the filter
sweep that any bundled .jtx / .jtx-setup pair relies on. Loads the
fixture, instantiates a SongPlayer for the first part, renders bar 0,
and asserts:

* No exceptions during construction or rendering.
* The filter voice receives CC74 events on its configured channel.
* The song produces at least one pitched NoteOn (i.e. it actually plays).

Prior to PR #120 this exercised five per-style demo songs (acid /
deep_techno / psytrance starters + demos). Those were deleted along
with the style-specific setups; one canonical fixture covers the
same surface.
"""

from __future__ import annotations

from pathlib import Path

from jtx.engine.events import ControlChange, NoteOn
from jtx.persist.json_io import load_setup, load_song
from jtx.player import SongPlayer

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_STEM = "test-fixture"


def test_bundled_song_renders_bar0() -> None:
    song = load_song(REPO_ROOT / "examples" / f"{FIXTURE_STEM}.jtx")
    setup = load_setup(REPO_ROOT / "examples" / f"{FIXTURE_STEM}.jtx-setup")
    part = song.arrangement[0] if song.arrangement else next(iter(song.parts))
    player = SongPlayer(song, setup, part)
    try:
        events = player.events_for_bar(0)
    finally:
        player.close()
    note_ons = [e for e in events if isinstance(e, NoteOn)]
    assert note_ons, f"{FIXTURE_STEM}: bar 0 emitted no NoteOns"


def test_bundled_song_filter_lfo_routes_to_cc74() -> None:
    """The bundled fixture's filter LFO should produce CC74 events on the
    filter slot's MIDI channel — the migration from cc_lfo voices to
    song-level voice:filter:cutoff LFOs preserves the sweep."""
    song = load_song(REPO_ROOT / "examples" / f"{FIXTURE_STEM}.jtx")
    setup = load_setup(REPO_ROOT / "examples" / f"{FIXTURE_STEM}.jtx-setup")
    filter_slot = setup.voice("filter")
    assert filter_slot is not None, f"{FIXTURE_STEM}: no filter voice in setup"

    part = song.arrangement[0] if song.arrangement else next(iter(song.parts))
    player = SongPlayer(song, setup, part)
    try:
        events = player.events_for_bar(0)
    finally:
        player.close()

    filter_cc74 = [
        e
        for e in events
        if isinstance(e, ControlChange) and e.cc == 74 and e.channel == filter_slot.midi_channel
    ]
    assert filter_cc74, (
        f"{FIXTURE_STEM}: no CC74 events on filter channel {filter_slot.midi_channel}; "
        f"the voice:filter:cutoff LFO is not reaching the wire"
    )
