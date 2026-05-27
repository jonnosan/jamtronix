"""Smoke tests for the PySide6 GUI.

Constructing the main window against the bundled acid-demo song
exercises the song-view, voice panels, knob factory, and File menu
wiring. We use Qt's offscreen platform so the tests work headless on
CI runners with no display.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx_gui.algorithm_meta import ALGORITHMS, SCHEMAS, algorithms_for  # noqa: E402
from jtx_gui.main_window import MainWindow  # noqa: E402
from jtx_gui.state import AppState  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
ACID_DEMO = REPO_ROOT / "examples" / "acid-demo.jtx"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_algorithms_for_each_voice_type_is_nonempty() -> None:
    """Every voice type must have at least one valid algorithm."""
    for voice_type in ("drum", "mono", "poly", "modulator", "follower"):
        assert algorithms_for(voice_type), f"no algorithms for {voice_type}"


def test_schemas_cover_every_algorithm() -> None:
    assert set(SCHEMAS.pattern_by_algo) == set(ALGORITHMS)


def test_main_window_constructs_empty(qapp: QApplication) -> None:
    """Window with no song loaded should still build cleanly."""
    state = AppState()
    window = MainWindow(state)
    assert window.windowTitle() == "Jamtronix"
    window.deleteLater()


def test_main_window_loads_acid_demo(qapp: QApplication) -> None:
    """Opening the bundled acid demo should populate the Song view."""
    state = AppState()
    window = MainWindow(state)
    assert window.open_song(ACID_DEMO)
    assert state.song is not None
    assert state.song.title == "Phuture Lines"
    assert not state.dirty
    assert "Phuture Lines" in window.windowTitle() or "acid-demo" in window.windowTitle()
    window.deleteLater()


def test_song_dirty_round_trip(tmp_path: Path, qapp: QApplication) -> None:
    """Editing then saving should clear dirty state."""
    state = AppState()
    state.open(ACID_DEMO)
    state.song.tempo = 130  # type: ignore[union-attr]
    state.mark_dirty()
    assert state.dirty
    save_path = tmp_path / "edited.jtx"
    state.save_as(save_path)
    assert not state.dirty
    assert save_path.exists()
    state2 = AppState()
    state2.open(save_path)
    assert state2.song.tempo == 130  # type: ignore[union-attr]
