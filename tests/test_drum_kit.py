"""Tests for the drum_kit algorithm.

The algorithm is MIDI-naive: it emits :class:`Hit` events keyed by
instrument name and never references channels or MIDI notes. The
voicing stage downstream maps each Hit to a MIDI ``(channel, note)``
using ``slot.kit_map``.
"""

from __future__ import annotations

import random

from jtx.algorithms import DrumKit
from jtx.algorithms.drum_kit import _derive_profile
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
        kit_map=kit_pieces
        if kit_pieces is not None
        else {
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
        pattern_knobs=pattern or {"kit_focus": "full"},
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
    hits = kit.generate_bar(
        _ctx(
            pattern={"kit_focus": "kick_only"},
            intensity=0.9,
        )
    )
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
    pattern = {"kit_focus": "build"}
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


def test_drum_kit_ignores_legacy_style_knob() -> None:
    """Stray ``style`` key from old saved songs/tests is silently ignored.

    Pre-refactor songs carried ``pattern.style = "acid"`` / ``"techno"`` /
    ``"psy"``. After the punch/mech refactor those values aren't read by
    the algorithm, but the dict still contains them. Verify they don't
    crash the generator.
    """
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx(pattern={"style": "nonsense", "kit_focus": "full"}, intensity=0.7))
    assert hits  # generator still runs


def test_drum_kit_no_kick_focus_drops_kick() -> None:
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx(pattern={"kit_focus": "no_kick"}))
    assert all(h.instrument != "kick" for h in hits)


def test_voicing_maps_kit_hits_to_per_piece_channels() -> None:
    """Each Hit lands on its kit_map piece's MIDI channel + note."""
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)
    hits = kit.generate_bar(_ctx(intensity=0.8))
    midi = translate_abstract_events(hits, slot)
    note_ons = [e for e in midi if isinstance(e, NoteOn)]
    valid_pairs = {(p.channel, p.note) for p in slot.kit_map.values()}
    for on in note_ons:
        assert (on.channel, on.note) in valid_pairs, (on.channel, on.note)
    # And we covered the three configured channels.
    seen_channels = {on.channel for on in note_ons}
    assert seen_channels.issubset({10, 11, 12})


def test_voicing_drops_hit_with_unknown_instrument() -> None:
    """An algorithm-emitted Hit whose instrument isn't in kit_map is dropped."""
    slot = _slot({"kick": KitPiece(note=36, channel=10)})
    bogus = Hit(instrument="cowbell_xl", velocity=100, duration_ticks=30, tick=0)
    midi = translate_abstract_events([bogus], slot)
    assert midi == []


# ---------------------------------------------------------------- _derive_profile


def test_derive_profile_clamps_inputs() -> None:
    """Inputs outside [0, 1] are clamped before derivation."""
    p_low = _derive_profile(punch=-1.0, mech=-1.0)
    p_high = _derive_profile(punch=5.0, mech=5.0)
    p_zero = _derive_profile(punch=0.0, mech=0.0)
    p_one = _derive_profile(punch=1.0, mech=1.0)
    assert p_low == p_zero
    assert p_high == p_one


def test_derive_profile_punch_raises_kick_and_snare_velocity() -> None:
    """Higher punch → harder kick and snare velocities."""
    low = _derive_profile(punch=0.0, mech=0.5)
    high = _derive_profile(punch=1.0, mech=0.5)
    assert high.kick_vel > low.kick_vel
    assert high.snare_vel > low.snare_vel


def test_derive_profile_mech_raises_snare_ceilings() -> None:
    """Higher mech → larger build- and default-mode snare ceilings."""
    low = _derive_profile(punch=0.5, mech=0.0)
    high = _derive_profile(punch=0.5, mech=1.0)
    assert high.build_snare_max > low.build_snare_max
    assert high.default_snare_max > low.default_snare_max


def test_derive_profile_mech_lowers_triplet_hat_threshold() -> None:
    """Higher mech → triplet hat polyrhythm fires at lower intensity."""
    low = _derive_profile(punch=0.5, mech=0.0)
    high = _derive_profile(punch=0.5, mech=1.0)
    assert high.triplet_hat_above < low.triplet_hat_above


def test_derive_profile_legacy_style_corners_are_distinct() -> None:
    """The 3 legacy style corners produce distinguishable profiles.

    Corner placements (informational, not exact reproduction of the
    legacy ``_STYLE_PROFILES`` values):
    * acid  ≈ (punch 0.55, mech 0.4) — restrained build, lower default snare
    * techno≈ (punch 0.4, mech 0.7) — driving snare, machine-gun build
    * psy   ≈ (punch 0.85, mech 0.85) — full ceilings, hard kick
    """
    acid = _derive_profile(punch=0.55, mech=0.4)
    techno = _derive_profile(punch=0.4, mech=0.7)
    psy = _derive_profile(punch=0.85, mech=0.85)
    # Default snare ceiling ordering (acid restrained; psy driving).
    assert acid.default_snare_max < techno.default_snare_max < psy.default_snare_max
    # Build snare ceiling ordering.
    assert acid.build_snare_max < techno.build_snare_max <= psy.build_snare_max
    # Psy hits hardest.
    assert psy.kick_vel > acid.kick_vel
    assert psy.kick_vel > techno.kick_vel


# ---------------------------------------------------------------- knob-driven behaviour


def test_drum_kit_build_snare_ceiling_depends_on_mech() -> None:
    """Build-mode snare ramp ceiling rises with mech.

    Low-mech (acid-ish) settings keep the build tense without going
    full machine-gun; high-mech (techno/psy-ish) settings hit the 32nd
    grid at the drop.
    """
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)

    def snares_at_progress_one(punch: float, mech: float) -> int:
        hits = kit.generate_bar(
            _ctx(
                bar_index=7,
                pattern={"punch": punch, "mech": mech, "kit_focus": "build"},
                progress=1.0,
                intensity=0.5,
            )
        )
        return sum(1 for h in hits if h.instrument == "snare")

    acid_like = snares_at_progress_one(punch=0.55, mech=0.4)
    psy_like = snares_at_progress_one(punch=0.85, mech=0.85)
    # The high-mech corner pushes a larger ceiling than the low-mech corner.
    assert acid_like < psy_like
    # Sanity bound: at progress=1 + low mech, snares stay well under the
    # full machine-gun count.
    assert acid_like <= 28


def test_drum_kit_default_snare_ceiling_depends_on_mech() -> None:
    """Default (kit_focus='full') snare auto-ramp ceiling rises with mech."""
    slot = _slot()
    kit = DrumKit(kit_map=slot.kit_map)

    def drop_snares(punch: float, mech: float) -> int:
        hits = kit.generate_bar(
            _ctx(
                pattern={"punch": punch, "mech": mech, "kit_focus": "full"},
                intensity=0.9,
                progress=0.5,
            )
        )
        return sum(1 for h in hits if h.instrument == "snare")

    acid_like = drop_snares(punch=0.55, mech=0.4)
    techno_like = drop_snares(punch=0.4, mech=0.7)
    psy_like = drop_snares(punch=0.85, mech=0.85)
    # The low-mech corner stays restrained; high-mech drives harder.
    assert acid_like < techno_like
    assert acid_like < psy_like
    # And the acid corner is genuinely restrained, not just "1 less".
    assert acid_like <= 14, f"low-mech corner snare too dense: {acid_like}"
    assert techno_like >= 14, f"mid-mech corner snare too sparse: {techno_like}"
