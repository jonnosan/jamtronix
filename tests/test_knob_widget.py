"""KnobWidget — value_committed signal timing + set_value commit semantics."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jtx_gui.widgets.knob import KnobWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_knob() -> KnobWidget:
    return KnobWidget(label="chaos", minimum=0.0, maximum=1.0, value=0.5)


def test_value_committed_not_fired_by_default_set_value(qapp: QApplication) -> None:
    """Programmatic set_value(...) does not fire value_committed."""
    knob = _make_knob()
    commits: list[float] = []
    knob.value_committed.connect(lambda v: commits.append(v))
    knob.set_value(0.7)
    assert commits == []


def test_value_committed_fired_by_set_value_with_emit_commit(qapp: QApplication) -> None:
    """set_value(..., emit_commit=True) fires value_committed."""
    knob = _make_knob()
    commits: list[float] = []
    knob.value_committed.connect(lambda v: commits.append(v))
    knob.set_value(0.7, emit_commit=True)
    assert commits == [0.7]


def test_value_committed_fires_on_mouse_release_after_drag(qapp: QApplication) -> None:
    """value_committed fires once on mouseRelease, not on each drag move."""
    knob = _make_knob()
    knob.resize(120, 140)
    knob.show()
    QApplication.processEvents()

    commits: list[float] = []
    knob.value_committed.connect(lambda v: commits.append(v))
    changes: list[float] = []
    knob.value_changed.connect(lambda v: changes.append(v))

    # Press near the centre cap so the click-to-set jump is suppressed —
    # then drag upward so the value increases. Knob centre cache is
    # populated after the first paint, so we approximate with widget centre.
    centre = QPoint(knob.width() // 2, knob.height() // 2)
    QTest.mousePress(
        knob, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre
    )
    # No commit yet — still dragging.
    assert commits == []
    # Drag up by 30px to push the value higher.
    QTest.mouseMove(knob, QPoint(centre.x(), centre.y() - 30))
    QApplication.processEvents()
    # value_changed should have fired at least once during the drag.
    assert len(changes) >= 1
    # ... but value_committed has not yet.
    assert commits == []

    QTest.mouseRelease(
        knob,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(centre.x(), centre.y() - 30),
    )
    assert len(commits) == 1
    assert commits[0] == knob.value()
    knob.deleteLater()


def test_set_value_emit_false_with_emit_commit(qapp: QApplication) -> None:
    """emit=False suppresses value_changed but emit_commit still fires."""
    knob = _make_knob()
    changes: list[float] = []
    commits: list[float] = []
    knob.value_changed.connect(lambda v: changes.append(v))
    knob.value_committed.connect(lambda v: commits.append(v))
    knob.set_value(0.8, emit=False, emit_commit=True)
    assert changes == []
    assert commits == [0.8]
