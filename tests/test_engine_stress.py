"""The bundled engine-stress-test song hits every channel densely
enough that a user wiring up Ableton can verify each track within
a couple of bars of pressing play.

Density rule: every musical voice (bass / sub / lead / pad / chord /
arp / stabs / fx + drum-kit groups) and both pitch-follower
references must fire at least one NoteOn no more than 2 bars apart
across the loop. The filter modulator's CC74 stream must do the
same. If a composer change ever stretches one of these gaps, this
test catches it.
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

# Maximum allowed gap (in bars) between consecutive NoteOns on the
# same channel, across the loop. 2 bars is the user-facing
# verification SLA: hit play, and any silent channel surfaces
# within 2 bars.
_MAX_BAR_GAP = 2


def _max_gap_for_channel(per_bar_channels: list[set[int]], channel: int) -> int:
    """Largest run of consecutive bars where *channel* sees no NoteOn."""
    bars = len(per_bar_channels)
    seen_bars = [i for i, chs in enumerate(per_bar_channels) if channel in chs]
    if not seen_bars:
        return bars
    gaps = [b - a for a, b in zip(seen_bars, seen_bars[1:])]
    return max(gaps) if gaps else 1


def test_engine_stress_song_every_note_channel_fires_within_2_bars() -> None:
    """No channel may go quiet for more than 2 bars across the loop."""
    song = load_song(SONG_PATH)
    setup = load_setup(SETUP_PATH)
    part_name = song.arrangement[0]
    bars = song.parts[part_name].bars

    player = SongPlayer(song, setup, part_name)
    try:
        per_bar: list[set[int]] = [set() for _ in range(bars)]
        for bar in range(bars):
            for ev in player.events_for_bar(bar):
                if isinstance(ev, NoteOn):
                    per_bar[bar].add(ev.channel)
    finally:
        player.close()

    offenders: list[tuple[int, int]] = []
    for ch in sorted(_EXPECTED_NOTE_CHANNELS):
        gap = _max_gap_for_channel(per_bar, ch)
        if gap > _MAX_BAR_GAP:
            offenders.append((ch, gap))
    assert not offenders, (
        f"channels exceeding the {_MAX_BAR_GAP}-bar quiet limit: "
        + ", ".join(f"ch{c}={g}" for c, g in offenders)
    )


def test_engine_stress_song_filter_modulator_emits_cc74_every_2_bars() -> None:
    """The filter utility voice must stream CC74 within 2 bars on its channel."""
    song = load_song(SONG_PATH)
    setup = load_setup(SETUP_PATH)
    filter_slot = setup.voice("filter")
    assert filter_slot is not None

    part_name = song.arrangement[0]
    bars = song.parts[part_name].bars

    player = SongPlayer(song, setup, part_name)
    try:
        cc_bars: set[int] = set()
        for bar in range(bars):
            for ev in player.events_for_bar(bar):
                if (
                    isinstance(ev, ControlChange)
                    and ev.cc == 74
                    and ev.channel == filter_slot.midi_channel
                ):
                    cc_bars.add(bar)
    finally:
        player.close()

    seen_bars = sorted(cc_bars)
    assert seen_bars, f"no CC74 on filter ch{filter_slot.midi_channel} — modulator silent"
    gaps = [b - a for a, b in zip(seen_bars, seen_bars[1:])]
    max_gap = max(gaps) if gaps else 1
    assert max_gap <= _MAX_BAR_GAP, (
        f"filter ch{filter_slot.midi_channel} CC74 quiet for {max_gap} bars (limit {_MAX_BAR_GAP})"
    )
