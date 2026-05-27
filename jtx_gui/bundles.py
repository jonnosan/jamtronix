"""Locate bundled .jtx-setup files shipped under the repo's ``setups/``.

The wizard offers these as starting points for a new song. We resolve
the directory by walking up from this module's path so the lookup
works both in a checkout and from an installed wheel.
"""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    # jtx_gui/bundles.py → jtx_gui/ → repo root
    return Path(__file__).resolve().parent.parent


def setups_dir() -> Path:
    return _repo_root() / "setups"


def bundled_setups() -> list[Path]:
    """All ``.jtx-setup`` files shipped with the app."""
    d = setups_dir()
    if not d.is_dir():
        return []
    return sorted(d.glob("*.jtx-setup"))
