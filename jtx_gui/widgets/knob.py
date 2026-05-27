"""KnobWidget — rotary control with a 1950s sci-fi look.

A custom-painted dial that rotates between ``min_value`` and ``max_value``.

Interactions:
* Click + drag (up/right increase, down/left decrease).
* Click on the arc — jumps to the value at that angle.
* Scroll wheel / two-finger trackpad scroll — step adjust.
* Double-click — opens a numeric editor.
* Hold Shift during any of the above for fine-tune (1/10th sensitivity).

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

# A drag of this many pixels (max of |dx|, |dy|) sweeps the whole knob range.
# 100 px is roughly the height of one knob — a wrist-flick is enough to
# go end-to-end without leaving the widget.
_DRAG_PIXELS_FULL_SWEEP = 100

# Trackpad pixel-scroll: how many pixels of scroll per knob step.
_PIXELS_PER_STEP = 8

# Click-to-set tolerance: how close (relative to radius) the click has to
# be to the dial arc to count as a "jump to this angle" gesture. Clicks
# inside the centre cap won't jump — only drag.
_CLICK_TO_SET_RADIUS_FRAC = 0.35

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
        self._drag_anchor: QPointF | None = None
        self._drag_anchor_value = 0.0
        # Cached centre + radius from the last paint; click-to-set
        # needs them in widget-local coords.
        self._dial_centre = QPointF(0, 0)
        self._dial_radius = 1.0
        # Pixel-scroll accumulator so trackpad scroll feels stepped
        # (pixelDelta() comes in granular ~1px increments per gesture).
        self._wheel_pixel_accum = 0.0

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(74, 96)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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

    def set_range(self, minimum: float, maximum: float) -> None:
        """Update the knob's min/max, clamping the current value to fit."""
        self._min = float(minimum)
        self._max = float(maximum)
        clamped = self._clamp(self._value)
        if clamped != self._value:
            self._value = clamped
            self.value_changed.emit(self._value)
        self.setToolTip(f"{self._label}\n[{self._min} … {self._max}]")
        self.update()

    # ----- input -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position()
        # If the click landed on the dial arc, jump to that angle first
        # so the drag continues from the clicked position. Clicks well
        # inside the centre cap just start a drag without a jump.
        dx = pos.x() - self._dial_centre.x()
        dy = pos.y() - self._dial_centre.y()
        dist = math.hypot(dx, dy)
        radius = max(1.0, self._dial_radius)
        if dist > radius * _CLICK_TO_SET_RADIUS_FRAC:
            self.set_value(self._value_for_angle(dx, dy))
        self._drag_anchor = QPointF(pos)
        self._drag_anchor_value = self._value
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_anchor is None:
            super().mouseMoveEvent(event)
            return
        pos = event.position()
        dx = pos.x() - self._drag_anchor.x()
        dy = self._drag_anchor.y() - pos.y()  # up = positive
        # Combine X + Y so the drag works in any direction. Use the
        # larger absolute component so diagonal drags don't double up.
        delta_px = dy if abs(dy) >= abs(dx) else dx
        span = self._max - self._min
        delta = (delta_px / _DRAG_PIXELS_FULL_SWEEP) * span
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta *= 0.1
        self.set_value(self._drag_anchor_value + delta)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_anchor is not None:
            self._drag_anchor = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._open_numeric_editor()
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        # macOS trackpad sends pixelDelta (granular px); classic mouse
        # wheel sends angleDelta in 1/8°-detents (120 per notch).
        # Handle both.
        step = max(1.0, self._step) if self._integer else self._step
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            step *= 0.1

        pixel_dy = event.pixelDelta().y()
        if pixel_dy != 0:
            self._wheel_pixel_accum += pixel_dy
            steps = int(self._wheel_pixel_accum / _PIXELS_PER_STEP)
            if steps:
                self._wheel_pixel_accum -= steps * _PIXELS_PER_STEP
                self.set_value(self._value + steps * step)
            event.accept()
            return

        notches = event.angleDelta().y() / 120.0
        if notches == 0:
            return
        self.set_value(self._value + notches * step)
        event.accept()

    # ----- click-to-angle resolution -------------------------------------

    def _value_for_angle(self, dx: float, dy: float) -> float:
        """Return the knob value that would put the pointer under (dx, dy)."""
        # math.atan2 returns radians in (-pi, pi], measured from +x with
        # +y going *up*. Qt has +y going *down*, so negate dy. Then
        # convert to degrees in [0, 360) and project onto the arc.
        angle_deg = math.degrees(math.atan2(-dy, dx)) % 360.0
        # Find fraction along the arc from start (225°) sweeping by
        # -270° (i.e. clockwise to -45° / 315°).
        # Convert click angle into "degrees clockwise from arc start".
        clockwise_from_start = (_ARC_START_DEG - angle_deg) % 360.0
        # Arc spans 270° clockwise; clicks outside the arc gap (the
        # bottom 90° between 315° and 225°) snap to the nearest end.
        if clockwise_from_start > 270.0:
            # Closer to min (0) if past min side; max otherwise.
            mid_gap = 270.0 + 45.0  # 315° from start = bottom of arc gap
            frac = 0.0 if clockwise_from_start > mid_gap else 1.0
        else:
            frac = clockwise_from_start / 270.0
        span = self._max - self._min
        return self._min + frac * span

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
        # Cache for click-to-set hit testing.
        self._dial_centre = QPointF(cx, cy)
        self._dial_radius = radius

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
