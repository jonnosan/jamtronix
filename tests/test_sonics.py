"""SONICS_REGIONS — importable from jtx.composer, four documented entries."""

from __future__ import annotations

import pytest

from jtx.composer import SONICS_REGIONS as SONICS_FROM_PACKAGE
from jtx.composer.sonics import SONICS_REGIONS


def test_sonics_regions_re_exported_from_composer_package() -> None:
    """SONICS_REGIONS is importable both directly and via jtx.composer."""
    assert SONICS_FROM_PACKAGE is SONICS_REGIONS


def test_sonics_regions_has_four_documented_entries() -> None:
    assert set(SONICS_REGIONS) == {"acid", "deep_techno", "psytrance", "dub_techno"}


@pytest.mark.parametrize(
    "name,expected",
    [
        ("acid",        (0.475, 0.725)),
        ("deep_techno", (0.775, 0.250)),
        ("psytrance",   (0.425, 0.850)),
        ("dub_techno",  (0.300, 0.800)),
    ],
)
def test_sonics_region_centres(name: str, expected: tuple[float, float]) -> None:
    assert SONICS_REGIONS[name] == expected


def test_sonics_region_values_in_unit_square() -> None:
    """Both axes are on [0, 1] — sonics has no negative-half semantics."""
    for name, (x, y) in SONICS_REGIONS.items():
        assert 0.0 <= x <= 1.0, f"{name} texture out of [0,1]: {x}"
        assert 0.0 <= y <= 1.0, f"{name} motion out of [0,1]: {y}"
