"""PartEditorPanel — edit the selected part's bars / intensity / loop / overrides.

Shown beneath the arrangement timeline in the Composer view. Writes
back into the live :class:`~jtx.model.Part` instance on the loaded
song and fires the supplied ``on_dirty`` callback so save state
tracks correctly.

Use :meth:`set_part` to bind a part; :meth:`clear` to detach.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from jtx.model import Part, Song
from jtx_gui import theme
from jtx_gui.widgets.collapsible import CollapsibleSection
from jtx_gui.widgets.knob import KnobWidget


class PartEditorPanel(QFrame):
    """Editor for the currently-selected part on the loaded song."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")

        self._song: Song | None = None
        self._part: Part | None = None
        self._part_name: str | None = None
        self._on_dirty: Callable[[], None] | None = None
        # Set True while we sync widgets from the model so signal
        # handlers don't write the same value straight back.
        self._suspended = False

        self._section = CollapsibleSection("PART EDITOR", expanded=True, parent=self)

        self._title_label = QLabel("(no part selected)")
        self._title_label.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-weight: bold; letter-spacing: 1px;"
        )

        self._bars = QSpinBox()
        self._bars.setRange(1, 1024)
        self._bars.setSuffix(" bars")
        self._bars.valueChanged.connect(self._on_bars_changed)

        self._loop = QCheckBox("LOOP (hold on this part)")
        self._loop.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK_DIM.name()}; }} "
            f"QCheckBox:checked {{ color: {theme.INK_HOT.name()}; }}"
        )
        self._loop.toggled.connect(self._on_loop_toggled)

        self._intensity_start = KnobWidget(
            label="start",
            minimum=0.0,
            maximum=1.0,
            value=0.5,
            step=0.05,
            decimals=2,
        )
        self._intensity_start.value_changed.connect(self._on_intensity_start)
        self._intensity_end = KnobWidget(
            label="end",
            minimum=0.0,
            maximum=1.0,
            value=0.5,
            step=0.05,
            decimals=2,
        )
        self._intensity_end.value_changed.connect(self._on_intensity_end)

        intensity_label = QLabel("INTENSITY")
        intensity_label.setObjectName("FieldLabel")
        intensity_row = QHBoxLayout()
        intensity_row.setSpacing(8)
        intensity_row.addWidget(intensity_label)
        intensity_row.addWidget(self._intensity_start)
        intensity_row.addWidget(self._intensity_end)
        intensity_row.addStretch(1)

        self._tempo_check = QCheckBox("OVERRIDE TEMPO")
        self._tempo_check.setStyleSheet(self._loop.styleSheet())
        self._tempo_check.toggled.connect(self._on_tempo_toggle)
        self._tempo_spin = QSpinBox()
        self._tempo_spin.setRange(30, 300)
        self._tempo_spin.setSuffix(" BPM")
        self._tempo_spin.valueChanged.connect(self._on_tempo_value)

        self._meter_check = QCheckBox("OVERRIDE METER")
        self._meter_check.setStyleSheet(self._loop.styleSheet())
        self._meter_check.toggled.connect(self._on_meter_toggle)
        self._meter_edit = QLineEdit()
        self._meter_edit.setMaximumWidth(96)
        self._meter_edit.editingFinished.connect(self._on_meter_edit)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("BARS"), 0, 0)
        grid.addWidget(self._bars, 0, 1)
        grid.addWidget(self._loop, 0, 2, 1, 2)
        grid.addWidget(self._tempo_check, 1, 0, 1, 2)
        grid.addWidget(self._tempo_spin, 1, 2)
        grid.addWidget(self._meter_check, 2, 0, 1, 2)
        grid.addWidget(self._meter_edit, 2, 2)
        grid.setColumnStretch(3, 1)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)
        body_layout.addWidget(self._title_label)
        body_layout.addLayout(grid)
        body_layout.addLayout(intensity_row)
        self._section.add_widget(body)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section)

        self._set_inputs_enabled(False)

    # ----- public API ------------------------------------------------------

    def set_part(
        self,
        *,
        song: Song,
        part_name: str,
        on_dirty: Callable[[], None],
    ) -> None:
        """Bind the editor to ``song.parts[part_name]``.

        Field changes write back into the live :class:`Part` instance
        and call ``on_dirty()`` so the AppState dirty flag tracks.
        """
        if part_name not in song.parts:
            self.clear()
            return
        self._song = song
        self._part_name = part_name
        self._part = song.parts[part_name]
        self._on_dirty = on_dirty
        self._refresh_fields()
        self._set_inputs_enabled(True)

    def clear(self) -> None:
        """Detach from any part — disables inputs and shows placeholder text."""
        self._song = None
        self._part = None
        self._part_name = None
        self._on_dirty = None
        self._title_label.setText("(no part selected)")
        self._set_inputs_enabled(False)

    def current_part_name(self) -> str | None:
        return self._part_name

    # ----- field sync ------------------------------------------------------

    def _refresh_fields(self) -> None:
        if self._part is None or self._song is None or self._part_name is None:
            return
        self._suspended = True
        try:
            self._title_label.setText(self._part_name.upper())
            self._bars.setValue(int(self._part.bars))
            self._loop.setChecked(bool(self._part.loop))
            self._intensity_start.set_value(
                float(self._part.intensity_start), emit=False,
            )
            self._intensity_end.set_value(
                float(self._part.intensity_end), emit=False,
            )

            tempo_overridden = self._part.tempo is not None
            self._tempo_check.setChecked(tempo_overridden)
            self._tempo_spin.setEnabled(tempo_overridden)
            self._tempo_spin.setValue(int(self._part.tempo or self._song.tempo))

            meter_overridden = self._part.meter is not None
            self._meter_check.setChecked(meter_overridden)
            self._meter_edit.setEnabled(meter_overridden)
            self._meter_edit.setText(str(self._part.meter or self._song.meter))
        finally:
            self._suspended = False

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (
            self._bars,
            self._loop,
            self._intensity_start,
            self._intensity_end,
            self._tempo_check,
            self._meter_check,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self._tempo_spin.setEnabled(False)
            self._meter_edit.setEnabled(False)

    # ----- write-back handlers --------------------------------------------

    def _mark_dirty(self) -> None:
        if self._on_dirty is not None:
            self._on_dirty()

    def _on_bars_changed(self, value: int) -> None:
        if self._suspended or self._part is None:
            return
        if value == self._part.bars:
            return
        self._part.bars = int(value)
        self._mark_dirty()

    def _on_loop_toggled(self, checked: bool) -> None:
        if self._suspended or self._part is None:
            return
        if checked == self._part.loop:
            return
        self._part.loop = bool(checked)
        self._mark_dirty()

    def _on_intensity_start(self, value: float) -> None:
        if self._suspended or self._part is None:
            return
        new_value = float(value)
        if new_value == self._part.intensity_start:
            return
        self._part.intensity_start = new_value
        self._mark_dirty()

    def _on_intensity_end(self, value: float) -> None:
        if self._suspended or self._part is None:
            return
        new_value = float(value)
        if new_value == self._part.intensity_end:
            return
        self._part.intensity_end = new_value
        self._mark_dirty()

    def _on_tempo_toggle(self, checked: bool) -> None:
        if self._suspended or self._part is None:
            return
        self._tempo_spin.setEnabled(checked)
        new_tempo = self._tempo_spin.value() if checked else None
        if new_tempo == self._part.tempo:
            return
        self._part.tempo = new_tempo
        self._mark_dirty()

    def _on_tempo_value(self, value: int) -> None:
        if self._suspended or self._part is None:
            return
        if not self._tempo_check.isChecked():
            return
        if value == self._part.tempo:
            return
        self._part.tempo = int(value)
        self._mark_dirty()

    def _on_meter_toggle(self, checked: bool) -> None:
        if self._suspended or self._part is None or self._song is None:
            return
        self._meter_edit.setEnabled(checked)
        new_meter = self._meter_edit.text().strip() or self._song.meter if checked else None
        if new_meter == self._part.meter:
            return
        self._part.meter = new_meter
        self._mark_dirty()

    def _on_meter_edit(self) -> None:
        if self._suspended or self._part is None:
            return
        if not self._meter_check.isChecked():
            return
        new_meter = self._meter_edit.text().strip()
        if not new_meter or new_meter == self._part.meter:
            return
        self._part.meter = new_meter
        self._mark_dirty()


__all__ = ["PartEditorPanel"]
