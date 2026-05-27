"""MainWindow — sidebar nav + central stack + File menu.

The Song view is the only populated view in #17; Parts (#18) and Live
(#19) get placeholder panels so the nav already shows the three slots.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jtx.model import ValidationError
from jtx_gui import theme
from jtx_gui.state import AppState
from jtx_gui.views.parts_view import PartsView
from jtx_gui.views.song_view import SongView

SETTINGS_ORG = "Jamtronix"
SETTINGS_APP = "Jamtronix"
SETTING_LAST_PATH = "last_song_path"


class MainWindow(QMainWindow):
    """Top-level Jamtronix window."""

    def __init__(self, state: AppState | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Jamtronix")
        self.resize(1200, 820)

        self._state = state or AppState(self)
        self._state.song_changed.connect(self._sync_title)
        self._state.dirty_changed.connect(lambda _v: self._sync_title())
        self._state.path_changed.connect(lambda _p: self._sync_title())

        self._stack = QStackedWidget(self)
        self._song_view = SongView(self._state, self)
        self._parts_view = PartsView(self._state, self)
        self._live_placeholder = _Placeholder(
            "LIVE VIEW",
            "Coming in issue #19 — transport + queueable parts + knob jam surface.",
        )
        self._stack.addWidget(self._song_view)
        self._stack.addWidget(self._parts_view)
        self._stack.addWidget(self._live_placeholder)

        sidebar = self._build_sidebar()

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._build_menu()
        self._sync_title()

    # ----- sidebar ---------------------------------------------------------

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(168)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(2)

        brand = QLabel("JTX")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-size: 22pt; font-weight: 800;"
            "letter-spacing: 5px; padding-bottom: 18px;"
        )
        layout.addWidget(brand)

        labels = ("SONG", "PARTS", "LIVE")
        self._nav_buttons: list[QPushButton] = []
        for index, text in enumerate(labels):
            btn = QPushButton(text, sidebar)
            btn.setObjectName("SidebarButton")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setChecked(index == 0)
            btn.clicked.connect(lambda _ch=False, i=index: self._switch_view(i))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch(1)
        return sidebar

    def _switch_view(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    # ----- menu ------------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_song_dialog)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_song)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As…", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_song_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # ----- file actions ----------------------------------------------------

    def open_song_dialog(self) -> bool:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        raw_last = settings.value(SETTING_LAST_PATH, "", type=str)
        last = str(raw_last) if raw_last else ""
        start_dir = str(Path(last).parent) if last else str(Path.home())
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Open Jamtronix song",
            start_dir,
            "Jamtronix song (*.jtx)",
        )
        if not path:
            return False
        return self.open_song(Path(path))

    def open_song(self, path: Path) -> bool:
        try:
            self._state.open(path)
        except (ValidationError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", f"Couldn't load {path}:\n{exc}")
            return False
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(SETTING_LAST_PATH, str(path))
        return True

    def save_song(self) -> bool:
        if self._state.song is None:
            return False
        if self._state.path is None:
            return self.save_song_as()
        try:
            self._state.save()
        except (ValidationError, OSError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        return True

    def save_song_as(self) -> bool:
        if self._state.song is None:
            return False
        suggested = self._state.path or Path.home() / f"{self._state.song.title or 'song'}.jtx"
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Save Jamtronix song",
            str(suggested),
            "Jamtronix song (*.jtx)",
        )
        if not path:
            return False
        try:
            self._state.save_as(Path(path))
        except (ValidationError, OSError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue(SETTING_LAST_PATH, str(path))
        return True

    # ----- close-with-dirty prompt -----------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._state.dirty:
            event.accept()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved changes",
            "The current song has unsaved changes. Save before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return
        if reply == QMessageBox.StandardButton.Save and not self.save_song():
            event.ignore()
            return
        event.accept()

    # ----- helpers ---------------------------------------------------------

    def _sync_title(self) -> None:
        self.setWindowTitle(self._state.display_title())


class _Placeholder(QWidget):
    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-size: 24pt; font-weight: 800;letter-spacing: 6px;"
        )
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(f"color: {theme.INK_DIM.name()}; font-size: 12pt; padding-top: 16px;")
        layout.addWidget(title_lbl)
        layout.addWidget(msg)
