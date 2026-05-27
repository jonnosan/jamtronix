"""Parts view — per-part override editor + arrangement editor.

Layout:
- left sidebar: list of parts (click to select); add/remove/rename buttons
- right: detail pane for the selected part — key/meter/algorithm/knob
  overrides per voice
- bottom: arrangement editor (drag/reorder + bar counts)

Override semantics (mirroring docs/SPEC.md §Knob Scope):
- A part's ``VoiceOverride`` can hold ``algorithm``, ``key``, ``meter``,
  partial ``pattern`` knob dict, partial ``feel`` knob dict.
- Anything not in the override inherits from the song-level
  ``VoiceConfig`` (or its algorithm's default).
- Toggling the OVERRIDE checkbox on a field writes/removes its key.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from jtx.model import Key, Part, Song, VoiceConfig, VoiceOverride
from jtx_gui import theme
from jtx_gui.algorithm_meta import (
    FEEL_KNOBS,
    SCHEMAS,
    KnobSpec,
    algorithms_for,
)
from jtx_gui.state import AppState
from jtx_gui.transport import TransportService
from jtx_gui.views.song_view import _SCALES, _TONICS, _clear_layout, _infer_voice_type
from jtx_gui.widgets.collapsible import CollapsibleSection
from jtx_gui.widgets.override import OverrideField, OverrideRow

_KNOBS_PER_ROW = 4


class PartsView(QWidget):
    """Top-level Parts editor pane.

    Layout: left = parts list with per-row PLAY + LOOP toggles + active
    highlight (driven by ``TransportService.part_changed``); right =
    detail pane for the selected part's per-voice overrides. The
    Live view is gone; transport controls live in the top toolbar
    and the arrangement now comes from natural parts order (advance
    or loop per ``Part.loop``).
    """

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
        self._current_part: str | None = None
        self._active_part: str | None = None

        self._empty_label = QLabel("Open a .jtx file from the File menu to begin.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {theme.INK_DIM.name()}; font-size: 14pt; padding: 80px;"
        )

        # ----- list sidebar -----
        self._list = QListWidget()
        self._list.setMinimumWidth(320)
        self._list.setMaximumWidth(380)
        self._list.itemSelectionChanged.connect(self._on_select_part)

        add_btn = QPushButton("ADD")
        rename_btn = QPushButton("RENAME")
        remove_btn = QPushButton("REMOVE")
        add_btn.clicked.connect(self._on_add_part)
        rename_btn.clicked.connect(self._on_rename_part)
        remove_btn.clicked.connect(self._on_remove_part)

        list_buttons = QHBoxLayout()
        list_buttons.setSpacing(4)
        list_buttons.addWidget(add_btn)
        list_buttons.addWidget(rename_btn)
        list_buttons.addWidget(remove_btn)

        list_column = QVBoxLayout()
        list_column.setContentsMargins(0, 0, 0, 0)
        list_column.setSpacing(6)
        list_title = QLabel("PARTS")
        list_title.setObjectName("SectionTitle")
        list_column.addWidget(list_title)
        list_column.addWidget(self._list, 1)
        list_column.addLayout(list_buttons)
        list_widget = QWidget()
        list_widget.setLayout(list_column)

        # ----- detail pane -----
        self._detail = QScrollArea()
        self._detail.setWidgetResizable(True)
        self._detail_inner = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_inner)
        self._detail_layout.setContentsMargins(14, 12, 14, 14)
        self._detail_layout.setSpacing(12)
        self._detail.setWidget(self._detail_inner)

        # ----- splitter for list + detail -----
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(list_widget)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # ----- assemble -----
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)
        content_layout.addWidget(splitter, 1)
        self._content.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._empty_label)
        root.addWidget(self._content)

        self._state.song_changed.connect(self._refresh_part_list)
        if self._transport is not None:
            self._transport.part_changed.connect(self._on_transport_part_changed)
            self._transport.stopped.connect(self._on_transport_stopped)
        self._refresh_part_list()

    # ----- list management -------------------------------------------------

    def _refresh_part_list(self) -> None:
        song = self._state.song
        if song is None:
            self._empty_label.setVisible(True)
            self._content.setVisible(False)
            return
        self._empty_label.setVisible(False)
        self._content.setVisible(True)

        previous = self._current_part
        self._list.blockSignals(True)
        self._list.clear()
        for name, part in song.parts.items():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, name)
            row = _PartListRow(
                name=name,
                part=part,
                on_play=self._on_play_part,
                on_loop_toggle=self._on_loop_toggle,
                on_bars_changed=self._on_bars_changed,
            )
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        self._list.blockSignals(False)

        # Select previous if still present; else first.
        if previous and previous in song.parts:
            self._select_by_name(previous)
        elif song.parts:
            self._list.setCurrentRow(0)
        else:
            self._current_part = None
            _clear_layout(self._detail_layout)

        self._restyle_rows()

    def _select_by_name(self, name: str) -> None:
        for i in range(self._list.count()):
            if str(self._list.item(i).data(Qt.ItemDataRole.UserRole)) == name:
                self._list.setCurrentRow(i)
                return

    def _on_select_part(self) -> None:
        items = self._list.selectedItems()
        if not items:
            self._current_part = None
            _clear_layout(self._detail_layout)
            return
        name = str(items[0].data(Qt.ItemDataRole.UserRole))
        if name == self._current_part:
            return
        self._current_part = name
        self._rebuild_detail()

    def _restyle_rows(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            widget = self._list.itemWidget(item)
            if isinstance(widget, _PartListRow):
                widget.set_active(widget.part_name == self._active_part)

    def _on_play_part(self, name: str) -> None:
        if self._transport is None:
            return
        if self._transport.is_running:
            self._transport.queue_part(name)
        else:
            QMessageBox.information(
                self,
                "Not playing",
                "Hit PLAY in the toolbar to start playback; the parts list "
                "queues jumps once the transport is running.",
            )

    def _on_loop_toggle(self, name: str, value: bool) -> None:
        song = self._state.song
        if song is None or name not in song.parts:
            return
        song.parts[name].loop = value
        self._state.mark_dirty()

    def _on_bars_changed(self, name: str, value: int) -> None:
        song = self._state.song
        if song is None or name not in song.parts:
            return
        if song.parts[name].bars == value:
            return
        song.parts[name].bars = value
        self._state.mark_dirty()

    def _on_transport_part_changed(self, name: str) -> None:
        self._active_part = name
        self._restyle_rows()

    def _on_transport_stopped(self) -> None:
        self._active_part = None
        self._restyle_rows()

    def _on_add_part(self) -> None:
        song = self._state.song
        if song is None:
            return
        name, ok = QInputDialog.getText(self, "New part", "Part name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in song.parts:
            QMessageBox.warning(self, "Duplicate", f"Part {name!r} already exists.")
            return
        song.parts[name] = Part(bars=16)
        self._state.notify_structural_change()
        self._select_by_name(name)

    def _on_rename_part(self) -> None:
        if self._current_part is None or self._state.song is None:
            return
        old = self._current_part
        new, ok = QInputDialog.getText(self, "Rename part", "New name:", text=old)
        if not ok:
            return
        new = new.strip()
        if not new or new == old:
            return
        song = self._state.song
        if new in song.parts:
            QMessageBox.warning(self, "Duplicate", f"Part {new!r} already exists.")
            return
        song.parts[new] = song.parts.pop(old)
        song.arrangement = [new if p == old else p for p in song.arrangement]
        self._state.notify_structural_change()
        self._select_by_name(new)

    def _on_remove_part(self) -> None:
        if self._current_part is None or self._state.song is None:
            return
        name = self._current_part
        if (
            QMessageBox.question(
                self,
                "Remove part",
                f"Remove part {name!r}? It will also disappear from the arrangement.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        song = self._state.song
        del song.parts[name]
        song.arrangement = [p for p in song.arrangement if p != name]
        self._state.notify_structural_change()

    # ----- detail pane -----------------------------------------------------

    def _rebuild_detail(self) -> None:
        _clear_layout(self._detail_layout)
        song = self._state.song
        if song is None or self._current_part is None:
            return
        part = song.parts[self._current_part]

        header = _PartHeaderPanel(
            song=song,
            part_name=self._current_part,
            part=part,
            on_dirty=self._state.mark_dirty,
        )
        self._detail_layout.addWidget(header)

        for voice_name, voice_config in song.voices.items():
            panel = _VoiceOverridePanel(
                voice_name=voice_name,
                song_config=voice_config,
                part=part,
                on_dirty=self._state.mark_dirty,
            )
            self._detail_layout.addWidget(panel)

        self._detail_layout.addStretch(1)


# --------------------------------------------------------------------------
#                          part-header panel
# --------------------------------------------------------------------------


class _PartHeaderPanel(QFrame):
    """Top of the part-detail pane: bars + part-level tempo + meter overrides."""

    def __init__(
        self,
        *,
        song: Song,
        part_name: str,
        part: Part,
        on_dirty: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._song = song
        self._part = part
        self._on_dirty = on_dirty

        title = QLabel(part_name.upper())
        title.setObjectName("SectionTitle")

        bars_label = QLabel("BARS")
        bars_label.setObjectName("FieldLabel")
        bars = QSpinBox()
        bars.setRange(1, 1024)
        bars.setValue(part.bars)

        def emit_bars(value: int) -> None:
            if value != part.bars:
                part.bars = value
                on_dirty()

        bars.valueChanged.connect(emit_bars)

        bars_row = QHBoxLayout()
        bars_row.setSpacing(8)
        bars_row.addWidget(bars_label)
        bars_row.addWidget(bars)
        bars_row.addStretch(1)

        tempo_row = self._make_tempo_row()
        meter_row = self._make_meter_row()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addLayout(bars_row)
        layout.addLayout(tempo_row)
        layout.addLayout(meter_row)

    # ----- tempo override -------------------------------------------------

    def _make_tempo_row(self) -> QHBoxLayout:
        self._tempo_check = QCheckBox("OVERRIDE TEMPO")
        self._tempo_check.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK_DIM.name()}; }} "
            f"QCheckBox:checked {{ color: {theme.INK_HOT.name()}; }}"
        )
        is_overridden = self._part.tempo is not None
        self._tempo_check.setChecked(is_overridden)

        self._tempo_spin = QSpinBox()
        self._tempo_spin.setRange(30, 300)
        self._tempo_spin.setSuffix(" BPM")
        self._tempo_spin.setValue(self._part.tempo or self._song.tempo)
        self._tempo_spin.setEnabled(is_overridden)

        self._tempo_check.toggled.connect(self._on_tempo_toggle)
        self._tempo_spin.valueChanged.connect(self._on_tempo_change)

        inherited = QLabel(f"(song = {self._song.tempo} BPM)")
        inherited.setStyleSheet(f"color: {theme.INK_DIM.name()};")

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._tempo_check)
        row.addWidget(self._tempo_spin)
        row.addWidget(inherited, 1)
        return row

    def _on_tempo_toggle(self, checked: bool) -> None:
        self._tempo_spin.setEnabled(checked)
        self._part.tempo = self._tempo_spin.value() if checked else None
        self._on_dirty()

    def _on_tempo_change(self, value: int) -> None:
        if self._tempo_check.isChecked():
            self._part.tempo = value
            self._on_dirty()

    # ----- meter override -------------------------------------------------

    def _make_meter_row(self) -> QHBoxLayout:
        self._meter_check = QCheckBox("OVERRIDE METER")
        self._meter_check.setStyleSheet(self._tempo_check.styleSheet())
        is_overridden = self._part.meter is not None
        self._meter_check.setChecked(is_overridden)

        self._meter_edit = QLineEdit(self._part.meter or self._song.meter)
        self._meter_edit.setMaximumWidth(96)
        self._meter_edit.setEnabled(is_overridden)

        self._meter_check.toggled.connect(self._on_meter_toggle)
        self._meter_edit.editingFinished.connect(self._on_meter_change)

        inherited = QLabel(f"(song = {self._song.meter})")
        inherited.setStyleSheet(f"color: {theme.INK_DIM.name()};")

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._meter_check)
        row.addWidget(self._meter_edit)
        row.addWidget(inherited, 1)
        return row

    def _on_meter_toggle(self, checked: bool) -> None:
        self._meter_edit.setEnabled(checked)
        self._part.meter = self._meter_edit.text().strip() if checked else None
        self._on_dirty()

    def _on_meter_change(self) -> None:
        if self._meter_check.isChecked():
            self._part.meter = self._meter_edit.text().strip()
            self._on_dirty()


# --------------------------------------------------------------------------
#                          voice override panel
# --------------------------------------------------------------------------


class _VoiceOverridePanel(QFrame):
    """One voice's overrides for the currently-selected part.

    Keeps a stable reference to the ``Part``; reads the
    ``VoiceOverride`` from ``part.voice_overrides`` on demand so we
    never hold a stale reference after creating one lazily.
    """

    def __init__(
        self,
        *,
        voice_name: str,
        song_config: VoiceConfig,
        part: Part,
        on_dirty: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._voice_name = voice_name
        self._song_config = song_config
        self._part = part
        self._on_dirty = on_dirty

        title = QLabel(f"{voice_name.upper()}  ·  inheriting from song")
        title.setObjectName("SectionTitle")
        self._title_label = title

        self._algo_override_chk = QCheckBox("OVERRIDE ALGORITHM")
        self._algo_override_chk.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK_DIM.name()}; }} "
            f"QCheckBox:checked {{ color: {theme.INK_HOT.name()}; }}"
        )
        self._algo_combo = QComboBox()
        voice_type = _infer_voice_type(song_config.algorithm)
        for meta in algorithms_for(voice_type):
            self._algo_combo.addItem(meta.name)
        override = self._override()
        algo_value = (
            override.algorithm
            if override is not None and override.algorithm
            else song_config.algorithm
        )
        if self._algo_combo.findText(algo_value) < 0:
            self._algo_combo.addItem(algo_value)
        self._algo_combo.setCurrentText(algo_value)

        algo_is_overridden = override is not None and override.algorithm is not None
        self._algo_override_chk.setChecked(algo_is_overridden)
        self._algo_combo.setEnabled(algo_is_overridden)
        self._algo_override_chk.toggled.connect(self._on_algo_toggle)
        self._algo_combo.currentTextChanged.connect(self._on_algo_change)

        algo_row = QHBoxLayout()
        algo_row.addWidget(self._algo_override_chk)
        algo_row.addWidget(self._algo_combo, 1)

        self._key_override_chk = QCheckBox("OVERRIDE KEY")
        self._key_override_chk.setStyleSheet(self._algo_override_chk.styleSheet())
        self._key_tonic = QComboBox()
        self._key_tonic.addItems(list(_TONICS))
        self._key_scale = QComboBox()
        self._key_scale.addItems(list(_SCALES))
        current_key: Key | None = override.key if override is not None else None
        if current_key is not None:
            self._key_override_chk.setChecked(True)
            if self._key_tonic.findText(current_key.tonic) < 0:
                self._key_tonic.addItem(current_key.tonic)
            if self._key_scale.findText(current_key.scale) < 0:
                self._key_scale.addItem(current_key.scale)
            self._key_tonic.setCurrentText(current_key.tonic)
            self._key_scale.setCurrentText(current_key.scale)
        self._key_tonic.setEnabled(self._key_override_chk.isChecked())
        self._key_scale.setEnabled(self._key_override_chk.isChecked())
        self._key_override_chk.toggled.connect(self._on_key_toggle)
        self._key_tonic.currentTextChanged.connect(self._on_key_change)
        self._key_scale.currentTextChanged.connect(self._on_key_change)

        key_row = QHBoxLayout()
        key_row.addWidget(self._key_override_chk)
        key_row.addWidget(QLabel("TONIC"))
        key_row.addWidget(self._key_tonic)
        key_row.addWidget(QLabel("SCALE"))
        key_row.addWidget(self._key_scale, 1)

        self._meter_override_chk = QCheckBox("OVERRIDE METER")
        self._meter_override_chk.setStyleSheet(self._algo_override_chk.styleSheet())
        self._meter_edit = QLineEdit()
        self._meter_edit.setMaximumWidth(96)
        current_meter = override.meter if override is not None else None
        if current_meter is not None:
            self._meter_override_chk.setChecked(True)
            self._meter_edit.setText(current_meter)
        self._meter_edit.setEnabled(self._meter_override_chk.isChecked())
        self._meter_override_chk.toggled.connect(self._on_meter_toggle)
        self._meter_edit.editingFinished.connect(self._on_meter_change)

        meter_row = QHBoxLayout()
        meter_row.addWidget(self._meter_override_chk)
        meter_row.addWidget(self._meter_edit)
        meter_row.addStretch(1)

        # ----- knob sections -----
        self._pattern_section = CollapsibleSection("Pattern Knobs", expanded=True)
        self._feel_section = CollapsibleSection("Feel Knobs", expanded=False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addLayout(algo_row)
        layout.addLayout(key_row)
        layout.addLayout(meter_row)
        layout.addWidget(self._pattern_section)
        layout.addWidget(self._feel_section)

        self._rebuild_knob_sections()
        self._sync_title()

    # ----- override accessor helpers --------------------------------------

    def _override(self) -> VoiceOverride | None:
        return self._part.voice_overrides.get(self._voice_name)

    def _ensure_override(self) -> VoiceOverride:
        override = self._override()
        if override is None:
            override = VoiceOverride()
            self._part.voice_overrides[self._voice_name] = override
        return override

    def _drop_override_if_empty(self) -> None:
        override = self._override()
        if override is None:
            return
        if (
            override.algorithm is None
            and override.key is None
            and override.meter is None
            and not override.pattern
            and not override.feel
        ):
            del self._part.voice_overrides[self._voice_name]

    # ----- algorithm override --------------------------------------------

    def _on_algo_toggle(self, checked: bool) -> None:
        if checked:
            self._ensure_override().algorithm = self._algo_combo.currentText()
        else:
            existing = self._override()
            if existing is not None:
                existing.algorithm = None
            self._drop_override_if_empty()
        self._algo_combo.setEnabled(checked)
        self._rebuild_knob_sections()
        self._on_dirty()
        self._sync_title()

    def _on_algo_change(self, new_algo: str) -> None:
        if not self._algo_override_chk.isChecked():
            return
        override = self._ensure_override()
        if override.algorithm == new_algo:
            return
        override.algorithm = new_algo
        # Drop pattern keys belonging to the previous override algorithm
        # but absent from the new one. (Unknown keys survive.)
        new_schema = SCHEMAS.pattern_by_algo.get(new_algo, {})
        if new_schema:
            override.pattern = {k: v for k, v in override.pattern.items() if k in new_schema}
        self._rebuild_knob_sections()
        self._on_dirty()

    # ----- key override --------------------------------------------------

    def _on_key_toggle(self, checked: bool) -> None:
        self._key_tonic.setEnabled(checked)
        self._key_scale.setEnabled(checked)
        if checked:
            self._ensure_override().key = Key(
                tonic=self._key_tonic.currentText(),
                scale=self._key_scale.currentText(),
            )
        else:
            existing = self._override()
            if existing is not None:
                existing.key = None
            self._drop_override_if_empty()
        self._on_dirty()
        self._sync_title()

    def _on_key_change(self, _text: str) -> None:
        if not self._key_override_chk.isChecked():
            return
        override = self._ensure_override()
        override.key = Key(
            tonic=self._key_tonic.currentText(),
            scale=self._key_scale.currentText(),
        )
        self._on_dirty()

    # ----- meter override ------------------------------------------------

    def _on_meter_toggle(self, checked: bool) -> None:
        self._meter_edit.setEnabled(checked)
        if checked:
            self._ensure_override().meter = self._meter_edit.text() or "4/4"
        else:
            existing = self._override()
            if existing is not None:
                existing.meter = None
            self._drop_override_if_empty()
        self._on_dirty()
        self._sync_title()

    def _on_meter_change(self) -> None:
        if not self._meter_override_chk.isChecked():
            return
        override = self._ensure_override()
        override.meter = self._meter_edit.text()
        self._on_dirty()

    # ----- knob sections (effective algorithm drives schema) ---------------

    def _effective_algorithm(self) -> str:
        override = self._override()
        if override is not None and override.algorithm is not None:
            return override.algorithm
        return self._song_config.algorithm

    def _rebuild_knob_sections(self) -> None:
        _clear_layout(self._pattern_section.body_layout())
        _clear_layout(self._feel_section.body_layout())

        algo = self._effective_algorithm()
        algo_schema = SCHEMAS.pattern_by_algo.get(algo, {})
        override = self._override()

        # Pattern knobs.
        row = OverrideRow()
        count_in_row = 0
        total_pattern = 0
        for spec in algo_schema.values():
            inherited = self._inherited_pattern_value(spec)
            override_value = (
                override.pattern.get(spec.name)
                if override is not None and spec.name in override.pattern
                else None
            )
            field = OverrideField(
                spec=spec,
                inherited_value=inherited,
                override_value=override_value,
                on_override_toggle=_make_pattern_toggle(self, spec.name),
                on_value_change=_make_pattern_setter(self, spec.name),
            )
            row.add(field)
            total_pattern += 1
            count_in_row += 1
            if count_in_row >= _KNOBS_PER_ROW:
                row.fill()
                self._pattern_section.add_widget(row)
                row = OverrideRow()
                count_in_row = 0
        if count_in_row:
            row.fill()
            self._pattern_section.add_widget(row)
        self._pattern_section.set_header_hint(f"{total_pattern} knobs")

        # Feel knobs (universal).
        row = OverrideRow()
        count_in_row = 0
        for spec in FEEL_KNOBS:
            inherited = self._song_config.feel.get(spec.name, spec.default)
            override_value = (
                override.feel.get(spec.name)
                if override is not None and spec.name in override.feel
                else None
            )
            field = OverrideField(
                spec=spec,
                inherited_value=inherited,
                override_value=override_value,
                on_override_toggle=_make_feel_toggle(self, spec.name),
                on_value_change=_make_feel_setter(self, spec.name),
            )
            row.add(field)
            count_in_row += 1
            if count_in_row >= _KNOBS_PER_ROW:
                row.fill()
                self._feel_section.add_widget(row)
                row = OverrideRow()
                count_in_row = 0
        if count_in_row:
            row.fill()
            self._feel_section.add_widget(row)
        self._feel_section.set_header_hint(f"{len(FEEL_KNOBS)} knobs")

    def _inherited_pattern_value(self, spec: KnobSpec) -> object:
        # Song-level voice value (if any) wins over the algorithm default.
        if spec.name in self._song_config.pattern:
            return self._song_config.pattern[spec.name]
        # If the song-level voice runs a different algorithm than the
        # override's algorithm, we don't have a sensible song-level
        # value; fall back to the spec default.
        if self._effective_algorithm() != self._song_config.algorithm:
            return spec.default
        # Algorithm default — same as the spec default in our schema.
        return spec.default

    # ----- pattern + feel override write paths ---------------------------

    def _toggle_pattern_override(
        self,
        name: str,
        enabled: bool,
        inherited: Any,
    ) -> None:
        if enabled:
            self._ensure_override().pattern[name] = inherited
        else:
            existing = self._override()
            if existing is not None and name in existing.pattern:
                del existing.pattern[name]
            self._drop_override_if_empty()
        self._on_dirty()
        self._sync_title()

    def _set_pattern_value(self, name: str, value: Any) -> None:
        override = self._ensure_override()
        override.pattern[name] = value
        self._on_dirty()

    def _toggle_feel_override(
        self,
        name: str,
        enabled: bool,
        inherited: Any,
    ) -> None:
        if enabled:
            self._ensure_override().feel[name] = inherited
        else:
            existing = self._override()
            if existing is not None and name in existing.feel:
                del existing.feel[name]
            self._drop_override_if_empty()
        self._on_dirty()
        self._sync_title()

    def _set_feel_value(self, name: str, value: Any) -> None:
        override = self._ensure_override()
        override.feel[name] = value
        self._on_dirty()

    # ----- helpers --------------------------------------------------------

    def _sync_title(self) -> None:
        override = self._override()
        is_overridden = bool(
            override
            and (
                override.algorithm
                or override.key
                or override.meter
                or override.pattern
                or override.feel
            )
        )
        suffix = "overriding" if is_overridden else "inheriting from song"
        self._title_label.setText(f"{self._voice_name.upper()}  ·  {suffix}")


def _make_pattern_toggle(panel: _VoiceOverridePanel, name: str) -> Callable[[bool, Any], None]:
    return lambda enabled, inherited: panel._toggle_pattern_override(name, enabled, inherited)


def _make_pattern_setter(panel: _VoiceOverridePanel, name: str) -> Callable[[Any], None]:
    return lambda value: panel._set_pattern_value(name, value)


def _make_feel_toggle(panel: _VoiceOverridePanel, name: str) -> Callable[[bool, Any], None]:
    return lambda enabled, inherited: panel._toggle_feel_override(name, enabled, inherited)


def _make_feel_setter(panel: _VoiceOverridePanel, name: str) -> Callable[[Any], None]:
    return lambda value: panel._set_feel_value(name, value)


class _PartListRow(QFrame):
    """One row in the parts list — name + bars + PLAY + LOOP."""

    def __init__(
        self,
        *,
        name: str,
        part: Part,
        on_play: Callable[[str], None],
        on_loop_toggle: Callable[[str, bool], None],
        on_bars_changed: Callable[[str, int], None],
    ) -> None:
        super().__init__()
        self.part_name = name
        self.setAutoFillBackground(True)

        name_lbl = QLabel(name.upper())
        name_lbl.setStyleSheet(f"color: {theme.INK.name()}; font-weight: bold; font-size: 11pt;")

        bars = QSpinBox()
        bars.setRange(1, 1024)
        bars.setValue(max(1, part.bars))
        bars.setSuffix(" bars")
        bars.setMaximumWidth(96)
        bars.valueChanged.connect(lambda v, n=name: on_bars_changed(n, v))

        play_btn = QPushButton("PLAY")
        play_btn.setMaximumWidth(72)
        play_btn.clicked.connect(lambda _checked=False, n=name: on_play(n))

        self._loop_chk = QCheckBox("LOOP")
        self._loop_chk.setChecked(part.loop)
        self._loop_chk.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK_DIM.name()}; }} "
            f"QCheckBox:checked {{ color: {theme.INK_HOT.name()}; }}"
        )
        self._loop_chk.toggled.connect(lambda v, n=name: on_loop_toggle(n, v))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        layout.addWidget(name_lbl, 1)
        layout.addWidget(bars)
        layout.addWidget(play_btn)
        layout.addWidget(self._loop_chk)

        self.set_active(False)

    def set_active(self, active: bool) -> None:
        """Toggle the 'now playing' highlight."""
        if active:
            self.setStyleSheet(
                f"QFrame {{ background-color: {theme.ACCENT_GREEN.name()}; }}"
                f"QLabel {{ color: {theme.PANEL_BG.name()}; }}"
            )
        else:
            self.setStyleSheet("")
