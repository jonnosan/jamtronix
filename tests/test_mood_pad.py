"""MoodPadWidget — set_mood, anchor snap-on-click, mood_changed signal."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx.composer.mood import MOOD_ANCHORS  # noqa: E402
from jtx_gui.widgets.mood_pad import MoodPadWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_set_mood_updates_state_and_emits(qapp: QApplication) -> None:
    pad = MoodPadWidget()
    received: list[tuple[float, float]] = []
    pad.mood_changed.connect(lambda v, e: received.append((v, e)))

    pad.set_mood(0.5, -0.25)
    assert pad.mood() == (0.5, -0.25)
    assert received == [(0.5, -0.25)]


def test_set_mood_clamps_out_of_range(qapp: QApplication) -> None:
    pad = MoodPadWidget()
    pad.set_mood(2.5, -3.0)
    assert pad.mood() == (1.0, -1.0)


def test_set_mood_no_emit_when_unchanged(qapp: QApplication) -> None:
    pad = MoodPadWidget()
    pad.set_mood(0.3, 0.4)
    received: list[tuple[float, float]] = []
    pad.mood_changed.connect(lambda v, e: received.append((v, e)))
    pad.set_mood(0.3, 0.4)  # same values — no emit
    assert received == []


def test_set_mood_emit_false_suppresses_signal(qapp: QApplication) -> None:
    pad = MoodPadWidget()
    received: list[tuple[float, float]] = []
    pad.mood_changed.connect(lambda v, e: received.append((v, e)))
    pad.set_mood(0.2, 0.2, emit=False)
    assert pad.mood() == (0.2, 0.2)
    assert received == []


def test_click_on_anchor_snaps_thumb(qapp: QApplication) -> None:
    """Clicking inside an anchor's hit-rect snaps to its canonical mood."""
    pad = MoodPadWidget()
    pad.resize(400, 400)
    pad.show()  # paint at least once to populate geometry
    QApplication.processEvents()

    received: list[tuple[float, float]] = []
    pad.mood_changed.connect(lambda v, e: received.append((v, e)))

    anchor = MOOD_ANCHORS["euphoric"]
    anchor_point = pad._point_for_mood(anchor.valence, anchor.energy)  # type: ignore[attr-defined]
    QTest.mouseClick(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(anchor_point.x()), int(anchor_point.y())),
    )

    assert pad.mood() == (anchor.valence, anchor.energy)
    assert received and received[-1] == (anchor.valence, anchor.energy)
    pad.deleteLater()


def test_click_off_anchor_places_freely(qapp: QApplication) -> None:
    """A click outside every anchor's hit-rect lands the thumb at the click."""
    pad = MoodPadWidget()
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    # The pad centre maps to (valence=0, energy=0) — guaranteed off-anchor
    # since no MOOD_ANCHOR sits at the origin.
    centre_point = pad._point_for_mood(0.0, 0.0)  # type: ignore[attr-defined]
    QTest.mouseClick(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(centre_point.x()), int(centre_point.y())),
    )
    v, e = pad.mood()
    assert abs(v) < 0.05
    assert abs(e) < 0.05
    pad.deleteLater()
