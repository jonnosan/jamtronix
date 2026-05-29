"""AppState.replace_song_in_place — settings-driven swap semantics."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx.model import Song  # noqa: E402
from jtx_gui.state import AppState  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_FIXTURE = REPO_ROOT / "examples" / "test-fixture.jtx"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_replace_song_in_place_swaps_song_and_fires_song_changed(
    qapp: QApplication,
) -> None:
    state = AppState()
    state.open(TEST_FIXTURE)
    original = state.song
    assert original is not None

    song_changed_count = 0

    def _bump() -> None:
        nonlocal song_changed_count
        song_changed_count += 1

    state.song_changed.connect(_bump)

    fields = {f.name: getattr(original, f.name) for f in dataclasses.fields(Song)}
    fields["title"] = "Replacement"
    replacement = Song(**fields)

    state.replace_song_in_place(replacement)
    assert state.song is replacement
    assert state.song.title == "Replacement"
    assert song_changed_count == 1


def test_replace_song_in_place_does_not_mark_dirty(qapp: QApplication) -> None:
    state = AppState()
    state.open(TEST_FIXTURE)
    assert not state.dirty

    fields = {f.name: getattr(state.song, f.name) for f in dataclasses.fields(Song)}
    fields["title"] = "Replacement"
    replacement = Song(**fields)

    dirty_signals: list[bool] = []
    state.dirty_changed.connect(lambda v: dirty_signals.append(v))

    state.replace_song_in_place(replacement)
    assert not state.dirty
    assert dirty_signals == []


def test_replace_song_in_place_does_not_change_path(qapp: QApplication) -> None:
    state = AppState()
    state.open(TEST_FIXTURE)
    original_path = state.path
    assert original_path is not None

    fields = {f.name: getattr(state.song, f.name) for f in dataclasses.fields(Song)}
    fields["title"] = "Replacement"
    replacement = Song(**fields)

    path_signals: list[object] = []
    state.path_changed.connect(lambda p: path_signals.append(p))

    state.replace_song_in_place(replacement)
    assert state.path == original_path
    assert path_signals == []
