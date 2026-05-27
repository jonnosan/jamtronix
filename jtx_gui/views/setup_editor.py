"""Setup editor dialog with per-voice CC mapping + MIDI-Learn audition.

Opens on the currently-loaded :class:`Setup`. Each voice slot becomes
a panel listing its mappable CC functions (driven by
:mod:`jtx_gui.cc_functions`). Per row:

* CC spinner — override the default CC number for that function.
* AUDITION — open a transient port and send a quick 0 → 64 → 127 → 64
  CC sweep on the voice's channel so Ableton's MIDI Learn can latch.

Save writes the updated setup back to its on-disk path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from jtx.model import Setup, ValidationError, VoiceSlot
from jtx.persist import save_setup
from jtx_gui import theme
from jtx_gui.cc_functions import CC_FUNCTIONS, all_functions_used_by

AuditionFn = Callable[[VoiceSlot, str, int], None]
"""Callable that fires a CC audition. Args: voice, function name, cc number."""


class SetupEditor(QDialog):
    """Modal editor for one :class:`Setup`."""

    def __init__(
        self,
        *,
        setup: Setup,
        setup_path: Path | None,
        audition_fn: AuditionFn | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._setup = setup
        self._setup_path = setup_path
        self._audition_fn = audition_fn or _default_audition
        self.setWindowTitle(f"Jamtronix — Edit Setup ({setup.name})")
        self.resize(720, 620)

        header = QLabel(f"SETUP  ·  {setup.name.upper()}")
        header.setObjectName("SectionTitle")
        port_lbl = QLabel(f"DEFAULT PORT  ·  {setup.default_midi_port}")
        port_lbl.setObjectName("FieldLabel")

        # ----- voices scroll area -----
        self._voice_panels: list[_VoiceCCSection] = []
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(10)
        for slot in setup.voices:
            section = _VoiceCCSection(
                voice=slot,
                default_port=setup.default_midi_port,
                audition_fn=self._audition_fn,
            )
            self._voice_panels.append(section)
            inner_layout.addWidget(section)
        inner_layout.addStretch(1)
        scroll.setWidget(inner)

        # ----- buttons -----
        save_btn = QPushButton("SAVE")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        close_btn = QPushButton("CLOSE")
        close_btn.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        button_row.addWidget(save_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(header)
        root.addWidget(port_lbl)
        root.addWidget(scroll, 1)
        root.addLayout(button_row)

    # ----- save -----------------------------------------------------------

    def _on_save(self) -> None:
        """Write each voice's cc_map back to the model and persist."""
        for panel in self._voice_panels:
            panel.flush()
        if self._setup_path is None:
            QMessageBox.warning(
                self,
                "Save",
                "Setup wasn't loaded from disk; changes apply for this session only.",
            )
            self.accept()
            return
        try:
            save_setup(self._setup, self._setup_path)
        except (ValidationError, OSError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.accept()


# --------------------------------------------------------------------------
#                          per-voice CC section
# --------------------------------------------------------------------------


class _VoiceCCSection(QFrame):
    def __init__(
        self,
        *,
        voice: VoiceSlot,
        default_port: str,
        audition_fn: AuditionFn,
    ) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._voice = voice
        self._default_port = default_port
        self._audition_fn = audition_fn
        # function-name → CC spinner reference, populated below.
        self._spinners: dict[str, QSpinBox] = {}
        # function-name → checkbox marking the override active.
        self._overrides: dict[str, QCheckBox] = {}

        title = QLabel(
            f"{voice.name.upper()}  ·  {voice.type}  ·  ch {voice.midi_channel}",
        )
        title.setObjectName("SectionTitle")

        defaults = all_functions_used_by(*CC_FUNCTIONS.keys())
        # Filter to functions relevant for this voice's role. For now we
        # show *all* known functions per voice — most users want one CC
        # number consistent across algorithms (e.g. resonance = same CC
        # everywhere). Mappings only take effect for voices running
        # algorithms that actually emit those functions.

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)

        for function, default_cc in sorted(defaults.items()):
            row = self._make_row(function, default_cc)
            body.addLayout(row)

        if not defaults:
            note = QLabel("(no mappable CC functions yet)")
            note.setStyleSheet(f"color: {theme.INK_DIM.name()};")
            body.addWidget(note)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addLayout(body)

    def _make_row(self, function: str, default_cc: int) -> QHBoxLayout:
        current = self._voice.cc_map.get(function)
        if current is not None:
            is_override = True
            value = int(current)
        else:
            is_override = False
            value = default_cc

        override_chk = QCheckBox("OVERRIDE")
        override_chk.setChecked(is_override)
        override_chk.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK_DIM.name()}; font-size: 8pt;"
            "letter-spacing: 1.1px; }}"
            f"QCheckBox:checked {{ color: {theme.INK_HOT.name()}; }}"
        )
        self._overrides[function] = override_chk

        func_label = QLabel(function.replace("_", " ").upper())
        func_label.setMinimumWidth(160)

        default_label = QLabel(f"DEFAULT  CC {default_cc}")
        default_label.setObjectName("FieldLabel")

        spinner = QSpinBox()
        spinner.setRange(0, 127)
        spinner.setValue(value)
        spinner.setPrefix("CC ")
        spinner.setEnabled(is_override)
        self._spinners[function] = spinner

        override_chk.toggled.connect(spinner.setEnabled)

        audition_btn = QPushButton("AUDITION")
        audition_btn.setToolTip(
            "Send CC 0 → 64 → 127 → 64 on this voice's port + channel "
            "so Ableton MIDI Learn can latch it."
        )
        audition_btn.clicked.connect(
            lambda _checked=False, fn=function: self._on_audition(fn),
        )

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(override_chk)
        row.addWidget(func_label)
        row.addWidget(default_label)
        row.addWidget(spinner)
        row.addWidget(audition_btn)
        row.addStretch(1)
        return row

    # ----- write-back ------------------------------------------------------

    def flush(self) -> None:
        new_map: dict[str, int] = {}
        for function, spinner in self._spinners.items():
            if self._overrides[function].isChecked():
                new_map[function] = int(spinner.value())
        self._voice.cc_map = new_map

    # ----- audition --------------------------------------------------------

    def _on_audition(self, function: str) -> None:
        cc = int(self._spinners[function].value())
        try:
            self._audition_fn(self._voice, function, cc)
        except Exception as exc:  # noqa: BLE001 — surface verbatim
            QMessageBox.critical(
                self,
                "Audition failed",
                f"Couldn't audition CC {cc}: {exc}",
            )


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
                    channel=voice.midi_channel - 1,  # mido channels are 0..15
                    control=cc,
                    value=value,
                )
            )
            time.sleep(0.04)
    finally:
        out.close()
