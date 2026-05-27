"""ArrangementEditor — the timeline playlist along the bottom of Parts.

A reorderable horizontal strip of part cells. Each cell shows the part
name + a bar-count spinner. Drag handles reorder. Buttons add/remove
references. The order of cells *is* the arrangement.

Operates directly on ``Song.arrangement`` (a list of part names) and
``Song.parts`` (dict for bar counts). When an arrangement cell's bar
count changes, the underlying ``Part.bars`` is updated.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from jtx.model import Song
from jtx_gui import theme


class ArrangementEditor(QFrame):
    """Bottom strip showing the playlist of part references."""

    def __init__(
        self,
        *,
        song: Song,
        on_dirty: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._song = song
        self._on_dirty = on_dirty

        title = QLabel("ARRANGEMENT")
        title.setObjectName("SectionTitle")

        self._list = QListWidget()
        self._list.setFlow(QListWidget.Flow.LeftToRight)
        self._list.setMovement(QListWidget.Movement.Snap)
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setSpacing(6)
        self._list.setFixedHeight(120)
        self._list.setStyleSheet(
            f"QListWidget {{ background-color: {theme.PANEL_BG_ALT.name()};"
            f" border: 1px solid {theme.PANEL_BORDER.name()}; }}"
        )
        self._list.model().rowsMoved.connect(self._on_rows_moved)

        self._add_combo = QComboBox()
        self._refresh_add_choices()
        add_btn = QPushButton("ADD TO PLAYLIST")
        add_btn.clicked.connect(self._on_add)
        remove_btn = QPushButton("REMOVE SELECTED")
        remove_btn.clicked.connect(self._on_remove)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("APPEND PART:"))
        controls.addWidget(self._add_combo, 1)
        controls.addWidget(add_btn)
        controls.addWidget(remove_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self._list)
        layout.addLayout(controls)

        self._rebuild_cells()

    # ----- public refresh hook --------------------------------------------

    def reload(self) -> None:
        self._refresh_add_choices()
        self._rebuild_cells()

    # ----- cell management ------------------------------------------------

    def _rebuild_cells(self) -> None:
        self._list.clear()
        for index, part_name in enumerate(self._song.arrangement):
            self._add_cell(index, part_name)

    def _add_cell(self, position: int, part_name: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, part_name)

        def bars_changed(n: int, name: str = part_name) -> None:
            self._on_bars_changed(name, n)

        cell = _PartCell(
            part_name=part_name,
            bars=self._song.parts[part_name].bars if part_name in self._song.parts else 0,
            on_bars_changed=bars_changed,
        )
        item.setSizeHint(cell.sizeHint())
        self._list.addItem(item)
        self._list.setItemWidget(item, cell)

    def _on_rows_moved(self, *_args: object) -> None:
        new_order = [
            str(self._list.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self._list.count())
        ]
        if new_order != self._song.arrangement:
            self._song.arrangement = new_order
            self._on_dirty()

    def _on_bars_changed(self, part_name: str, bars: int) -> None:
        if part_name in self._song.parts and self._song.parts[part_name].bars != bars:
            self._song.parts[part_name].bars = bars
            self._on_dirty()

    # ----- add / remove ---------------------------------------------------

    def _refresh_add_choices(self) -> None:
        self._add_combo.clear()
        self._add_combo.addItems(sorted(self._song.parts.keys()))

    def _on_add(self) -> None:
        part_name = self._add_combo.currentText()
        if not part_name or part_name not in self._song.parts:
            return
        self._song.arrangement.append(part_name)
        self._add_cell(len(self._song.arrangement) - 1, part_name)
        self._on_dirty()

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        del self._song.arrangement[row]
        self._list.takeItem(row)
        self._on_dirty()


class _PartCell(QFrame):
    """One arrangement-strip cell — part name + bar-count spinner."""

    def __init__(
        self,
        *,
        part_name: str,
        bars: int,
        on_bars_changed: Callable[[int], None],
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.setFixedSize(160, 92)

        name_lbl = QLabel(part_name.upper())
        name_lbl.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-weight: bold; letter-spacing: 1px;"
        )
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bars_lbl = QLabel("BARS")
        bars_lbl.setObjectName("FieldLabel")
        bars_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        spinner = QSpinBox()
        spinner.setRange(1, 1024)
        spinner.setValue(max(1, bars))
        spinner.valueChanged.connect(on_bars_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        layout.addWidget(name_lbl)
        layout.addWidget(bars_lbl)
        layout.addWidget(spinner)
