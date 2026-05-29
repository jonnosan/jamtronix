"""MoodPadWidget / Pad2DWidget — axis math, click-anywhere, signal timing."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx.composer.mood import MOOD_ANCHORS  # noqa: E402
from jtx.composer.sonics import SONICS_REGIONS  # noqa: E402
from jtx_gui.widgets.mood_pad import MoodPadWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


# ---------- set_mood + clamp -------------------------------------------


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


# ---------- click-anywhere semantics (no snap) -------------------------


def test_click_at_anchor_lands_at_exact_anchor_no_snap(qapp: QApplication) -> None:
    """Clicking at an anchor's pixel position lands at that exact value
    (which happens to be the anchor's value) — but the path is geometric,
    not snap-based. A click 5px away lands 5px away (see next test)."""
    pad = MoodPadWidget()
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    anchor = MOOD_ANCHORS["euphoric"]
    anchor_point = pad._point_for_mood(anchor.valence, anchor.energy)  # type: ignore[attr-defined]
    QTest.mouseClick(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(anchor_point.x()), int(anchor_point.y())),
    )
    v, e = pad.mood()
    assert abs(v - anchor.valence) < 0.02
    assert abs(e - anchor.energy) < 0.02
    pad.deleteLater()


def test_click_near_anchor_does_not_snap(qapp: QApplication) -> None:
    """A click well inside the legacy snap hit-rect lands at the click
    point, not the anchor's value — anchors are visual only now."""
    pad = MoodPadWidget()
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    anchor = MOOD_ANCHORS["euphoric"]
    anchor_point = pad._point_for_mood(anchor.valence, anchor.energy)  # type: ignore[attr-defined]
    # 18px south of the anchor — would have fallen inside the old
    # 25px hit-rect and snapped to the anchor.
    near_point = QPoint(int(anchor_point.x()), int(anchor_point.y()) + 18)
    QTest.mouseClick(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        near_point,
    )
    v, e = pad.mood()
    # Mood is *not* the anchor's mood — the click lands 18px south
    # which translates to a lower energy than the anchor.
    assert e < anchor.energy - 0.05
    pad.deleteLater()


def test_click_at_centre_places_at_zero(qapp: QApplication) -> None:
    """Click at the geometric centre of the default (-1, 1) range
    lands at (0, 0)."""
    pad = MoodPadWidget()
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    centre_point = pad._point_for_mood(0.0, 0.0)  # type: ignore[attr-defined]
    QTest.mouseClick(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(centre_point.x()), int(centre_point.y())),
    )
    v, e = pad.mood()
    assert abs(v) < 0.02
    assert abs(e) < 0.02
    pad.deleteLater()


# ---------- (0, 1) axis range — sonics configuration --------------------


def test_axis_range_zero_one_centre_maps_to_half(qapp: QApplication) -> None:
    """With axis_range=(0, 1), clicking the geometric centre yields (0.5, 0.5)."""
    pad = MoodPadWidget(
        anchors=SONICS_REGIONS,
        axis_range=(0.0, 1.0),
        axis_labels=("TEXTURE", "MOTION"),
    )
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    centre_point = pad._point_for_mood(0.5, 0.5)  # type: ignore[attr-defined]
    QTest.mouseClick(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(centre_point.x()), int(centre_point.y())),
    )
    v, e = pad.value()
    assert abs(v - 0.5) < 0.02
    assert abs(e - 0.5) < 0.02
    pad.deleteLater()


def test_axis_range_zero_one_clamps_below_zero(qapp: QApplication) -> None:
    """set_mood with negative input clamps to 0 on (0, 1) range."""
    pad = MoodPadWidget(
        anchors=SONICS_REGIONS,
        axis_range=(0.0, 1.0),
        axis_labels=("TEXTURE", "MOTION"),
    )
    pad.set_mood(-0.5, 1.5)
    assert pad.value() == (0.0, 1.0)


def test_axis_range_zero_one_round_trip_corners(qapp: QApplication) -> None:
    """_point_for_mood / _mood_for_point are inverses at the corners."""
    pad = MoodPadWidget(
        anchors=SONICS_REGIONS,
        axis_range=(0.0, 1.0),
        axis_labels=("TEXTURE", "MOTION"),
    )
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    for x_target, y_target in [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5), (0.25, 0.75)]:
        p = pad._point_for_mood(x_target, y_target)  # type: ignore[attr-defined]
        x_back, y_back = pad._mood_for_point(p)  # type: ignore[attr-defined]
        assert abs(x_back - x_target) < 1e-6
        assert abs(y_back - y_target) < 1e-6
    pad.deleteLater()


# ---------- value_committed timing -------------------------------------


def test_value_committed_fires_on_mouse_release(qapp: QApplication) -> None:
    """value_committed fires once when the mouse is released after a drag."""
    pad = MoodPadWidget()
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    commits: list[tuple[float, float]] = []
    pad.value_committed.connect(lambda v, e: commits.append((v, e)))

    centre_point = pad._point_for_mood(0.0, 0.0)  # type: ignore[attr-defined]
    pt = QPoint(int(centre_point.x()), int(centre_point.y()))
    QTest.mousePress(pad, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    # Nothing committed yet — drag still in progress.
    assert commits == []
    QTest.mouseRelease(
        pad, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt
    )
    assert len(commits) == 1
    v, e = commits[0]
    assert abs(v) < 0.02
    assert abs(e) < 0.02
    pad.deleteLater()


def test_value_committed_not_fired_by_set_mood_default(qapp: QApplication) -> None:
    """Programmatic set_mood does not fire value_committed by default."""
    pad = MoodPadWidget()
    commits: list[tuple[float, float]] = []
    pad.value_committed.connect(lambda v, e: commits.append((v, e)))
    pad.set_mood(0.3, 0.4)
    assert commits == []


def test_value_committed_fired_by_set_mood_with_emit_commit(qapp: QApplication) -> None:
    """set_mood(emit_commit=True) fires value_committed even on programmatic set."""
    pad = MoodPadWidget()
    commits: list[tuple[float, float]] = []
    pad.value_committed.connect(lambda v, e: commits.append((v, e)))
    pad.set_mood(0.3, 0.4, emit_commit=True)
    assert commits == [(0.3, 0.4)]


def test_mood_changed_still_fires_on_drag(qapp: QApplication) -> None:
    """mood_changed keeps firing on every drag move (high-frequency)."""
    pad = MoodPadWidget()
    pad.resize(400, 400)
    pad.show()
    QApplication.processEvents()

    changes: list[tuple[float, float]] = []
    pad.mood_changed.connect(lambda v, e: changes.append((v, e)))

    start_point = pad._point_for_mood(0.0, 0.0)  # type: ignore[attr-defined]
    QTest.mousePress(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(start_point.x()), int(start_point.y())),
    )
    # Press at centre logged one change.
    initial = len(changes)
    # Drag a bit — at least one more change should fire on move.
    end_point = pad._point_for_mood(0.3, 0.3)  # type: ignore[attr-defined]
    QTest.mouseMove(
        pad, QPoint(int(end_point.x()), int(end_point.y()))
    )
    QApplication.processEvents()
    assert len(changes) > initial
    QTest.mouseRelease(
        pad,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(end_point.x()), int(end_point.y())),
    )
    pad.deleteLater()
