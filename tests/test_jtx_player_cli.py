"""Lightweight tests for the ``tools/jtx_player.py`` CLI helpers.

The CLI itself drives MIDI playback so end-to-end testing is out of
scope here — these tests just pin the setup-resolution policy that
recently grew a ``./setups/<setup_ref>.jtx-setup`` fallback so songs
in ``examples/`` work without ``--setup`` when run from the repo
root.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_PLAYER_PATH = REPO_ROOT / "tools" / "jtx_player.py"


def _load_player_module():
    spec = importlib.util.spec_from_file_location("jtx_player_cli", _PLAYER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("jtx_player_cli", module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def player_mod():
    return _load_player_module()


def test_resolve_setup_path_uses_explicit_when_given(player_mod, tmp_path: Path) -> None:
    """--setup wins even if a co-located file exists."""
    song = tmp_path / "song.jtx"
    song.write_text("{}")
    co_located = tmp_path / "ableton.jtx-setup"
    co_located.write_text("{}")
    explicit = tmp_path / "other.jtx-setup"
    explicit.write_text("{}")

    parser = argparse.ArgumentParser()
    resolved = player_mod._resolve_setup_path(explicit, song, "ableton", parser)
    assert resolved == explicit


def test_resolve_setup_path_falls_back_to_co_located(player_mod, tmp_path: Path) -> None:
    """When --setup isn't given, prefer the file next to the song."""
    song = tmp_path / "song.jtx"
    song.write_text("{}")
    co_located = tmp_path / "ableton.jtx-setup"
    co_located.write_text("{}")

    parser = argparse.ArgumentParser()
    resolved = player_mod._resolve_setup_path(None, song, "ableton", parser)
    assert resolved == co_located


def test_resolve_setup_path_falls_back_to_cwd_setups_dir(
    player_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When neither --setup nor a co-located file exists, fall back to ./setups/."""
    song_dir = tmp_path / "examples"
    song_dir.mkdir()
    song = song_dir / "song.jtx"
    song.write_text("{}")

    setups_dir = tmp_path / "setups"
    setups_dir.mkdir()
    bundled = setups_dir / "ableton.jtx-setup"
    bundled.write_text("{}")

    monkeypatch.chdir(tmp_path)
    parser = argparse.ArgumentParser()
    resolved = player_mod._resolve_setup_path(None, song, "ableton", parser)
    assert resolved == bundled


def test_resolve_setup_path_errors_when_no_candidate_found(
    player_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both fallbacks miss → argparse error mentions both candidates tried."""
    song = tmp_path / "song.jtx"
    song.write_text("{}")
    monkeypatch.chdir(tmp_path)
    parser = argparse.ArgumentParser()
    with pytest.raises(SystemExit):
        player_mod._resolve_setup_path(None, song, "nonexistent", parser)
