"""MoodPadWidget — 2D pad with 7 anchor snap targets + draggable thumb.

Custom-painted square pad with valence (sad↔happy, X) and energy
(calm↔intense, Y) axes on ``[-1, 1]``. The seven named
:data:`MOOD_ANCHORS` are rendered as labelled hit-rects; clicking
within an anchor's hit-rect snaps the thumb to its canonical
position. Clicks elsewhere place the thumb freely; drag continues
the gesture until the mouse releases.

Owners listen for :attr:`mood_changed` ``(valence, energy)``; the
widget knows nothing about :class:`~jtx.model.Song` — the consumer
(typically :class:`~jtx_gui.views.composer_view.ComposerView`) is
responsible for plumbing values into the composer pipeline at
generate time.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from jtx.composer.mood import MOOD_ANCHORS
from jtx_gui import theme

_ANCHOR_HIT_HALF = 25
"""Half-width (px) of each anchor's snap hit-rect."""

_THUMB_RADIUS = 10
"""Radius (px) of the draggable thumb circle."""

_PAD_MARGIN = 28
"""Padding (px) around the pad square, leaving room for axis labels."""


class MoodPadWidget(QWidget):
    """Square mood pad with 7 named anchor snaps + a draggable thumb."""

    mood_changed = Signal(float, float)
    """Emitted with ``(valence, energy)`` each time the thumb moves."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._valence = 0.0
        self._energy = 0.0
        self._dragging = False
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ----- public API ------------------------------------------------------

    def mood(self) -> tuple[float, float]:
        return (self._valence, self._energy)

    def set_mood(self, valence: float, energy: float, *, emit: bool = True) -> None:
        v = max(-1.0, min(1.0, float(valence)))
        e = max(-1.0, min(1.0, float(energy)))
        if v == self._valence and e == self._energy:
            return
        self._valence = v
        self._energy = e
        self.update()
        if emit:
            self.mood_changed.emit(v, e)

    # ----- geometry --------------------------------------------------------

    def _pad_rect(self) -> QRectF:
        side = max(50.0, float(min(self.width(), self.height()) - 2 * _PAD_MARGIN))
        x = (self.width() - side) / 2.0
        y = (self.height() - side) / 2.0
        return QRectF(x, y, side, side)

    def _point_for_mood(self, valence: float, energy: float) -> QPointF:
        rect = self._pad_rect()
        x = rect.left() + (valence + 1.0) * 0.5 * rect.width()
        # Energy axis flipped: +1 (intense) at the top, -1 (calm) at the bottom.
        y = rect.top() + (1.0 - (energy + 1.0) * 0.5) * rect.height()
        return QPointF(x, y)

    def _mood_for_point(self, p: QPointF) -> tuple[float, float]:
        rect = self._pad_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return (0.0, 0.0)
        v = (p.x() - rect.left()) / rect.width() * 2.0 - 1.0
        e = 1.0 - (p.y() - rect.top()) / rect.height() * 2.0
        return (
            max(-1.0, min(1.0, v)),
            max(-1.0, min(1.0, e)),
        )

    def _anchor_at(self, p: QPointF) -> str | None:
        """Return the anchor name whose hit-rect contains *p*, else None."""
        for name, spec in MOOD_ANCHORS.items():
            ap = self._point_for_mood(spec.valence, spec.energy)
            if (
                abs(p.x() - ap.x()) <= _ANCHOR_HIT_HALF
                and abs(p.y() - ap.y()) <= _ANCHOR_HIT_HALF
            ):
                return name
        return None

    # ----- input -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        p = event.position()
        anchor = self._anchor_at(p)
        if anchor is not None:
            spec = MOOD_ANCHORS[anchor]
            self.set_mood(spec.valence, spec.energy)
        else:
            v, e = self._mood_for_point(p)
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

        # Cross-hair at the (0, 0) origin.
        centre = self._point_for_mood(0.0, 0.0)
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
            "VALENCE  SAD ←→ HAPPY",
        )
        painter.save()
        painter.translate(rect.left() - 8, rect.top() + rect.height() / 2)
        painter.rotate(-90)
        painter.drawText(
            QRectF(-rect.height() / 2, -14, rect.height(), 14),
            Qt.AlignmentFlag.AlignCenter,
            "ENERGY  CALM ←→ INTENSE",
        )
        painter.restore()

        # Anchor labels + hit-rect outlines.
        painter.setFont(theme.label_font(size=9))
        for name, spec in MOOD_ANCHORS.items():
            ap = self._point_for_mood(spec.valence, spec.energy)
            box = QRectF(
                ap.x() - _ANCHOR_HIT_HALF,
                ap.y() - _ANCHOR_HIT_HALF,
                _ANCHOR_HIT_HALF * 2,
                _ANCHOR_HIT_HALF * 2,
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.BRASS_DARK, 1))
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(QPen(theme.INK, 1))
            painter.drawText(
                box,
                Qt.AlignmentFlag.AlignCenter,
                name.upper(),
            )

        # Draggable thumb.
        thumb = self._point_for_mood(self._valence, self._energy)
        painter.setBrush(QBrush(theme.ACCENT_AMBER))
        painter.setPen(QPen(QColor("#3a1a04"), 2))
        painter.drawEllipse(thumb, _THUMB_RADIUS, _THUMB_RADIUS)
