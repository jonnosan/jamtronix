"""MoodPadWidget — generalized 2D pad with reference anchors + draggable thumb.

Custom-painted square pad with two axes parameterised by ``axis_range``
and ``axis_labels``. Named ``anchors`` are rendered as small dim-brass
dots with adjacent text labels — they're visual reference markers
only; clicks land wherever the cursor is (click-anywhere semantics).

Defaults are set up for the mood pad: ``axis_range=(-1.0, 1.0)`` with
``MOOD_ANCHORS`` and valence/energy labels. Pass different params to
reuse the same widget for sonics (texture × motion on ``[0, 1]²``).

Two signals:

* :attr:`mood_changed` — fired on every value change (drag, click,
  programmatic ``set_mood``). Suitable for high-frequency visual
  feedback (e.g. a readout label).
* :attr:`value_committed` — fired only on mouse release after a drag
  or on ``set_mood(..., emit_commit=True)``. Suitable for downstream
  consumers that need debounced commits (live re-roll).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from jtx.composer.mood import MOOD_ANCHORS
from jtx_gui import theme

_THUMB_RADIUS = 10
"""Radius (px) of the draggable thumb circle."""

_PAD_MARGIN = 28
"""Padding (px) around the pad square, leaving room for axis labels."""

_ANCHOR_DOT_RADIUS = 4
"""Radius (px) of each anchor's visual reference dot."""

_ANCHOR_LABEL_GAP = 6
"""Pixel gap between an anchor dot and its adjacent text label."""

_DEFAULT_MOOD_AXIS_LABELS = (
    "VALENCE  SAD ←→ HAPPY",
    "ENERGY  CALM ←→ INTENSE",
)


def _mood_anchors_as_tuples() -> dict[str, tuple[float, float]]:
    return {name: (spec.valence, spec.energy) for name, spec in MOOD_ANCHORS.items()}


class MoodPadWidget(QWidget):
    """Square 2D pad with named visual anchors + a draggable thumb."""

    mood_changed = Signal(float, float)
    """Emitted with ``(x, y)`` on every value change (drag, click, set_mood)."""

    value_committed = Signal(float, float)
    """Emitted with ``(x, y)`` only on mouse release or explicit commit."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        anchors: dict[str, tuple[float, float]] | None = None,
        axis_range: tuple[float, float] = (-1.0, 1.0),
        axis_labels: tuple[str, str] = _DEFAULT_MOOD_AXIS_LABELS,
    ) -> None:
        super().__init__(parent)
        self._axis_min = float(axis_range[0])
        self._axis_max = float(axis_range[1])
        if self._axis_max <= self._axis_min:
            raise ValueError(
                f"axis_range must be increasing, got {axis_range!r}"
            )
        self._anchors = (
            dict(anchors) if anchors is not None else _mood_anchors_as_tuples()
        )
        self._axis_labels = (str(axis_labels[0]), str(axis_labels[1]))
        # Default thumb position at the geometric centre of the axis range.
        centre = (self._axis_min + self._axis_max) / 2.0
        self._valence = centre
        self._energy = centre
        self._dragging = False
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ----- public API ------------------------------------------------------

    def mood(self) -> tuple[float, float]:
        return (self._valence, self._energy)

    def value(self) -> tuple[float, float]:
        """Alias for :meth:`mood` — preferred when the pad isn't a mood pad."""
        return (self._valence, self._energy)

    def set_mood(
        self,
        valence: float,
        energy: float,
        *,
        emit: bool = True,
        emit_commit: bool = False,
    ) -> None:
        v = max(self._axis_min, min(self._axis_max, float(valence)))
        e = max(self._axis_min, min(self._axis_max, float(energy)))
        changed = (v != self._valence) or (e != self._energy)
        if changed:
            self._valence = v
            self._energy = e
            self.update()
            if emit:
                self.mood_changed.emit(v, e)
        if emit_commit:
            self.value_committed.emit(v, e)

    # ----- geometry --------------------------------------------------------

    def _pad_rect(self) -> QRectF:
        side = max(50.0, float(min(self.width(), self.height()) - 2 * _PAD_MARGIN))
        x = (self.width() - side) / 2.0
        y = (self.height() - side) / 2.0
        return QRectF(x, y, side, side)

    def _axis_span(self) -> float:
        return self._axis_max - self._axis_min

    def _point_for_mood(self, valence: float, energy: float) -> QPointF:
        rect = self._pad_rect()
        span = self._axis_span()
        x = rect.left() + (valence - self._axis_min) / span * rect.width()
        # Y axis flipped: axis_max at the top, axis_min at the bottom.
        y = rect.top() + (1.0 - (energy - self._axis_min) / span) * rect.height()
        return QPointF(x, y)

    def _mood_for_point(self, p: QPointF) -> tuple[float, float]:
        rect = self._pad_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            centre = (self._axis_min + self._axis_max) / 2.0
            return (centre, centre)
        span = self._axis_span()
        v = self._axis_min + (p.x() - rect.left()) / rect.width() * span
        e = self._axis_min + (1.0 - (p.y() - rect.top()) / rect.height()) * span
        return (
            max(self._axis_min, min(self._axis_max, v)),
            max(self._axis_min, min(self._axis_max, e)),
        )

    # ----- input -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        v, e = self._mood_for_point(event.position())
        self.set_mood(v, e)
        self._dragging = True
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        v, e = self._mood_for_point(event.position())
        self.set_mood(v, e)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.value_committed.emit(self._valence, self._energy)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ----- painting --------------------------------------------------------

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._pad_rect()

        # Pad background panel + bezel.
        painter.setBrush(QBrush(theme.PANEL_BG_ALT))
        painter.setPen(QPen(theme.PANEL_BORDER, 2))
        painter.drawRoundedRect(rect, 6, 6)

        # Cross-hair at the axis-range midpoint.
        centre_val = (self._axis_min + self._axis_max) / 2.0
        centre = self._point_for_mood(centre_val, centre_val)
        painter.setPen(QPen(theme.INK_DIM, 1, Qt.PenStyle.DashLine))
        painter.drawLine(
            QPointF(rect.left(), centre.y()),
            QPointF(rect.right(), centre.y()),
        )
        painter.drawLine(
            QPointF(centre.x(), rect.top()),
            QPointF(centre.x(), rect.bottom()),
        )

        # Axis labels.
        painter.setPen(QPen(theme.INK_DIM, 1))
        painter.setFont(theme.label_font(size=8))
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 4, rect.width(), 16),
            Qt.AlignmentFlag.AlignCenter,
            self._axis_labels[0],
        )
        painter.save()
        painter.translate(rect.left() - 8, rect.top() + rect.height() / 2)
        painter.rotate(-90)
        painter.drawText(
            QRectF(-rect.height() / 2, -14, rect.height(), 14),
            Qt.AlignmentFlag.AlignCenter,
            self._axis_labels[1],
        )
        painter.restore()

        # Anchor dots + adjacent labels (visual reference only — no hit-rect).
        painter.setFont(theme.label_font(size=9))
        for name, (ax, ay) in self._anchors.items():
            ap = self._point_for_mood(ax, ay)
            painter.setBrush(QBrush(theme.BRASS_DARK))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(ap, _ANCHOR_DOT_RADIUS, _ANCHOR_DOT_RADIUS)
            # Label sits to the right of the dot; if it would run past the
            # pad edge, flip it to the left so it stays inside the bezel.
            label = name.upper()
            label_w = 120.0
            label_h = 14.0
            label_x = ap.x() + _ANCHOR_DOT_RADIUS + _ANCHOR_LABEL_GAP
            alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            if label_x + label_w > rect.right():
                label_x = ap.x() - _ANCHOR_DOT_RADIUS - _ANCHOR_LABEL_GAP - label_w
                alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            painter.setPen(QPen(theme.INK, 1))
            painter.drawText(
                QRectF(label_x, ap.y() - label_h / 2, label_w, label_h),
                alignment,
                label,
            )

        # Draggable thumb.
        thumb = self._point_for_mood(self._valence, self._energy)
        painter.setBrush(QBrush(theme.ACCENT_AMBER))
        painter.setPen(QPen(QColor("#3a1a04"), 2))
        painter.drawEllipse(thumb, _THUMB_RADIUS, _THUMB_RADIUS)
