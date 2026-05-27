"""Top toolbar — clock mode, port override, DAW launcher, render.

Lives along the top of the main window. Most controls disable while
the transport is running; clock mode changes are forwarded back to
the next :meth:`TransportService.start` call.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from jtx.model import ClockMode
from jtx_gui.state import AppState
from jtx_gui.transport import TransportService

_CLOCK_MODES: tuple[tuple[ClockMode, str], ...] = (
    ("internal_master", "INTERNAL MASTER"),
    ("midi_clock_slave", "MIDI CLOCK SLAVE"),
    ("ableton_link", "ABLETON LINK"),
)


class TopToolbar(QFrame):
    """Top strip with clock / port / DAW / render controls."""

    def __init__(
        self,
        *,
        state: AppState,
        transport: TransportService,
        port_factory: Callable[[], list[str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setFixedHeight(56)
        self._state = state
        self._transport = transport
        self._port_factory = port_factory or _detect_midi_outputs
        self._port_override: str | None = None
        self._clock_mode: ClockMode = "internal_master"

        # ----- clock mode selector -----
        self._clock_combo = QComboBox()
        for mode, label in _CLOCK_MODES:
            self._clock_combo.addItem(label, mode)
        self._clock_combo.currentIndexChanged.connect(self._on_clock_change)

        # ----- port override -----
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(220)
        self._port_combo.addItem("(use setup default)", None)
        self._refresh_ports()
        self._port_combo.currentIndexChanged.connect(self._on_port_change)
        port_refresh_btn = QPushButton("RESCAN")
        port_refresh_btn.setToolTip("Re-scan available MIDI output ports")
        port_refresh_btn.setMinimumWidth(80)
        port_refresh_btn.clicked.connect(self._refresh_ports)

        # ----- DAW launch -----
        self._daw_btn = QPushButton("LAUNCH DAW TEMPLATE")
        self._daw_btn.setMinimumWidth(200)
        self._daw_btn.clicked.connect(self._on_launch_daw)

        # ----- render -----
        self._render_btn = QPushButton("RENDER TO MIDI…")
        self._render_btn.setMinimumWidth(170)
        self._render_btn.clicked.connect(self._on_render)

        # ----- layout -----
        clock_lbl = QLabel("CLOCK")
        clock_lbl.setObjectName("FieldLabel")
        port_lbl = QLabel("PORT")
        port_lbl.setObjectName("FieldLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)
        layout.addWidget(clock_lbl)
        layout.addWidget(self._clock_combo)
        layout.addSpacing(12)
        layout.addWidget(port_lbl)
        layout.addWidget(self._port_combo)
        layout.addWidget(port_refresh_btn)
        layout.addStretch(1)
        layout.addWidget(self._daw_btn)
        layout.addWidget(self._render_btn)

        # ----- wire transport state -----
        self._transport.started.connect(self._on_transport_started)
        self._transport.stopped.connect(self._on_transport_stopped)
        self._state.song_changed.connect(self._refresh_song_state)
        self._refresh_song_state()

    # ----- accessors used by MainWindow when starting transport ----------

    @property
    def clock_mode(self) -> ClockMode:
        return self._clock_mode

    @property
    def port_override(self) -> str | None:
        return self._port_override

    # ----- selector callbacks --------------------------------------------

    def _on_clock_change(self) -> None:
        value = self._clock_combo.currentData()
        if isinstance(value, str):
            self._clock_mode = value  # type: ignore[assignment]

    def _on_port_change(self) -> None:
        value = self._port_combo.currentData()
        self._port_override = value if isinstance(value, str) else None

    def _refresh_ports(self) -> None:
        current = self._port_combo.currentData()
        ports = self._port_factory()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        self._port_combo.addItem("(use setup default)", None)
        for name in ports:
            self._port_combo.addItem(name, name)
        # restore selection if still present
        if isinstance(current, str):
            idx = self._port_combo.findData(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
        self._port_combo.blockSignals(False)

    # ----- transport-state guards ----------------------------------------

    def _on_transport_started(self) -> None:
        # Spec: clock-mode change requires a stopped transport.
        self._clock_combo.setEnabled(False)

    def _on_transport_stopped(self) -> None:
        self._clock_combo.setEnabled(True)

    def _refresh_song_state(self) -> None:
        setup = self._state.setup
        has_template = setup is not None and bool(setup.daw_template_path)
        self._daw_btn.setEnabled(has_template)
        if not has_template:
            self._daw_btn.setToolTip(
                "Setup has no daw_template_path; edit the setup file to set one."
            )
        else:
            assert setup is not None  # for mypy
            self._daw_btn.setToolTip(f"open {setup.daw_template_path}")
        # Pre-select setup's clock mode the first time a song loads.
        if setup is not None:
            idx = self._clock_combo.findData(setup.clock_mode)
            if idx >= 0 and self._clock_combo.currentIndex() != idx:
                self._clock_combo.setCurrentIndex(idx)
                self._clock_mode = setup.clock_mode
        self._render_btn.setEnabled(self._state.song is not None)

    # ----- DAW launcher --------------------------------------------------

    def _on_launch_daw(self) -> None:
        setup = self._state.setup
        if setup is None or not setup.daw_template_path:
            return
        path = Path(setup.daw_template_path).expanduser()
        if not path.exists():
            QMessageBox.warning(
                self,
                "DAW template",
                f"Template not found:\n{path}",
            )
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["start", "", str(path)], shell=True)
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            QMessageBox.critical(self, "Couldn't open DAW template", str(exc))

    # ----- render --------------------------------------------------------

    def _on_render(self) -> None:
        from jtx_gui.render import render_song_to_midi

        song = self._state.song
        setup = self._state.setup
        if song is None:
            return
        if setup is None:
            QMessageBox.warning(
                self,
                "Render to MIDI",
                self._state.setup_error or "Setup not loaded — can't render.",
            )
            return
        suggested = Path.home() / f"{song.title or 'song'}.mid"
        if self._state.path is not None:
            suggested = self._state.path.with_suffix(".mid")
        target_str, _filter = QFileDialog.getSaveFileName(
            self,
            "Render Jamtronix song to MIDI",
            str(suggested),
            "MIDI files (*.mid *.midi)",
        )
        if not target_str:
            return
        try:
            render_song_to_midi(song, setup, Path(target_str))
        except Exception as exc:  # noqa: BLE001 — surface verbatim
            QMessageBox.critical(self, "Render failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Render complete",
            f"Wrote {target_str}",
        )


def _detect_midi_outputs() -> list[str]:
    """Return available MIDI output port names; empty on failure."""
    try:
        import mido

        names = mido.get_output_names()
        return list(names)
    except Exception:  # noqa: BLE001 — port enumeration shouldn't crash the UI
        return []
