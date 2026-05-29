"""PatcherView — consolidated song + parts editor for power users.

Stacks the existing :class:`~jtx_gui.views.song_view.SongView` (song-
level header, voices, LFO definitions, global feel) and
:class:`~jtx_gui.views.parts_view.PartsView` (per-part overrides,
arrangement) in a vertical :class:`QSplitter`. Each inner view keeps
its internals — Patcher is purely a composition layer that replaces
the old separate SONG + PARTS sidebar tabs.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from jtx_gui.state import AppState
from jtx_gui.transport import TransportService
from jtx_gui.views.parts_view import PartsView
from jtx_gui.views.song_view import SongView


class PatcherView(QWidget):
    """Power-user editor that bundles SongView + PartsView in a splitter."""

    def __init__(
        self,
        state: AppState,
        *,
        transport: TransportService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._transport = transport

        self._song_view = SongView(state, self)
        self._parts_view = PartsView(state, transport=transport, parent=self)

        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.addWidget(self._song_view)
        self._splitter.addWidget(self._parts_view)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)

    # ----- accessors -------------------------------------------------------

    def song_view(self) -> SongView:
        return self._song_view

    def parts_view(self) -> PartsView:
        return self._parts_view

    def splitter(self) -> QSplitter:
        return self._splitter


__all__ = ["PatcherView"]
