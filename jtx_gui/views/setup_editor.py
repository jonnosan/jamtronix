"""Full setup editor — header + voices + per-voice CC mapping.

Two tabs:

* **General** — name, default MIDI port, clock mode, slave port,
  DAW template path.
* **Voices** — list of voice slots with add / remove. Each row exposes
  name / type / role / channel / port override / kit_map (drums only)
  / CC mapping with AUDITION buttons.

Save writes the updated setup to the on-disk path; Save As lets the
user fork the bundled setups to a new file.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jtx.model import (
    CCTarget,
    ClockMode,
    MPEPitchBendTarget,
    MPEPressureTarget,
    MPETimbreTarget,
    ParameterTarget,
    Setup,
    ValidationError,
    VoiceSlot,
)
from jtx.model.types import ROLES_BY_TYPE
from jtx.persist import save_setup
from jtx_gui import theme
from jtx_gui.cc_functions import DEFAULT_TARGETS, functions_for_type

AuditionFn = Callable[[VoiceSlot, str, int], None]
"""Callable that fires a CC audition. Args: voice, function name, cc number."""

MPEAuditionFn = Callable[[VoiceSlot, str, str], None]
"""Callable that fires an MPE-target audition.

Args: voice, function name, kind (one of ``"mpe_pitch_bend"``,
``"mpe_pressure"``, ``"mpe_timbre"``). Sends a NoteOn + ramp + NoteOff
on the voice's first MPE channel so an MPE-aware instrument latches.
"""

NoteAuditionFn = Callable[[VoiceSlot, list[int]], None]
"""Callable that fires a brief MIDI note (or chord) audition on the voice."""

# UI-visible kind keys for the parameter target combo.
_KIND_LABELS: tuple[tuple[str, str], ...] = (
    ("cc", "CC"),
    ("mpe_pitch_bend", "MPE pitch bend"),
    ("mpe_pressure", "MPE pressure"),
    ("mpe_timbre", "MPE timbre (CC 74)"),
)


def _target_kind(target: ParameterTarget) -> str:
    if isinstance(target, CCTarget):
        return "cc"
    if isinstance(target, MPEPitchBendTarget):
        return "mpe_pitch_bend"
    if isinstance(target, MPEPressureTarget):
        return "mpe_pressure"
    if isinstance(target, MPETimbreTarget):
        return "mpe_timbre"
    return "cc"  # pragma: no cover


def _target_from_kind(kind: str, cc: int) -> ParameterTarget:
    if kind == "cc":
        return CCTarget(int(cc))
    if kind == "mpe_pitch_bend":
        return MPEPitchBendTarget()
    if kind == "mpe_pressure":
        return MPEPressureTarget()
    if kind == "mpe_timbre":
        return MPETimbreTarget()
    raise ValueError(f"unknown parameter target kind: {kind!r}")


_VOICE_TYPES: tuple[str, ...] = ("drum", "mono", "poly", "modulator", "follower")

# Note pitches used for the per-voice audition buttons by role. Drum
# pitches come from each kit_map row, so they're not in this table.
_AUDITION_PITCHES: dict[str, list[int]] = {
    "bass": [45],  # A2
    "lead": [69],  # A4
    "pad": [60, 64, 67],  # C major triad at C4
    "stab": [69, 72, 76],  # A minor triad at A4
    "chord": [69, 72, 76],  # A minor triad at A4
    "modulator": [],  # use the CC audition instead
    "follower": [],  # follower has no own pitch
}
_CLOCK_LABELS: tuple[tuple[ClockMode, str], ...] = (
    ("internal_master", "Internal master"),
    ("midi_clock_slave", "MIDI clock slave"),
    ("ableton_link", "Ableton Link"),
)


class SetupEditor(QDialog):
    """Modal editor for one :class:`Setup`."""

    def __init__(
        self,
        *,
        setup: Setup,
        setup_path: Path | None,
        audition_fn: AuditionFn | None = None,
        note_audition_fn: NoteAuditionFn | None = None,
        mpe_audition_fn: MPEAuditionFn | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Have Qt destroy the dialog (and its whole widget tree) as soon
        # as it closes. Otherwise PySide6's Python wrappers linger until
        # GC, and the next ev-loop pending-calls flush can re-fire C++
        # destructors on already-freed children — segfaults during
        # playback when the beat timer keeps the loop hot.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._setup = setup
        self._setup_path = setup_path
        self._audition_fn = audition_fn or _default_audition
        self._note_audition_fn = note_audition_fn or _default_note_audition
        self._mpe_audition_fn = mpe_audition_fn or _default_mpe_audition
        self.setWindowTitle(f"Jamtronix — Edit Setup ({setup.name})")
        self.resize(900, 660)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_voices_tab(), "Voices")

        save_btn = QPushButton("SAVE")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        save_as_btn = QPushButton("SAVE AS…")
        save_as_btn.clicked.connect(self._on_save_as)
        close_btn = QPushButton("CLOSE")
        close_btn.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        button_row.addWidget(save_as_btn)
        button_row.addWidget(save_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        root.addWidget(tabs, 1)
        root.addLayout(button_row)

    # ----- General tab ----------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(20, 16, 20, 16)
        form.setVerticalSpacing(10)

        self._name_edit = QLineEdit(self._setup.name)
        self._name_edit.editingFinished.connect(self._on_name_changed)

        self._port_edit = QLineEdit(self._setup.default_midi_port)
        self._port_edit.editingFinished.connect(self._on_port_changed)

        self._clock_combo = QComboBox()
        for value, label in _CLOCK_LABELS:
            self._clock_combo.addItem(label, value)
        for index, (value, _label) in enumerate(_CLOCK_LABELS):
            if value == self._setup.clock_mode:
                self._clock_combo.setCurrentIndex(index)
                break
        self._clock_combo.currentIndexChanged.connect(self._on_clock_changed)

        self._slave_port_edit = QLineEdit(self._setup.midi_clock_in_port or "")
        self._slave_port_edit.setPlaceholderText("(only used for MIDI clock slave)")
        self._slave_port_edit.editingFinished.connect(self._on_slave_port_changed)

        self._template_edit = QLineEdit(self._setup.daw_template_path or "")
        self._template_edit.setPlaceholderText("Path to .als (or any DAW project)")
        self._template_edit.editingFinished.connect(self._on_template_changed)
        browse_btn = QPushButton("BROWSE…")
        browse_btn.setMaximumWidth(110)
        browse_btn.clicked.connect(self._on_browse_template)
        template_row = QHBoxLayout()
        template_row.setContentsMargins(0, 0, 0, 0)
        template_row.addWidget(self._template_edit, 1)
        template_row.addWidget(browse_btn)
        template_wrap = QWidget()
        template_wrap.setLayout(template_row)

        form.addRow("Setup name", self._name_edit)
        form.addRow("Default MIDI port", self._port_edit)
        form.addRow("Clock mode", self._clock_combo)
        form.addRow("MIDI clock-in port", self._slave_port_edit)
        form.addRow("DAW template path", template_wrap)
        form.addRow(
            QLabel(""),
            QLabel(self._setup_path_summary()),
        )
        return page

    def _setup_path_summary(self) -> str:
        if self._setup_path is None:
            return "(no on-disk path — Save As to write the setup)"
        return f"on disk: {self._setup_path}"

    def _on_name_changed(self) -> None:
        self._setup.name = self._name_edit.text().strip() or self._setup.name

    def _on_port_changed(self) -> None:
        text = self._port_edit.text().strip()
        if text:
            self._setup.default_midi_port = text

    def _on_clock_changed(self, _index: int) -> None:
        value = self._clock_combo.currentData()
        if isinstance(value, str):
            self._setup.clock_mode = value  # type: ignore[assignment]

    def _on_slave_port_changed(self) -> None:
        text = self._slave_port_edit.text().strip()
        self._setup.midi_clock_in_port = text or None

    def _on_template_changed(self) -> None:
        text = self._template_edit.text().strip()
        self._setup.daw_template_path = text or None

    def _on_browse_template(self) -> None:
        start = Path(self._setup.daw_template_path or "").expanduser().parent
        if not start.exists():
            start = Path.home()
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Pick a DAW template",
            str(start),
            "DAW projects (*.als *.logicx *.flp *.cpr);;All files (*)",
        )
        if not path:
            return
        self._template_edit.setText(path)
        self._setup.daw_template_path = path

    # ----- Voices tab -----------------------------------------------------

    def _build_voices_tab(self) -> QWidget:
        # Parent passed at construction so PySide6 hands lifetime to Qt
        # immediately. Without it, the Python wrapper retains C++ ownership
        # and a later GC pass can re-fire the C++ destructor → segfault.
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: voice list + add/remove/rename buttons.
        left = QWidget()
        left_col = QVBoxLayout(left)
        left_col.setContentsMargins(6, 6, 6, 6)
        left_col.setSpacing(6)
        self._voice_list = QListWidget()
        self._voice_list.itemSelectionChanged.connect(self._on_voice_selected)
        add_btn = QPushButton("ADD")
        rename_btn = QPushButton("RENAME")
        remove_btn = QPushButton("REMOVE")
        add_btn.clicked.connect(self._on_add_voice)
        rename_btn.clicked.connect(self._on_rename_voice)
        remove_btn.clicked.connect(self._on_remove_voice)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rename_btn)
        btn_row.addWidget(remove_btn)
        left_col.addWidget(self._voice_list, 1)
        left_col.addLayout(btn_row)

        # Right: scrollable detail pane for the selected voice.
        right = QScrollArea()
        right.setWidgetResizable(True)
        self._voice_detail_holder = QWidget()
        self._voice_detail_layout = QVBoxLayout(self._voice_detail_holder)
        self._voice_detail_layout.setContentsMargins(12, 12, 12, 12)
        self._voice_detail_layout.setSpacing(10)
        self._voice_detail_layout.addStretch(1)
        right.setWidget(self._voice_detail_holder)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 600])

        wrapper = QWidget()
        wrap_layout = QVBoxLayout(wrapper)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.addWidget(splitter)

        self._refresh_voice_list()
        return wrapper

    def _refresh_voice_list(self) -> None:
        selected = self._voice_list.currentRow()
        self._voice_list.blockSignals(True)
        self._voice_list.clear()
        for slot in self._setup.voices:
            label = f"{slot.name}  ·  {slot.type}  ·  ch {slot.midi_channel}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, slot.name)
            self._voice_list.addItem(item)
        self._voice_list.blockSignals(False)
        if self._setup.voices:
            row = selected if 0 <= selected < len(self._setup.voices) else 0
            self._voice_list.setCurrentRow(row)
            self._show_voice_detail(self._setup.voices[row])
        else:
            self._clear_voice_detail()

    def _on_voice_selected(self) -> None:
        row = self._voice_list.currentRow()
        if 0 <= row < len(self._setup.voices):
            self._show_voice_detail(self._setup.voices[row])
        else:
            self._clear_voice_detail()

    def _clear_voice_detail(self) -> None:
        while self._voice_detail_layout.count():
            item = self._voice_detail_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._voice_detail_layout.addStretch(1)

    def _show_voice_detail(self, slot: VoiceSlot) -> None:
        self._clear_voice_detail()
        editor = _VoiceSlotEditor(
            slot=slot,
            audition_fn=self._audition_fn,
            note_audition_fn=self._note_audition_fn,
            mpe_audition_fn=self._mpe_audition_fn,
            on_changed=self._refresh_voice_list,
        )
        # Insert above the trailing stretch (which is index 0 because we
        # just cleared everything and re-added one stretch).
        self._voice_detail_layout.insertWidget(0, editor)

    def _on_add_voice(self) -> None:
        existing = {v.name for v in self._setup.voices}
        base = "voice"
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        new_name = f"{base}{i}"
        self._setup.voices.append(
            VoiceSlot(
                name=new_name,
                type="mono",
                default_role="bass",
                midi_channel=1,
            )
        )
        self._refresh_voice_list()
        # Select the new entry.
        self._voice_list.setCurrentRow(len(self._setup.voices) - 1)

    def _on_rename_voice(self) -> None:
        row = self._voice_list.currentRow()
        if not (0 <= row < len(self._setup.voices)):
            return
        slot = self._setup.voices[row]
        new_name, ok = QInputDialog.getText(self, "Rename voice", "New name:", text=slot.name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == slot.name:
            return
        if any(v.name == new_name for v in self._setup.voices):
            QMessageBox.warning(self, "Rename", f"Voice {new_name!r} already exists.")
            return
        QMessageBox.information(
            self,
            "Heads up",
            (
                "Songs reference voices by name. Renaming this slot won't update "
                "any songs that already exist — those songs will lose this voice "
                "until you rename it back or edit the song."
            ),
        )
        slot.name = new_name
        self._refresh_voice_list()

    def _on_remove_voice(self) -> None:
        row = self._voice_list.currentRow()
        if not (0 <= row < len(self._setup.voices)):
            return
        slot = self._setup.voices[row]
        if (
            QMessageBox.question(
                self,
                "Remove voice",
                f"Remove voice {slot.name!r}? Songs that reference it will lose it.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        del self._setup.voices[row]
        self._refresh_voice_list()

    # ----- save / save as -------------------------------------------------

    def _on_save(self) -> None:
        if self._setup_path is None:
            self._on_save_as()
            return
        try:
            save_setup(self._setup, self._setup_path)
        except (ValidationError, OSError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.accept()

    def _on_save_as(self) -> None:
        suggested = self._setup_path or (Path.home() / f"{self._setup.id}.jtx-setup")
        path_str, _filter = QFileDialog.getSaveFileName(
            self,
            "Save setup as",
            str(suggested),
            "Setup files (*.jtx-setup)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            save_setup(self._setup, path)
        except (ValidationError, OSError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._setup_path = path
        self.accept()


# --------------------------------------------------------------------------
#                          per-voice slot editor
# --------------------------------------------------------------------------


class _VoiceSlotEditor(QFrame):
    """Detail editor for one voice slot.

    Surfaces every editable field on ``VoiceSlot``: type, role,
    channel, port override, drum kit map (when type == drum), and the
    CC-mapping table with audition buttons.
    """

    def __init__(
        self,
        *,
        slot: VoiceSlot,
        audition_fn: AuditionFn,
        note_audition_fn: NoteAuditionFn,
        mpe_audition_fn: MPEAuditionFn,
        on_changed: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._slot = slot
        self._audition_fn = audition_fn
        self._note_audition_fn = note_audition_fn
        self._mpe_audition_fn = mpe_audition_fn
        self._on_changed = on_changed

        title = QLabel(f"VOICE  ·  {slot.name.upper()}")
        title.setObjectName("SectionTitle")

        form = QFormLayout()
        form.setVerticalSpacing(6)

        # Type combo (drives role + kit_map visibility).
        self._type_combo = QComboBox()
        self._type_combo.addItems(_VOICE_TYPES)
        self._type_combo.setCurrentText(slot.type)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)

        # Role combo, populated from ROLES_BY_TYPE based on current type.
        self._role_combo = QComboBox()
        self._refresh_role_combo()
        self._role_combo.currentTextChanged.connect(self._on_role_changed)

        # Channel.
        self._channel_spin = QSpinBox()
        self._channel_spin.setRange(1, 16)
        self._channel_spin.setValue(slot.midi_channel)
        self._channel_spin.valueChanged.connect(self._on_channel_changed)

        # Port override.
        self._port_edit = QLineEdit(slot.midi_port or "")
        self._port_edit.setPlaceholderText("(use setup default)")
        self._port_edit.editingFinished.connect(self._on_port_changed)

        # MPE mode toggle + channel-count spinner.
        self._mpe_mode_chk = QCheckBox("MPE mode")
        self._mpe_mode_chk.setChecked(slot.mpe_mode)
        self._mpe_mode_chk.setToolTip(
            "When on, the voice spans a block of MIDI channels starting at "
            "the voice's MIDI channel; NoteOns round-robin through the block "
            "so per-note pitch bend lands on the right note."
        )
        self._mpe_mode_chk.toggled.connect(self._on_mpe_mode_changed)
        self._mpe_count_spin = QSpinBox()
        self._mpe_count_spin.setRange(1, 16)
        self._mpe_count_spin.setValue(slot.mpe_channel_count)
        self._mpe_count_spin.setEnabled(slot.mpe_mode)
        self._mpe_count_spin.valueChanged.connect(self._on_mpe_count_changed)
        mpe_row = QHBoxLayout()
        mpe_row.setContentsMargins(0, 0, 0, 0)
        mpe_row.setSpacing(8)
        mpe_row.addWidget(self._mpe_mode_chk)
        mpe_row.addWidget(QLabel("MPE channels"))
        mpe_row.addWidget(self._mpe_count_spin)
        mpe_row.addStretch(1)
        mpe_wrap = QWidget()
        mpe_wrap.setLayout(mpe_row)

        form.addRow("Type", self._type_combo)
        form.addRow("Role", self._role_combo)
        form.addRow("MIDI channel", self._channel_spin)
        form.addRow("Port override", self._port_edit)
        form.addRow("MPE", mpe_wrap)

        # Voice-level note audition (mono / poly). Drum voices use the
        # per-row buttons in the kit map instead.
        self._note_audition_btn = QPushButton("PLAY NOTE")
        self._note_audition_btn.setMaximumWidth(160)
        self._note_audition_btn.setToolTip(
            "Send a brief note (or chord) consistent with this voice's "
            "role so you can MIDI-Learn the synth or just check it's wired."
        )
        self._note_audition_btn.clicked.connect(self._on_note_audition)
        self._note_audition_btn.setVisible(slot.type in {"mono", "poly"})

        # Kit-map editor — only visible for drum voices.
        self._kit_panel = _KitMapEditor(slot=slot, note_audition_fn=note_audition_fn)
        self._kit_panel.setVisible(slot.type == "drum")

        # Parameter-map section — function rows from FUNCTIONS_BY_VOICE_TYPE.
        self._param_section = _ParameterMapSection(
            slot=slot,
            audition_fn=audition_fn,
            mpe_audition_fn=mpe_audition_fn,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self._note_audition_btn, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._kit_panel)
        layout.addWidget(self._param_section)

    def _on_note_audition(self) -> None:
        notes = _AUDITION_PITCHES.get(self._slot.default_role, [60])
        if not notes:
            return
        try:
            self._note_audition_fn(self._slot, list(notes))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Audition failed",
                f"Couldn't play audition notes: {exc}",
            )

    # ----- top-level field callbacks --------------------------------------

    def _on_type_changed(self, new_type: str) -> None:
        if new_type == self._slot.type:
            return
        self._slot.type = new_type  # type: ignore[assignment]
        self._refresh_role_combo()
        # Pick a valid default role for the new type. ROLES_BY_TYPE
        # keys are Literal VoiceTypes; the combobox hands us a plain
        # str so we look up via a wider variable.
        from typing import cast

        roles_map: dict[str, tuple[str, ...]] = cast("dict[str, tuple[str, ...]]", ROLES_BY_TYPE)
        roles = roles_map.get(new_type, ())
        if roles and self._slot.default_role not in roles:
            self._slot.default_role = roles[0]  # type: ignore[assignment]
            self._role_combo.setCurrentText(roles[0])
        self._kit_panel.setVisible(new_type == "drum")
        self._note_audition_btn.setVisible(new_type in {"mono", "poly"})
        self._param_section.refresh_rows()
        self._on_changed()

    def _on_mpe_mode_changed(self, checked: bool) -> None:
        self._slot.mpe_mode = bool(checked)
        self._mpe_count_spin.setEnabled(checked)
        self._on_changed()

    def _on_mpe_count_changed(self, value: int) -> None:
        self._slot.mpe_channel_count = int(value)
        self._on_changed()

    def _refresh_role_combo(self) -> None:
        roles = ROLES_BY_TYPE.get(self._slot.type, ())
        self._role_combo.blockSignals(True)
        self._role_combo.clear()
        self._role_combo.addItems(list(roles))
        if self._slot.default_role in roles:
            self._role_combo.setCurrentText(self._slot.default_role)
        elif roles:
            self._role_combo.setCurrentText(roles[0])
        self._role_combo.blockSignals(False)

    def _on_role_changed(self, role: str) -> None:
        if role:
            self._slot.default_role = role  # type: ignore[assignment]

    def _on_channel_changed(self, value: int) -> None:
        self._slot.midi_channel = value
        self._on_changed()

    def _on_port_changed(self) -> None:
        text = self._port_edit.text().strip()
        self._slot.midi_port = text or None


# --------------------------------------------------------------------------
#                          kit-map editor (drum voices only)
# --------------------------------------------------------------------------


class _KitMapEditor(QFrame):
    """Free-form ``piece_name → MIDI note`` editor for drum voices."""

    def __init__(self, *, slot: VoiceSlot, note_audition_fn: NoteAuditionFn) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._slot = slot
        self._note_audition_fn = note_audition_fn
        # Track per-row (line_edit, spinner) so we never have to call
        # findChildren — that introduced Qt cleanup ordering issues.
        self._rows: list[tuple[QLineEdit, QSpinBox]] = []

        title = QLabel("KIT MAP")
        title.setObjectName("FieldLabel")

        self._rows_holder = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_holder)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)

        for piece, note in slot.kit_map.items():
            self._add_row(piece, int(note))

        if not slot.kit_map:
            self._add_row(slot.name, 36)

        add_btn = QPushButton("ADD PIECE")
        add_btn.clicked.connect(self._on_add)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addWidget(self._rows_holder)
        layout.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignLeft)

    def _add_row(self, piece: str, note: int) -> None:
        piece_edit = QLineEdit(piece)
        piece_edit.setMaximumWidth(180)
        note_spin = QSpinBox()
        note_spin.setRange(0, 127)
        note_spin.setValue(int(note))
        audition_btn = QPushButton("PLAY")
        audition_btn.setMaximumWidth(64)
        audition_btn.setToolTip("Send this drum's MIDI note on the voice's channel")
        remove_btn = QPushButton("×")
        remove_btn.setMaximumWidth(32)

        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(piece_edit)
        row.addWidget(note_spin)
        row.addWidget(audition_btn)
        row.addWidget(remove_btn)

        entry = (piece_edit, note_spin)
        self._rows.append(entry)

        piece_edit.editingFinished.connect(self._rebuild_map)
        note_spin.valueChanged.connect(lambda _v: self._rebuild_map())

        def on_audition() -> None:
            try:
                self._note_audition_fn(self._slot, [int(note_spin.value())])
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(
                    self,
                    "Audition failed",
                    f"Couldn't audition note: {exc}",
                )

        audition_btn.clicked.connect(on_audition)

        def on_remove() -> None:
            if entry in self._rows:
                self._rows.remove(entry)
            row_widget.setVisible(False)
            self._rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()
            self._rebuild_map()

        remove_btn.clicked.connect(on_remove)
        self._rows_layout.addWidget(row_widget)

    def _on_add(self) -> None:
        self._add_row("piece", 36)
        self._rebuild_map()

    def _rebuild_map(self) -> None:
        kit_map: dict[str, int] = {}
        for piece_edit, note_spin in self._rows:
            piece = piece_edit.text().strip()
            if not piece:
                continue
            kit_map[piece] = int(note_spin.value())
        self._slot.kit_map = kit_map


# --------------------------------------------------------------------------
#                       parameter-mapping section
# --------------------------------------------------------------------------


class _ParameterMapSection(QFrame):
    """Function → :class:`ParameterTarget` table with per-row override.

    For each function in the v1 vocabulary appropriate to the voice
    type, surfaces:

    * a kind combo (``CC`` / ``MPE pitch bend`` / ``MPE pressure`` /
      ``MPE timbre``) — picks the target type;
    * a CC# spinner (visible only when kind == CC);
    * an OVERRIDE checkbox toggling whether the row writes to
      ``slot.parameter_map`` (otherwise the slot inherits the
      algorithm's ``DEFAULT_PARAM_MAP``);
    * an AUDITION button that fires the right kind of MIDI for the
      selected target type.

    Functions present in the voice's ``parameter_map`` but absent from
    the v1 vocab (``detune``, ``glide_on``) render as read-only
    "custom" rows so users can see them without surprise.
    """

    def __init__(
        self,
        *,
        slot: VoiceSlot,
        audition_fn: AuditionFn,
        mpe_audition_fn: MPEAuditionFn,
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._slot = slot
        self._audition_fn = audition_fn
        self._mpe_audition_fn = mpe_audition_fn

        self._kind_combos: dict[str, QComboBox] = {}
        self._cc_spinners: dict[str, QSpinBox] = {}
        self._overrides: dict[str, QCheckBox] = {}

        self._title = QLabel("PARAMETER MAP")
        self._title.setObjectName("FieldLabel")
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self._title)
        layout.addLayout(self._body)

        self.refresh_rows()

    def refresh_rows(self) -> None:
        """Rebuild the row list. Called when the voice type changes."""
        # Clear existing rows.
        while self._body.count():
            item = self._body.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                child_layout = item.layout()
                if child_layout is not None:
                    _drain_layout(child_layout)
        self._kind_combos.clear()
        self._cc_spinners.clear()
        self._overrides.clear()

        functions = functions_for_type(self._slot.type)
        # Show v1 vocab rows first, then any extra ("custom") functions
        # present in the parameter_map but not in the vocab.
        extras = tuple(fn for fn in self._slot.parameter_map if fn not in functions)

        if not functions and not extras:
            note = QLabel("(no mappable parameters for this voice type)")
            note.setStyleSheet(f"color: {theme.INK_DIM.name()};")
            self._body.addWidget(note)
            return

        for function in functions:
            self._body.addLayout(self._make_param_row(function))
        for function in extras:
            self._body.addLayout(self._make_custom_row(function))

    def _make_param_row(self, function: str) -> QHBoxLayout:
        override_target = self._slot.parameter_map.get(function)
        default_target = DEFAULT_TARGETS.get(function, CCTarget(0))
        is_override = override_target is not None
        target = override_target if override_target is not None else default_target

        override_chk = QCheckBox("OVERRIDE")
        override_chk.setChecked(is_override)
        override_chk.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK_DIM.name()}; }} "
            f"QCheckBox:checked {{ color: {theme.INK_HOT.name()}; }}"
        )
        self._overrides[function] = override_chk

        func_label = QLabel(function.replace("_", " ").upper())
        func_label.setMinimumWidth(120)

        kind_combo = QComboBox()
        for kind, label in _KIND_LABELS:
            kind_combo.addItem(label, kind)
        current_kind = _target_kind(target)
        for index in range(kind_combo.count()):
            if kind_combo.itemData(index) == current_kind:
                kind_combo.setCurrentIndex(index)
                break
        kind_combo.setEnabled(is_override)
        self._kind_combos[function] = kind_combo

        cc_spinner = QSpinBox()
        cc_spinner.setRange(0, 127)
        cc_spinner.setPrefix("CC ")
        cc_value = target.cc if isinstance(target, CCTarget) else _default_cc_for(function)
        cc_spinner.setValue(int(cc_value))
        cc_spinner.setEnabled(is_override and current_kind == "cc")
        cc_spinner.setVisible(current_kind == "cc")
        self._cc_spinners[function] = cc_spinner

        audition_btn = QPushButton("AUDITION")
        audition_btn.setToolTip(
            "Send a probe sequence appropriate for the target kind so the "
            "receiving instrument latches (CC sweep for CC; NoteOn + ramp + "
            "NoteOff for MPE kinds)."
        )

        def on_override(checked: bool, fn: str = function) -> None:
            self._kind_combos[fn].setEnabled(checked)
            kind = self._current_kind(fn)
            self._cc_spinners[fn].setEnabled(checked and kind == "cc")
            self._sync_param(fn)

        def on_kind_changed(_idx: int, fn: str = function) -> None:
            kind = self._current_kind(fn)
            self._cc_spinners[fn].setVisible(kind == "cc")
            self._cc_spinners[fn].setEnabled(self._overrides[fn].isChecked() and kind == "cc")
            self._sync_param(fn)

        def on_cc_changed(_v: int, fn: str = function) -> None:
            self._sync_param(fn)

        override_chk.toggled.connect(on_override)
        kind_combo.currentIndexChanged.connect(on_kind_changed)
        cc_spinner.valueChanged.connect(on_cc_changed)
        audition_btn.clicked.connect(
            lambda _checked=False, fn=function: self._on_audition_param(fn),
        )

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(override_chk)
        row.addWidget(func_label)
        row.addWidget(kind_combo)
        row.addWidget(cc_spinner)
        row.addWidget(audition_btn)
        row.addStretch(1)
        return row

    def _make_custom_row(self, function: str) -> QHBoxLayout:
        target = self._slot.parameter_map[function]
        kind = _target_kind(target)
        label = next((lbl for k, lbl in _KIND_LABELS if k == kind), kind)
        row = QHBoxLayout()
        row.setSpacing(8)
        marker = QLabel("CUSTOM")
        marker.setStyleSheet(f"color: {theme.INK_DIM.name()};")
        func_label = QLabel(function.replace("_", " ").upper())
        func_label.setMinimumWidth(120)
        info = QLabel(label)
        if isinstance(target, CCTarget):
            info = QLabel(f"{label}  ·  CC {target.cc}")
        row.addWidget(marker)
        row.addWidget(func_label)
        row.addWidget(info)
        row.addStretch(1)
        return row

    def _current_kind(self, function: str) -> str:
        combo = self._kind_combos[function]
        data = combo.currentData()
        return str(data) if data is not None else "cc"

    def _sync_param(self, function: str) -> None:
        if not self._overrides[function].isChecked():
            self._slot.parameter_map.pop(function, None)
            return
        kind = self._current_kind(function)
        cc = int(self._cc_spinners[function].value())
        self._slot.parameter_map[function] = _target_from_kind(kind, cc)

    def _on_audition_param(self, function: str) -> None:
        kind = self._current_kind(function)
        try:
            if kind == "cc":
                cc = int(self._cc_spinners[function].value())
                self._audition_fn(self._slot, function, cc)
            else:
                self._mpe_audition_fn(self._slot, function, kind)
        except Exception as exc:  # noqa: BLE001 — surface verbatim
            QMessageBox.critical(
                self,
                "Audition failed",
                f"Couldn't audition {function!r}: {exc}",
            )


def _default_cc_for(function: str) -> int:
    target = DEFAULT_TARGETS.get(function)
    return target.cc if isinstance(target, CCTarget) else 0


def _drain_layout(layout: object) -> None:
    """Recursively delete all children of a layout."""
    from PySide6.QtWidgets import QLayout

    if not isinstance(layout, QLayout):  # pragma: no cover — defensive
        return
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                _drain_layout(child)


# --------------------------------------------------------------------------
#                          default audition impl
# --------------------------------------------------------------------------


def _default_audition(voice: VoiceSlot, _function: str, cc: int) -> None:
    """Send 0 → 64 → 127 → 64 on the voice's port + channel."""
    import time

    import mido

    port_name = voice.midi_port
    out = mido.open_output(port_name) if port_name else mido.open_output()
    try:
        for value in (0, 64, 127, 64):
            out.send(
                mido.Message(
                    "control_change",
                    channel=voice.midi_channel - 1,
                    control=cc,
                    value=value,
                )
            )
            time.sleep(0.04)
    finally:
        out.close()


def _default_note_audition(voice: VoiceSlot, notes: list[int]) -> None:
    """Send a short NoteOn cluster + matching NoteOff on the voice."""
    import time

    import mido

    if not notes:
        return
    port_name = voice.midi_port
    out = mido.open_output(port_name) if port_name else mido.open_output()
    try:
        channel = voice.midi_channel - 1  # mido channels are 0..15
        for note in notes:
            note = max(0, min(127, int(note)))
            out.send(mido.Message("note_on", channel=channel, note=note, velocity=100))
        time.sleep(0.35)
        for note in notes:
            note = max(0, min(127, int(note)))
            out.send(mido.Message("note_off", channel=channel, note=note, velocity=0))
    finally:
        out.close()


def _default_mpe_audition(voice: VoiceSlot, _function: str, kind: str) -> None:
    """Probe an MPE target so the receiving instrument latches.

    Sends NoteOn + a 4-step ramp of the appropriate expression message
    + NoteOff on the voice's first MPE channel. The receiving track
    (set to MPE in) will pick up on the per-note expression and learn
    the mapping.
    """
    import time

    import mido

    if not voice.mpe_mode:
        # Caller wired this up for an MPE kind on a non-MPE voice;
        # fall through to the voice's main channel.
        channel = voice.midi_channel - 1
    else:
        channel = voice.midi_channel - 1  # first channel of the MPE block
    port_name = voice.midi_port
    out = mido.open_output(port_name) if port_name else mido.open_output()
    audition_note = 69  # A4 — neutral mid-register probe
    try:
        out.send(mido.Message("note_on", channel=channel, note=audition_note, velocity=100))
        if kind == "mpe_pitch_bend":
            for pb in (-4096, 0, 4096, 0):
                out.send(mido.Message("pitchwheel", channel=channel, pitch=pb))
                time.sleep(0.06)
        elif kind == "mpe_pressure":
            for value in (0, 64, 127, 64):
                out.send(mido.Message("aftertouch", channel=channel, value=value))
                time.sleep(0.06)
        elif kind == "mpe_timbre":
            for value in (0, 64, 127, 64):
                out.send(
                    mido.Message(
                        "control_change",
                        channel=channel,
                        control=74,
                        value=value,
                    )
                )
                time.sleep(0.06)
        time.sleep(0.08)
        out.send(mido.Message("note_off", channel=channel, note=audition_note, velocity=0))
    finally:
        out.close()
