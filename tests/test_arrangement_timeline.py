"""ArrangementTimeline — set_song, click selects part, signal emission."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx.model import Key, Part, Song  # noqa: E402
from jtx_gui.widgets.arrangement_timeline import ArrangementTimeline  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _four_part_song() -> Song:
    song = Song(title="t", setup_ref="x", key=Key(tonic="C"))
    song.parts = {
        "intro": Part(bars=8, intensity_start=0.2, intensity_end=0.5),
        "verse": Part(bars=16, intensity_start=0.5, intensity_end=0.7),
        "chorus": Part(bars=16, intensity_start=0.7, intensity_end=0.9),
        "outro": Part(bars=8, intensity_start=0.9, intensity_end=0.3),
    }
    return song


def test_paint_event_fires_for_four_part_song(qapp: QApplication) -> None:
    """Showing a populated timeline fills the cached block hit-rects."""
    timeline = ArrangementTimeline()
    timeline.resize(800, 96)
    timeline.set_song(_four_part_song())
    timeline.show()
    QApplication.processEvents()
    timeline.repaint()
    assert len(timeline._block_rects) == 4
    names = [n for n, _r in timeline._block_rects]
    assert names == ["intro", "verse", "chorus", "outro"]
    timeline.deleteLater()


def test_click_emits_part_selected_with_correct_name(qapp: QApplication) -> None:
    """Clicking inside the third block emits the third part's name."""
    timeline = ArrangementTimeline()
    timeline.resize(800, 96)
    timeline.set_song(_four_part_song())
    timeline.show()
    QApplication.processEvents()
    timeline.repaint()

    received: list[str] = []
    timeline.part_selected.connect(received.append)

    _name, rect = timeline._block_rects[2]
    QTest.mouseClick(
        timeline,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(rect.center().x()), int(rect.center().y())),
    )
    assert received == ["chorus"]
    assert timeline.selected_part() == "chorus"
    timeline.deleteLater()


def test_empty_song_renders_placeholder_and_no_blocks(qapp: QApplication) -> None:
    """A timeline without a song shows a placeholder and has no hit-rects."""
    timeline = ArrangementTimeline()
    timeline.resize(800, 96)
    timeline.show()
    QApplication.processEvents()
    timeline.repaint()
    assert timeline._block_rects == []
    assert timeline.selected_part() is None
    timeline.deleteLater()


def test_set_song_clears_stale_selection(qapp: QApplication) -> None:
    """Switching to a new song drops a selection that isn't present in it."""
    timeline = ArrangementTimeline()
    timeline.resize(800, 96)
    timeline.set_song(_four_part_song())
    timeline.set_selected_part("chorus")
    other = Song(title="o", setup_ref="x", key=Key(tonic="C"))
    other.parts = {"only": Part(bars=4)}
    timeline.set_song(other)
    assert timeline.selected_part() == "only"
    timeline.deleteLater()
