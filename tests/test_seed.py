"""Tests for deterministic seed derivation.

These tests pin the SHA-256 derivation to known vectors so an accidental
change to the hashing scheme (which would break reproducibility for every
saved song) fails loudly.
"""

from __future__ import annotations

from jtx.seed import (
    derive_bar_seed,
    derive_hold_seed,
    derive_loop_seed,
    derive_part_voice_seed,
    seed_from_title,
)


def test_seed_from_title_known_vector() -> None:
    # Pin the actual digest so any future change to the hash scheme is
    # caught — this is what reproducibility on disk hinges on.
    assert seed_from_title("Phuture") == 873133126309787064


def test_seed_from_title_is_deterministic() -> None:
    assert seed_from_title("Phuture") == seed_from_title("Phuture")


def test_seed_from_title_distinguishes_titles() -> None:
    assert seed_from_title("Phuture") != seed_from_title("phuture")
    assert seed_from_title("Phuture") != seed_from_title("Phuture ")


def test_seed_from_title_is_63_bit_positive() -> None:
    for title in ["", "x", "Phuture", "🥁 a long unicode title ✨"]:
        s = seed_from_title(title)
        assert 0 <= s < (1 << 63)


def test_derive_part_voice_seed_deterministic() -> None:
    song = seed_from_title("Phuture")
    assert derive_part_voice_seed(song, "drop", "acid") == derive_part_voice_seed(
        song, "drop", "acid"
    )


def test_derive_part_voice_seed_distinguishes_inputs() -> None:
    song = seed_from_title("Phuture")
    by_part = derive_part_voice_seed(song, "drop", "acid")
    by_voice = derive_part_voice_seed(song, "drop", "kick")
    by_other_part = derive_part_voice_seed(song, "intro", "acid")
    other_song = derive_part_voice_seed(seed_from_title("Other"), "drop", "acid")
    assert len({by_part, by_voice, by_other_part, other_song}) == 4


def test_derive_part_voice_seed_avoids_concat_collision() -> None:
    # NUL separator ensures ('foo','bar') and ('foob','ar') don't collide.
    song = 12345
    a = derive_part_voice_seed(song, "foo", "bar")
    b = derive_part_voice_seed(song, "foob", "ar")
    assert a != b


def test_derive_bar_seed_deterministic_and_varies_by_bar() -> None:
    song = seed_from_title("Phuture")
    pv = derive_part_voice_seed(song, "drop", "acid")
    seeds = [derive_bar_seed(pv, b) for b in range(32)]
    assert len(set(seeds)) == 32
    assert derive_bar_seed(pv, 0) == derive_bar_seed(pv, 0)


def test_derive_bar_seed_is_63_bit_positive() -> None:
    pv = derive_part_voice_seed(seed_from_title("x"), "p", "v")
    for bar in [0, 1, 100, 9999]:
        s = derive_bar_seed(pv, bar)
        assert 0 <= s < (1 << 63)


def test_full_chain_known_vector() -> None:
    # End-to-end pin: title → song → (part, voice) → bar. Locks the wire
    # format every saved song depends on.
    song = seed_from_title("Phuture")
    pv = derive_part_voice_seed(song, "drop", "acid")
    bar = derive_bar_seed(pv, 0)
    assert pv == 3823166437560449937
    assert bar == 852521614396855364


def test_derive_loop_seed_off_falls_back_to_bar_seed() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    for bar in [0, 3, 7, 16]:
        assert derive_loop_seed(pv, 0, bar) == derive_bar_seed(pv, bar)


def test_derive_loop_seed_period_groups_by_slot() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    # period=4: bars 0/4/8 share a slot, bars 1/5 share a different slot.
    assert derive_loop_seed(pv, 4, 0) == derive_loop_seed(pv, 4, 4)
    assert derive_loop_seed(pv, 4, 0) == derive_loop_seed(pv, 4, 8)
    assert derive_loop_seed(pv, 4, 1) == derive_loop_seed(pv, 4, 5)
    assert derive_loop_seed(pv, 4, 0) != derive_loop_seed(pv, 4, 1)
    assert derive_loop_seed(pv, 4, 0) != derive_loop_seed(pv, 4, 2)


def test_derive_loop_seed_period_1_means_every_bar_identical() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    seeds = {derive_loop_seed(pv, 1, b) for b in range(16)}
    assert len(seeds) == 1


def test_derive_loop_seed_part_constant_across_bars() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    seeds = {derive_loop_seed(pv, "part", b) for b in range(32)}
    assert len(seeds) == 1


def test_derive_hold_seed_groups_by_epoch() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    # period=4: bars 0..3 share an epoch, bars 4..7 share a different epoch.
    s_epoch0 = derive_hold_seed(pv, 4, 0)
    assert derive_hold_seed(pv, 4, 1) == s_epoch0
    assert derive_hold_seed(pv, 4, 2) == s_epoch0
    assert derive_hold_seed(pv, 4, 3) == s_epoch0
    s_epoch1 = derive_hold_seed(pv, 4, 4)
    assert s_epoch1 != s_epoch0
    assert derive_hold_seed(pv, 4, 5) == s_epoch1


def test_derive_hold_seed_off_falls_back_to_bar_seed() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    for bar in [0, 3, 7, 16]:
        assert derive_hold_seed(pv, 0, bar) == derive_bar_seed(pv, bar)


def test_derive_hold_seed_part_constant_across_bars() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    seeds = {derive_hold_seed(pv, "part", b) for b in range(32)}
    assert len(seeds) == 1


def test_loop_and_hold_are_distinct_streams() -> None:
    # Same period, same bar → different seeds because of the loop/hold tag.
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    for bar in range(8):
        assert derive_loop_seed(pv, 4, bar) != derive_hold_seed(pv, 4, bar)
    assert derive_loop_seed(pv, "part", 0) != derive_hold_seed(pv, "part", 0)


def test_loop_and_hold_salt_separates_streams() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    assert derive_loop_seed(pv, 4, 0, salt="a") != derive_loop_seed(pv, 4, 0, salt="b")
    assert derive_hold_seed(pv, 4, 0, salt="a") != derive_hold_seed(pv, 4, 0, salt="b")


def test_loop_hold_seeds_are_63_bit_positive() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    for period in [1, 2, 4, 8, 16, "part"]:
        for bar in [0, 1, 100, 9999]:
            assert 0 <= derive_loop_seed(pv, period, bar) < (1 << 63)
            assert 0 <= derive_hold_seed(pv, period, bar) < (1 << 63)


def test_loop_seed_period_2_alternates() -> None:
    pv = derive_part_voice_seed(seed_from_title("Phuture"), "drop", "acid")
    even = {derive_loop_seed(pv, 2, b) for b in [0, 2, 4, 6, 8]}
    odd = {derive_loop_seed(pv, 2, b) for b in [1, 3, 5, 7, 9]}
    assert len(even) == 1
    assert len(odd) == 1
    assert even != odd
