"""Tests for deterministic seed derivation.

These tests pin the SHA-256 derivation to known vectors so an accidental
change to the hashing scheme (which would break reproducibility for every
saved song) fails loudly.
"""

from __future__ import annotations

from jtx.seed import (
    derive_bar_seed,
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
