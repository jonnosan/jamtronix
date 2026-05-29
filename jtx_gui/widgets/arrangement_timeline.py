"""ArrangementTimeline — horizontal strip of parts as bar-scaled blocks.

A v1 render-only timeline used by the Composer view: each part in
``song.parts`` becomes a coloured block whose width is proportional
to ``part.bars``. Inside each block, a 2-point polyline draws the
intensity envelope (``intensity_start`` → ``intensity_end``) — matching
the linear interp the engine uses in
:meth:`jtx.player.SongPlayer.events_for_bar`.

Clicking a block selects it and emits :attr:`part_selected`. Interactive
drag-to-resize is a follow-up; this widget is read-only for now.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from jtx.model import Song
from jtx_gui import theme

_PALETTE: tuple[QColor, ...] = (
    QColor("#5a4426"),
    QColor("#a07840"),
    QColor("#d4a663"),
    QColor("#7d5a30"),
    QColor("#b08858"),
    QColor("#8a6440"),
)
"""Block fill colours, cycled by part index."""

_GAP_PX = 2
"""Horizontal gap between adjacent part blocks."""

_LABEL_HEIGHT = 16
"""Reserved height for the part-name label above each block."""


class ArrangementTimeline(QWidget):
    """Read-only strip of part blocks with intensity polylines."""

    part_selected = Signal(str)
    """Emitted with the part name when the user clicks a block."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._song: Song | None = None
        self._selected: str | None = None
        # Cached block hit-rects from the last paint, used by mousePressEvent.
        self._block_rects: list[tuple[str, QRectF]] = []
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ----- public API ------------------------------------------------------

    def set_song(self, song: Song | None) -> None:
        """Bind to a song; pass ``None`` to clear."""
        self._song = song
        if song is None or not song.parts:
            self._selected = None
        elif self._selected not in song.parts:
            self._selected = next(iter(song.parts), None)
        self.update()

    def selected_part(self) -> str | None:
        return self._selected

    def set_selected_part(self, name: str | None) -> None:
        if name == self._selected:
            return
        if name is not None and (self._song is None or name not in self._song.parts):
            return
        self._selected = name
        self.update()

    def refresh(self) -> None:
        """Force a repaint after external mutation (e.g. bars change)."""
        self.update()

    # ----- input -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if not self._block_rects:
            return
        x = event.position().x()
        y = event.position().y()
        for name, rect in self._block_rects:
            if rect.left() <= x <= rect.right() and rect.top() <= y <= rect.bottom():
                if name != self._selected:
                    self._selected = name
                    self.update()
                self.part_selected.emit(name)
                event.accept()
                return

    # ----- painting --------------------------------------------------------

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._block_rects = []

        w = float(self.width())
        h = float(self.height())

        # Background.
        painter.fillRect(QRectF(0, 0, w, h), theme.PANEL_BG_ALT)
        painter.setPen(QPen(theme.PANEL_BORDER, 1))
        painter.drawRect(QRectF(0.5, 0.5, w - 1, h - 1))

        if self._song is None or not self._song.parts:
            painter.setPen(QPen(theme.INK_DIM, 1))
            painter.setFont(theme.label_font(size=10))
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "GENERATE A SONG TO SEE THE ARRANGEMENT",
            )
            return

        # Compute proportional widths by bar count.
        names = list(self._song.parts.keys())
        bars_each = [max(1, self._song.parts[n].bars) for n in names]
        total_bars = float(sum(bars_each))
        gap_total = _GAP_PX * max(0, len(names) - 1)
        avail = max(1.0, w - gap_total - 8.0)  # 4px left + right margin
        x = 4.0
        top = _LABEL_HEIGHT + 2.0
        block_h = h - top - 6.0

        painter.setFont(theme.label_font(size=9))
        for index, (name, bars) in enumerate(zip(names, bars_each, strict=False)):
            block_w = avail * (bars / total_bars)
            rect = QRectF(x, top, block_w, block_h)
            self._block_rects.append((name, rect))

            part = self._song.parts[name]
            colour = _PALETTE[index % len(_PALETTE)]
            painter.setBrush(QBrush(colour))
            border_colour = (
                theme.INK_HOT if name == self._selected else theme.BRASS_DARK
            )
            border_width = 2 if name == self._selected else 1
            painter.setPen(QPen(border_colour, border_width))
            painter.drawRoundedRect(rect, 3, 3)

            # Intensity polyline (start, end) → screen y inside the block.
            poly_top = rect.top() + 4.0
            poly_bottom = rect.bottom() - 4.0
            poly_h = max(1.0, poly_bottom - poly_top)
            y_start = poly_bottom - poly_h * max(
                0.0, min(1.0, part.intensity_start),
            )
            y_end = poly_bottom - poly_h * max(
                0.0, min(1.0, part.intensity_end),
            )
            painter.setPen(QPen(theme.INK, 2))
            painter.drawLine(
                QPointF(rect.left() + 4.0, y_start),
                QPointF(rect.right() - 4.0, y_end),
            )

            # Part name above the block.
            label_rect = QRectF(x, 2.0, block_w, _LABEL_HEIGHT)
            painter.setPen(QPen(theme.INK, 1))
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignCenter,
                f"{name}  ({bars} bars)".upper(),
            )

            x += block_w + _GAP_PX


__all__ = ["ArrangementTimeline"]
