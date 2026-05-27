"""Top toolbar — clock mode, port override, transport, DAW launcher, render.

Lives along the top of the main window. After the Live-view consolidation,
the toolbar also owns PLAY / STOP and the bar/beat readout — the
parts list (in the Parts view) handles per-part PLAY + LOOP toggles.

Transport handling here is intentionally thin: this widget triggers
``TransportService.start`` with the *first* part in the loaded song
and subscribes to its signals for the readout. Per-part jumps come
from the Parts view via ``transport.queue_part``.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QWidget,
)

from jtx.model import ClockMode
from jtx_gui import theme
from jtx_gui.state import AppState
from jtx_gui.transport import BarTick, TransportService

_CLOCK_MODES: tuple[tuple[ClockMode, str], ...] = (
    ("internal_master", "INTERNAL MASTER"),
    ("midi_clock_slave", "MIDI CLOCK SLAVE"),
    ("ableton_link", "ABLETON LINK"),
)


class TopToolbar(QFrame):
    """Top strip — clock / port / transport / DAW / render."""

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
        self.setFixedHeight(64)
        self._state = state
        self._transport = transport
        self._port_factory = port_factory or _detect_midi_outputs
        self._port_override: str | None = None
        self._clock_mode: ClockMode = "internal_master"

        # ----- clock + port -----
        self._clock_combo = QComboBox()
        for mode, label in _CLOCK_MODES:
            self._clock_combo.addItem(label, mode)
        self._clock_combo.currentIndexChanged.connect(self._on_clock_change)

        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(220)
        self._port_combo.addItem("(use setup default)", None)
        self._refresh_ports()
        self._port_combo.currentIndexChanged.connect(self._on_port_change)
        port_refresh_btn = QPushButton("RESCAN")
        port_refresh_btn.setToolTip("Re-scan available MIDI output ports")
        port_refresh_btn.setMinimumWidth(80)
        port_refresh_btn.clicked.connect(self._refresh_ports)

        # ----- transport -----
        # Triangle-right / square glyphs — render fine in the default font
        # and keep the button tight (was a 100px PLAY/STOP rect).
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(48, 40)
        self._play_btn.setStyleSheet(self._play_button_style(playing=False))
        self._play_btn.clicked.connect(self._on_play_toggle)

        self._bar_label = QLabel("BAR — ·  BEAT —")
        self._bar_label.setStyleSheet(
            f"font-family: {theme.MONO_FONT_FAMILY}; color: {theme.INK_HOT.name()};font-size: 12pt;"
        )
        # Song-position slider — read-only progress bar of bar_index /
        # part_bars (per part). Visible feedback while jamming.
        self._position = QSlider(Qt.Orientation.Horizontal)
        self._position.setRange(0, 1)
        self._position.setValue(0)
        self._position.setEnabled(False)
        self._position.setMinimumWidth(180)
        self._position.setMaximumHeight(20)
        self._position.setToolTip("Bar position within the current part")
        self._part_label = QLabel("NOT PLAYING")
        self._part_label.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-size: 11pt; font-weight: bold;"
        )

        # ----- DAW + render -----
        self._daw_btn = QPushButton("LAUNCH DAW TEMPLATE")
        self._daw_btn.setMinimumWidth(200)
        self._daw_btn.clicked.connect(self._on_launch_daw)
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
        layout.addSpacing(10)
        layout.addWidget(port_lbl)
        layout.addWidget(self._port_combo)
        layout.addWidget(port_refresh_btn)
        layout.addSpacing(20)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._bar_label)
        layout.addWidget(self._position, 1)
        layout.addWidget(self._part_label)
        layout.addWidget(self._daw_btn)
        layout.addWidget(self._render_btn)

        # ----- transport signal wiring -----
        self._beat_timer = QTimer(self)
        self._beat_timer.setInterval(30)
        self._beat_timer.timeout.connect(self._tick_beat_visual)
        self._beat = 0
        self._beat_ms_elapsed = 0
        self._bar_index = 0
        self._part_bars = 0

        self._transport.started.connect(self._on_transport_started)
        self._transport.stopped.connect(self._on_transport_stopped)
        self._transport.bar_changed.connect(self._on_bar_changed)
        self._transport.part_changed.connect(self._on_part_changed)
        self._state.song_changed.connect(self._refresh_song_state)
        self._refresh_song_state()

    # ----- accessors used by callers when starting transport ----------

    @property
    def clock_mode(self) -> ClockMode:
        return self._clock_mode

    @property
    def port_override(self) -> str | None:
        return self._port_override

    # ----- transport actions ---------------------------------------------

    def _on_play_toggle(self) -> None:
        if self._transport.is_running:
            self._transport.stop()
            return
        song = self._state.song
        setup = self._state.setup
        if song is None or setup is None:
            QMessageBox.warning(
                self,
                "Can't play",
                self._state.setup_error or "Open a song with a sibling .jtx-setup before playing.",
            )
            return
        if not song.parts:
            QMessageBox.warning(self, "Can't play", "This song has no parts.")
            return
        first_part = next(iter(song.parts.keys()))
        self._transport.start(
            song=song,
            setup=setup,
            part_name=first_part,
            port_name=self._port_override or setup.default_midi_port,
            clock_mode=self._clock_mode,
        )

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
        if isinstance(current, str):
            idx = self._port_combo.findData(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
        self._port_combo.blockSignals(False)

    # ----- transport-state guards ----------------------------------------

    def _on_transport_started(self) -> None:
        self._clock_combo.setEnabled(False)
        self._play_btn.setText("■")  # stop glyph
        self._play_btn.setStyleSheet(self._play_button_style(playing=True))
        self._beat = 0
        self._beat_ms_elapsed = 0
        self._beat_timer.start()

    def _on_transport_stopped(self) -> None:
        self._clock_combo.setEnabled(True)
        self._play_btn.setText("▶")  # play glyph
        self._play_btn.setStyleSheet(self._play_button_style(playing=False))
        self._beat_timer.stop()
        self._bar_label.setText("BAR — ·  BEAT —")
        self._part_label.setText("NOT PLAYING")
        self._position.setRange(0, 1)
        self._position.setValue(0)

    def _on_bar_changed(self, tick: BarTick) -> None:
        self._bar_index = tick.bar_index
        self._part_bars = tick.part_bars
        self._beat = 0
        self._beat_ms_elapsed = 0
        self._update_bar_label()
        # Position slider: 0..part_bars-1, current bar index.
        if tick.part_bars > 0:
            self._position.setRange(0, max(1, tick.part_bars - 1))
            self._position.setValue(min(tick.bar_index, tick.part_bars - 1))

    def _on_part_changed(self, name: str) -> None:
        self._part_label.setText(f"NOW PLAYING  ·  {name.upper()}")

    def _refresh_song_state(self) -> None:
        setup = self._state.setup
        has_template = setup is not None and bool(setup.daw_template_path)
        self._daw_btn.setEnabled(has_template)
        if not has_template:
            self._daw_btn.setToolTip(
                "Setup has no daw_template_path; edit the setup file to set one."
            )
        else:
            assert setup is not None
            self._daw_btn.setToolTip(f"open {setup.daw_template_path}")
        if setup is not None:
            idx = self._clock_combo.findData(setup.clock_mode)
            if idx >= 0 and self._clock_combo.currentIndex() != idx:
                self._clock_combo.setCurrentIndex(idx)
                self._clock_mode = setup.clock_mode
        self._render_btn.setEnabled(self._state.song is not None)
        self._play_btn.setEnabled(self._state.song is not None and self._state.setup is not None)

    # ----- beat-readout visual tick --------------------------------------

    def _tick_beat_visual(self) -> None:
        song = self._state.song
        if song is None:
            return
        ms_per_beat = 60000.0 / max(1, song.tempo)
        self._beat_ms_elapsed += self._beat_timer.interval()
        if self._beat_ms_elapsed >= ms_per_beat:
            self._beat_ms_elapsed = 0
            self._beat = (self._beat + 1) % 4
            self._update_bar_label()

    def _update_bar_label(self) -> None:
        bar_text = (
            f"{self._bar_index + 1}/{self._part_bars}"
            if self._part_bars
            else f"{self._bar_index + 1}"
        )
        self._bar_label.setText(f"BAR {bar_text}  ·  BEAT {self._beat + 1}/4")

    # ----- DAW launcher --------------------------------------------------

    def _on_launch_daw(self) -> None:
        setup = self._state.setup
        if setup is None or not setup.daw_template_path:
            return
        path = Path(setup.daw_template_path).expanduser()
        if not path.exists():
            QMessageBox.warning(self, "DAW template", f"Template not found:\n{path}")
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
        QMessageBox.information(self, "Render complete", f"Wrote {target_str}")

    # ----- play-button styling -------------------------------------------

    @staticmethod
    def _play_button_style(playing: bool) -> str:
        bg = theme.ACCENT_RED.name() if playing else theme.ACCENT_GREEN.name()
        return (
            f"QPushButton {{ background-color: {bg};"
            f" color: {theme.PANEL_BG.name()};"
            "font-weight: bold; font-size: 18pt;"
            "border-radius: 4px; padding: 0; }"
        )


def _detect_midi_outputs() -> list[str]:
    """Return available MIDI output port names; empty on failure."""
    try:
        import mido

        names = mido.get_output_names()
        return list(names)
    except Exception:  # noqa: BLE001 — port enumeration shouldn't crash the UI
        return []
