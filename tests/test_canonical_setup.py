"""Each bundled setup exposes the composer's FIXED_PALETTE + utility cluster.

The composer always emits the same 9 musical voice names plus the three
utility voices (``filter``, ``root_ref``, ``chord_ref``). For a bundled
setup to be usable by a composer-generated song, it must expose every
one of those names. This test catches the regression class where a
setup drifts out of palette (missing voice, stale legacy name).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jtx.model.composer_types import FIXED_PALETTE, UTILITY_VOICES
from jtx.persist import load_setup

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUPS = ("jamtronix", "iac", "ableton", "ableton-mpe")

_REQUIRED_KIT_PIECES = ("kick", "snare", "chh", "ohh", "clap", "perc")


@pytest.mark.parametrize("setup_name", SETUPS)
def test_bundled_setup_has_fixed_palette(setup_name: str) -> None:
    """Every palette voice name resolves to a slot in the setup."""
    setup = load_setup(REPO_ROOT / "setups" / f"{setup_name}.jtx-setup")
    voice_names = {slot.name for slot in setup.voices}
    missing = set(FIXED_PALETTE) - voice_names
    assert not missing, f"{setup_name}: missing palette voices: {sorted(missing)}"


@pytest.mark.parametrize("setup_name", SETUPS)
def test_bundled_setup_has_utility_cluster(setup_name: str) -> None:
    """``filter`` + ``root_ref`` + ``chord_ref`` all exist."""
    setup = load_setup(REPO_ROOT / "setups" / f"{setup_name}.jtx-setup")
    for util in UTILITY_VOICES:
        assert setup.voice(util) is not None, f"{setup_name}: missing utility voice {util!r}"


@pytest.mark.parametrize("setup_name", SETUPS)
def test_bundled_setup_drumkit_has_required_pieces(setup_name: str) -> None:
    """The drumkit voice's kit_map has at least the core 6 GM pieces."""
    setup = load_setup(REPO_ROOT / "setups" / f"{setup_name}.jtx-setup")
    drumkit = setup.voice("drumkit")
    assert drumkit is not None, f"{setup_name}: no drumkit voice"
    assert drumkit.type == "drum_kit"
    pieces = set(drumkit.kit_map.keys())
    missing = set(_REQUIRED_KIT_PIECES) - pieces
    assert not missing, f"{setup_name}: drumkit missing kit_map pieces: {sorted(missing)}"


@pytest.mark.parametrize("setup_name", SETUPS)
def test_bundled_setup_filter_routes_cc74(setup_name: str) -> None:
    """The ``filter`` modulator slot maps ``cutoff`` → CC74."""
    from jtx.model.parameter_target import CCTarget

    setup = load_setup(REPO_ROOT / "setups" / f"{setup_name}.jtx-setup")
    filter_slot = setup.voice("filter")
    assert filter_slot is not None
    cutoff = filter_slot.parameter_map.get("cutoff")
    assert isinstance(cutoff, CCTarget), f"{setup_name}: filter cutoff not wired to a CC target"
    assert cutoff.cc == 74
