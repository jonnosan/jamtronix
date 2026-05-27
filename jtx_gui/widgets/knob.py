"""KnobWidget — rotary control with a 1950s sci-fi look.

A custom-painted dial that rotates between ``min_value`` and ``max_value``.
Vertical mouse drag and wheel both change the value; double-click opens a
numeric editor. A small dot in the upper-right corner indicates that an
LFO is bound to the knob (set via :meth:`set_modulated`).

This widget knows nothing about the song model. Owners connect
:attr:`value_changed` and write the new value back to the model.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QRadialGradient,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QInputDialog,
    QSizePolicy,
    QWidget,
)

from jtx_gui import theme

# A drag of this many vertical pixels sweeps the whole knob range.
_DRAG_PIXELS_FULL_SWEEP = 200

# Knob arc — slightly more than 3/4 of a circle, opening downward.
# 0 deg = +x axis, counter-clockwise. Min is bottom-left, max bottom-right.
_ARC_START_DEG = 225.0  # bottom-left
_ARC_SPAN_DEG = -270.0  # sweep clockwise to bottom-right


class KnobWidget(QWidget):
    """Rotary knob + numeric readout for one float (or int) knob value."""

    value_changed = Signal(float)

    def __init__(
        self,
        *,
        label: str,
        minimum: float,
        maximum: float,
        value: float,
        step: float = 0.01,
        decimals: int = 2,
        integer: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._min = float(minimum)
        self._max = float(maximum)
        self._step = float(step)
        self._decimals = 0 if integer else decimals
        self._integer = integer
        self._value = self._clamp(float(value))
        self._modulated = False
        self._drag_anchor_y: float | None = None
        self._drag_anchor_value = 0.0

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(74, 96)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(f"{label}\n[{self._min} … {self._max}]")

    # ----- public API ------------------------------------------------------

    def value(self) -> float:
        return self._value

    def set_value(self, v: float, *, emit: bool = True) -> None:
        clamped = self._clamp(v)
        if self._integer:
            clamped = float(round(clamped))
        if clamped == self._value:
            return
        self._value = clamped
        self.update()
        if emit:
            self.value_changed.emit(self._value)

    def set_modulated(self, on: bool) -> None:
        if on != self._modulated:
            self._modulated = on
            self.update()

    # ----- input -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_anchor_y = event.position().y()
            self._drag_anchor_value = self._value
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_anchor_y is None:
            return super().mouseMoveEvent(event)
        dy = self._drag_anchor_y - event.position().y()
        span = self._max - self._min
        delta = (dy / _DRAG_PIXELS_FULL_SWEEP) * span
        # Hold Shift for a fine-tune drag.
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta *= 0.1
        self.set_value(self._drag_anchor_value + delta)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_anchor_y is not None:
            self._drag_anchor_y = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._open_numeric_editor()
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120.0
        if notches == 0:
            return
        if self._integer:
            step = max(1.0, self._step)
        else:
            step = self._step
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            step *= 0.1
        self.set_value(self._value + notches * step)
        event.accept()

    # ----- painting --------------------------------------------------------

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        # Reserve space for the value readout below.
        readout_h = 18
        label_h = 14
        dial_top = label_h
        dial_bottom = h - readout_h
        dial_side = min(w, dial_bottom - dial_top)
        cx = w / 2.0
        cy = dial_top + dial_side / 2.0
        radius = dial_side / 2.0 - 4

        # ----- label (uppercase, stencil) ------------------------------------
        painter.setFont(theme.label_font(size=9))
        painter.setPen(QPen(theme.INK_DIM, 1))
        painter.drawText(
            QRectF(0, 0, w, label_h),
            Qt.AlignmentFlag.AlignCenter,
            self._label.upper(),
        )

        # ----- tick marks ----------------------------------------------------
        painter.setPen(QPen(theme.INK_DIM, 1))
        tick_outer = radius + 4
        tick_inner = radius + 1
        major_inner = radius - 1
        for i in range(11):
            frac = i / 10.0
            angle_deg = _ARC_START_DEG + frac * _ARC_SPAN_DEG
            a = math.radians(angle_deg)
            cos_a = math.cos(a)
            sin_a = math.sin(a)
            # Major tick every 5; longer + bright cream.
            is_major = i % 5 == 0
            inner = major_inner if is_major else tick_inner
            pen = QPen(theme.INK if is_major else theme.INK_DIM, 2 if is_major else 1)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(cx + inner * cos_a, cy - inner * sin_a),
                QPointF(cx + tick_outer * cos_a, cy - tick_outer * sin_a),
            )

        # ----- knob face (brass radial gradient) -----------------------------
        face_rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        grad = QRadialGradient(QPointF(cx - radius * 0.25, cy - radius * 0.35), radius * 1.4)
        grad.setColorAt(0.0, theme.BRASS_HIGHLIGHT)
        grad.setColorAt(0.4, theme.BRASS_LIGHT)
        grad.setColorAt(0.85, theme.BRASS_DARK)
        grad.setColorAt(1.0, QColor("#2a1c0e"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor("#2a1c0e"), 1.5))
        painter.drawEllipse(face_rect)

        # Inner bevel ring for that machined-metal feel.
        painter.setPen(QPen(theme.BRASS_DARK, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(face_rect.adjusted(3, 3, -3, -3))

        # ----- pointer line --------------------------------------------------
        frac = (self._value - self._min) / max(1e-9, (self._max - self._min))
        frac = max(0.0, min(1.0, frac))
        pointer_deg = _ARC_START_DEG + frac * _ARC_SPAN_DEG
        a = math.radians(pointer_deg)
        cos_a = math.cos(a)
        sin_a = math.sin(a)
        pointer_outer = radius - 5
        pointer_inner = radius * 0.25
        painter.setPen(QPen(theme.PANEL_BG, 4))
        painter.drawLine(
            QPointF(cx + pointer_inner * cos_a, cy - pointer_inner * sin_a),
            QPointF(cx + pointer_outer * cos_a, cy - pointer_outer * sin_a),
        )
        painter.setPen(QPen(theme.INK_HOT, 2))
        painter.drawLine(
            QPointF(cx + pointer_inner * cos_a, cy - pointer_inner * sin_a),
            QPointF(cx + pointer_outer * cos_a, cy - pointer_outer * sin_a),
        )

        # Centre cap — small dark dome.
        cap_r = radius * 0.18
        painter.setBrush(QBrush(QColor("#1a1208")))
        painter.setPen(QPen(theme.BRASS_DARK, 1))
        painter.drawEllipse(QPointF(cx, cy), cap_r, cap_r)

        # ----- modulator indicator dot ---------------------------------------
        if self._modulated:
            dot_r = 4.0
            painter.setBrush(QBrush(theme.MOD_DOT))
            painter.setPen(QPen(QColor("#5a1020"), 1))
            painter.drawEllipse(QPointF(w - 8, dial_top + 8), dot_r, dot_r)

        # ----- value readout -------------------------------------------------
        painter.setFont(theme.value_font(size=10))
        painter.setPen(QPen(theme.INK, 1))
        readout_rect = QRectF(0, dial_bottom, w, readout_h)
        painter.drawText(
            readout_rect,
            Qt.AlignmentFlag.AlignCenter,
            self._format_value(),
        )

    # ----- helpers ---------------------------------------------------------

    def _clamp(self, v: float) -> float:
        return max(self._min, min(self._max, v))

    def _format_value(self) -> str:
        if self._integer:
            return f"{int(round(self._value))}"
        return f"{self._value:.{self._decimals}f}"

    def _open_numeric_editor(self) -> None:
        if self._integer:
            int_val, ok = QInputDialog.getInt(
                self,
                self._label,
                f"{self._label} value",
                int(round(self._value)),
                int(self._min),
                int(self._max),
                max(1, int(self._step)),
            )
            if ok:
                self.set_value(float(int_val))
        else:
            float_val, ok = QInputDialog.getDouble(
                self,
                self._label,
                f"{self._label} value",
                self._value,
                self._min,
                self._max,
                self._decimals,
            )
            if ok:
                self.set_value(float(float_val))
