"""MainWindow — sidebar nav + central stack + File menu.

Two stacked views — :class:`ComposerView` (front door, mood + format)
and :class:`PatcherView` (consolidated song / parts editor). The
SETUP button at the bottom of the sidebar is an action that opens
the :class:`SetupEditor` modal rather than a third view.
"""

from __future__ import annotations

import random
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

from jtx.composer import FORMAT_SPECS, MOOD_ANCHORS, compose, random_title
from jtx.model import ClockMode, ValidationError
from jtx.persist import load_setup
from jtx_gui import theme
from jtx_gui.bundles import bundled_setups
from jtx_gui.state import AppState
from jtx_gui.transport import TransportService
from jtx_gui.views.composer_view import ComposerView
from jtx_gui.views.patcher_view import PatcherView
from jtx_gui.views.setup_editor import SetupEditor
from jtx_gui.views.toolbar import TopToolbar

SETTINGS_ORG = "Jamtronix"
SETTINGS_APP = "Jamtronix"
SETTING_LAST_PATH = "last_song_path"
SETTING_LAST_SETUP_ID = "last_setup_id"
SETTING_LAST_CLOCK_MODE = "last_clock_mode"

_DEFAULT_SETUP_ID = "ableton"
_DEFAULT_CLOCK_MODE: ClockMode = "internal_master"
_VALID_CLOCK_MODES: frozenset[ClockMode] = frozenset(
    {"internal_master", "midi_clock_slave", "ableton_link"}
)


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

        # Build a shared transport service first so the toolbar and the
        # Live view both see the same state.
        self._transport = TransportService(parent=self)

        self._stack = QStackedWidget(self)
        self._composer_view = ComposerView(
            self._state, transport=self._transport, parent=self,
        )
        self._patcher_view = PatcherView(self._state, transport=self._transport, parent=self)
        self._stack.addWidget(self._composer_view)
        self._stack.addWidget(self._patcher_view)

        sidebar = self._build_sidebar()
        self._toolbar = TopToolbar(state=self._state, transport=self._transport, parent=self)

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._toolbar)

        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self._stack, 1)
        outer.addWidget(body, 1)
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
            f"color: {theme.INK_HOT.name()}; font-size: 22pt; font-weight: bold;"
            "letter-spacing: 5px; padding-bottom: 18px;"
        )
        layout.addWidget(brand)

        labels = ("COMPOSER", "PATCHER")
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

        # SETUP is an action, not a view, so it goes below the
        # stretch (anchored to the bottom of the sidebar) and is
        # not part of the checkable nav group.
        setup_btn = QPushButton("SETUP", sidebar)
        setup_btn.setObjectName("SidebarButton")
        setup_btn.clicked.connect(self.edit_setup)
        layout.addWidget(setup_btn)
        return sidebar

    def _switch_view(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    # ----- menu ------------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("&New…", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.show_composer)
        file_menu.addAction(new_action)

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

    def show_composer(self) -> None:
        """Switch the stacked view to the Composer and check its nav button.

        Replaces the old new-song wizard; the Composer view is the
        in-place new-song flow (epic #118 PR 4 / #123).
        """
        self._stack.setCurrentIndex(0)
        if self._nav_buttons:
            self._nav_buttons[0].setChecked(True)

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

    def bootstrap_random_song(self) -> None:
        """Auto-generate a random song using the last-used setup + clock mode.

        Replaces the old splash dialog: at launch with no song arg, the
        app lands directly on a fresh composition so the user can hit
        Play immediately. Setup + clock mode persist across launches
        via QSettings; everything else (mood, format, chaos, texture,
        motion, title) is freshly randomised every launch.
        """
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        setup_id = str(
            settings.value(SETTING_LAST_SETUP_ID, _DEFAULT_SETUP_ID, type=str)
            or _DEFAULT_SETUP_ID
        )
        clock_raw = str(
            settings.value(SETTING_LAST_CLOCK_MODE, _DEFAULT_CLOCK_MODE, type=str)
            or _DEFAULT_CLOCK_MODE
        )
        clock_mode: ClockMode = (
            clock_raw if clock_raw in _VALID_CLOCK_MODES else _DEFAULT_CLOCK_MODE
        )

        bundles = {path.stem: path for path in bundled_setups()}
        setup_path = bundles.get(setup_id) or bundles.get(_DEFAULT_SETUP_ID)
        if setup_path is None:
            # No bundled setups at all — nothing we can do but bail out
            # without crashing. The Composer view will stay empty.
            return
        setup = load_setup(setup_path)

        fmt = random.choice(list(FORMAT_SPECS.keys()))
        anchor_name = random.choice(list(MOOD_ANCHORS.keys()))
        mood = MOOD_ANCHORS[anchor_name]
        chaos = random.uniform(0.0, 1.0)
        texture = random.uniform(0.0, 1.0)
        motion = random.uniform(0.0, 1.0)
        title = random_title(mood, fmt)

        song = compose(
            title=title,
            setup_ref=setup.id,
            mood=mood,
            fmt=fmt,
            chaos=chaos,
            texture=texture,
            motion=motion,
        )
        self._state.adopt(song=song, setup=setup)
        self._toolbar.set_clock_mode(clock_mode)

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

    def edit_setup(self) -> bool:
        """Open the setup editor for the currently-loaded setup."""
        if self._state.song is None:
            QMessageBox.information(
                self,
                "Edit Setup",
                "Open a song first — the setup is loaded alongside it.",
            )
            return False
        if self._state.setup is None:
            QMessageBox.warning(
                self,
                "Edit Setup",
                self._state.setup_error or "No setup loaded for this song.",
            )
            return False
        setup_path = (
            self._state.path.parent / f"{self._state.setup.id}.jtx-setup"
            if self._state.path is not None
            else None
        )
        editor = SetupEditor(
            setup=self._state.setup,
            setup_path=setup_path,
            parent=self,
        )
        return editor.exec() == SetupEditor.DialogCode.Accepted

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
        if self._state.dirty:
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
        # Synchronously stop the worker so its sink.stop() (which fires
        # all-notes-off on every channel) runs before the QThread is
        # destroyed. Otherwise Qt aborts with "QThread: Destroyed while
        # thread is still running" and notes linger in the DAW.
        self._transport.stop_and_wait()
        event.accept()

    # ----- helpers ---------------------------------------------------------

    def _sync_title(self) -> None:
        self.setWindowTitle(self._state.display_title())
