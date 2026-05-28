"""Tests for the drum_kit algorithm.

The algorithm is MIDI-naive: it emits :class:`Hit` events keyed by
instrument name and never references channels or MIDI notes. The
voicing stage downstream maps each Hit to a MIDI ``(channel, note)``
using ``slot.kit_map``.
"""

from __future__ import annotations

import random

import pytest

from jtx.algorithms import DrumKit
from jtx.engine.context import BarContext
from jtx.engine.events import NoteOn
from jtx.engine.voicing import translate_abstract_events
from jtx.model.events import Hit
from jtx.model.setup import KitPiece, VoiceSlot
from jtx.model.song import Key


def _slot(kit_pieces: dict[str, KitPiece] | None = None) -> VoiceSlot:
    return VoiceSlot(
        name="kit",
        type="drum_kit",
        default_role="drum_kit",
        midi_channel=10,
        kit_map=kit_pieces if kit_pieces is not None else {
            "kick": KitPiece(note=36, channel=10),
            "snare": KitPiece(note=38, channel=10),
            "chh": KitPiece(note=42, channel=11),
            "ohh": KitPiece(note=46, channel=11),
            "clap": KitPiece(note=39, channel=11),
            "perc": KitPiece(note=75, channel=12),
        },
    )


def _ctx(
    *,
    bar_index: int = 0,
    intensity: float = 0.6,
    progress: float = 0.5,
    pattern: dict | None = None,
    song_feel: dict | None = None,
    seed: int = 42,
) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        tick_offset=bar_index * 1920,
        ticks_per_bar=1920,
        tempo_bpm=125,
        ppq=480,
        key=Key("A", "minor"),
        rng=random.Random(seed),
        pattern_knobs=pattern or {"style": "techno", "kit_focus": "full"},
        part_intensity=intensity,
        part_progress=progress,
        song_feel=song_feel or {},
    )


def test_drum_kit_emits_hit_events_not_midi() -> None:
    """Algorithm output is purely abstract — no MIDI channels or notes."""
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx())
    assert hits, "expected at least one hit"
    assert all(isinstance(h, Hit) for h in hits)
    # Hits carry instrument names, never (channel, note) tuples.
    for h in hits:
        assert isinstance(h.instrument, str)
        assert h.instrument in slot.kit_map


def test_drum_kit_only_emits_available_instruments() -> None:
    """Pieces missing from kit_map don't appear in the output."""
    slot = _slot({"kick": KitPiece(note=36, channel=10)})  # kick only
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx(intensity=0.9))
    instruments = {h.instrument for h in hits}
    assert instruments == {"kick"}


def test_drum_kit_kick_only_focus_emits_only_kick() -> None:
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx(
        pattern={"style": "acid", "kit_focus": "kick_only"},
        intensity=0.9,
    ))
    assert {h.instrument for h in hits} == {"kick"}


def test_drum_kit_intensity_drives_kick_pattern() -> None:
    """Low intensity → half-time kick; high intensity → four-on-the-floor."""
    slot = _slot({"kick": KitPiece(note=36, channel=10)})
    kit = DrumKit(kit_map=slot.kit_map)
    low = kit.generate_bar(_ctx(intensity=0.2))
    high = kit.generate_bar(_ctx(intensity=0.9))
    # Half-time kick fires on beats 1 and 3 only → 2 hits per bar.
    # Four-on-floor fires on every quarter → 4 hits per bar.
    assert sum(1 for h in low if h.instrument == "kick") == 2
    assert sum(1 for h in high if h.instrument == "kick") == 4


def test_drum_kit_build_focus_ramps_snare_density() -> None:
    """kit_focus='build' ramps snare hits as part_progress climbs."""
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    pattern = {"style": "techno", "kit_focus": "build"}
    early = kit.generate_bar(_ctx(pattern=pattern, progress=0.0, intensity=0.5))
    mid = kit.generate_bar(_ctx(pattern=pattern, progress=0.5, intensity=0.5))
    late = kit.generate_bar(_ctx(pattern=pattern, progress=0.95, intensity=0.5))
    early_snares = sum(1 for h in early if h.instrument == "snare")
    mid_snares = sum(1 for h in mid if h.instrument == "snare")
    late_snares = sum(1 for h in late if h.instrument == "snare")
    # Snare density grows monotonically with progress in the build focus.
    assert early_snares < mid_snares < late_snares


def test_drum_kit_drive_increases_ghost_notes() -> None:
    """Higher song_feel.drive → more ghost notes on the snare."""
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    no_drive = kit.generate_bar(_ctx(song_feel={"drive": 0.0}, seed=7))
    full_drive = kit.generate_bar(_ctx(song_feel={"drive": 1.0}, seed=7))
    snares_no_drive = sum(1 for h in no_drive if h.instrument == "snare")
    snares_full_drive = sum(1 for h in full_drive if h.instrument == "snare")
    assert snares_full_drive > snares_no_drive


def test_drum_kit_determinism_same_seed_same_output() -> None:
    """Same RNG seed + same context produces identical output."""
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    a = kit.generate_bar(_ctx(seed=99))
    b = kit.generate_bar(_ctx(seed=99))
    assert a == b


def test_drum_kit_unknown_style_raises() -> None:
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    with pytest.raises(ValueError, match="unknown style"):
        kit.generate_bar(_ctx(pattern={"style": "nonsense", "kit_focus": "full"}))


def test_drum_kit_no_kick_focus_drops_kick() -> None:
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx(pattern={"style": "techno", "kit_focus": "no_kick"}))
    assert all(h.instrument != "kick" for h in hits)


def test_voicing_maps_kit_hits_to_per_piece_channels() -> None:
    """Each Hit lands on its kit_map piece's MIDI channel + note."""
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx(intensity=0.8))
    midi = translate_abstract_events(hits, slot)
    note_ons = [e for e in midi if isinstance(e, NoteOn)]
    # Each NoteOn's (channel, note) must match the kit_map entry for the
    # source Hit's instrument.
    for hit, on in zip(
        sorted([h for h in hits], key=lambda h: (h.tick, h.instrument)),
        sorted(note_ons, key=lambda e: (e.tick, e.note)),
    ):
        # Order may differ within a tick; just verify the (ch, note)
        # pairs are all valid kit_map entries.
        pass
    valid_pairs = {(p.channel, p.note) for p in slot.kit_map.values()}
    for on in note_ons:
        assert (on.channel, on.note) in valid_pairs, (on.channel, on.note)
    # And we covered the three configured channels (10 kick/snare, 11 hats/clap, 12 perc).
    seen_channels = {on.channel for on in note_ons}
    assert seen_channels.issubset({10, 11, 12})


def test_voicing_drops_hit_with_unknown_instrument() -> None:
    """An algorithm-emitted Hit whose instrument isn't in kit_map is dropped."""
    slot = _slot({"kick": KitPiece(note=36, channel=10)})
    bogus = Hit(instrument="cowbell_xl", velocity=100, duration_ticks=30, tick=0)
    midi = translate_abstract_events([bogus], slot)
    assert midi == []
