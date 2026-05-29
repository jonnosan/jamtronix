"""Single-page new-song dialog.

Title + style + bundled setup picker. On Finish the dialog hands the
caller a (Song, Setup) pair in memory — no save dialog at this point,
so the user can audition the new song before deciding where to write
it. ``MainWindow`` adopts the result via :meth:`AppState.adopt`.

Transient state: with the style templates removed (PR 2 of the mood +
format composer rework), the only style left is ``blank``. The full
Composer view replaces this wizard in PR 4.
"""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jtx.model import Setup, Song
from jtx.persist import load_setup
from jtx_gui import theme
from jtx_gui.bundles import bundled_setups
from templates import STYLES
from templates import build as build_song

_TITLE_FIRST = (
    "Phuture",
    "Acid",
    "Sub",
    "Deep",
    "Strobe",
    "Neon",
    "Helix",
    "Vapor",
    "Voltage",
    "Lunar",
    "Solar",
    "Astral",
    "Magnet",
    "Cipher",
    "Mirage",
    "Pulse",
)
_TITLE_SECOND = (
    "Lines",
    "Drift",
    "Field",
    "Engine",
    "Storm",
    "Tower",
    "Mirror",
    "Loop",
    "Rapture",
    "Tide",
    "Bloom",
    "Maze",
    "Cycle",
    "Static",
    "Bloom",
    "Garden",
)


def random_title() -> str:
    """Pick a fresh two-word jam-tool title."""
    return f"{random.choice(_TITLE_FIRST)} {random.choice(_TITLE_SECOND)}"


def random_non_blank_style() -> str:
    """Pick a random style excluding 'blank' where possible.

    With the style templates removed (PR 2 of the mood + format composer
    rework), the only style left is ``blank`` — so this falls through
    to that. Preserved as a no-op shim until PR 4 deletes the wizard.
    """
    non_blank = [s for s in STYLES.keys() if s != "blank"]
    if non_blank:
        return random.choice(non_blank)
    return next(iter(STYLES.keys()))


class NewSongWizard(QDialog):
    """Modal dialog that returns a (Song, Setup) pair on accept."""

    _STYLE_BLURBS = {
        "blank": "Empty song — no voices, one intro part. Compose from scratch.",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Jamtronix — New Song")
        self.setMinimumWidth(540)
        self._result: tuple[Song, Setup] | None = None
        self._custom_setup_path: Path | None = None
        self._setup_paths: dict[str, Path] = {}

        title_label = QLabel("NEW SONG")
        title_label.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-size: 20pt; font-weight: bold;"
            "letter-spacing: 4px; padding-bottom: 8px;"
        )

        # ----- title input -----
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("e.g. Phuture Lines")
        self._title_edit.setText(random_title())
        self._title_edit.selectAll()

        # ----- style picker -----
        self._style_combo = QComboBox()
        self._style_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._style_combo.setMinimumWidth(240)
        self._style_combo.view().setMinimumWidth(240)
        for style in STYLES.keys():
            label = style.replace("_", " ").title()
            self._style_combo.addItem(label, style)
        default_style = random_non_blank_style()
        default_index = self._style_combo.findData(default_style)
        if default_index >= 0:
            self._style_combo.setCurrentIndex(default_index)
        self._style_blurb = QLabel("")
        self._style_blurb.setWordWrap(True)
        self._style_blurb.setStyleSheet(f"color: {theme.INK_DIM.name()}; padding: 4px 0;")
        self._style_combo.currentIndexChanged.connect(self._refresh_style_blurb)

        # ----- setup picker -----
        self._setup_combo = QComboBox()
        self._setup_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._setup_combo.setMinimumWidth(240)
        self._setup_combo.view().setMinimumWidth(240)
        for path in bundled_setups():
            self._setup_combo.addItem(f"BUNDLED  ·  {path.stem}", path)
            self._setup_paths[path.stem] = path
        browse_btn = QPushButton("BROWSE…")
        browse_btn.clicked.connect(self._on_browse)
        self._custom_label = QLabel("(no custom setup)")
        self._custom_label.setStyleSheet(f"color: {theme.INK_DIM.name()};")

        setup_row = QHBoxLayout()
        setup_row.addWidget(self._setup_combo, 1)
        setup_row.addWidget(browse_btn)

        # ----- form -----
        form = QFormLayout()
        form.addRow("TITLE", self._title_edit)
        form.addRow("STYLE", self._style_combo)
        form.addRow("", self._style_blurb)
        form.addRow("SETUP", setup_row)
        form.addRow("", self._custom_label)

        # ----- buttons -----
        create_btn = QPushButton("CREATE")
        create_btn.setDefault(True)
        create_btn.clicked.connect(self._on_finish)
        cancel_btn = QPushButton("CANCEL")
        cancel_btn.clicked.connect(self.reject)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(create_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        root.addWidget(title_label)
        root.addLayout(form)
        root.addStretch(1)
        root.addLayout(button_row)

        self._refresh_style_blurb()

    # ----- result --------------------------------------------------------

    def result_song(self) -> tuple[Song, Setup] | None:
        """Return the created (song, setup), or None if cancelled / not finished."""
        return self._result

    # ----- callbacks -----------------------------------------------------

    def _refresh_style_blurb(self) -> None:
        style_id = self._style_combo.currentData()
        self._style_blurb.setText(self._STYLE_BLURBS.get(style_id, ""))

    def _on_browse(self) -> None:
        path_str, _filter = QFileDialog.getOpenFileName(
            self,
            "Pick a custom .jtx-setup",
            str(Path.home()),
            "Setup files (*.jtx-setup)",
        )
        if not path_str:
            return
        path = Path(path_str)
        self._custom_setup_path = path
        self._custom_label.setText(f"Using {path.name}")

    def _on_finish(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "New song", "Title is required.")
            return
        style = self._style_combo.currentData()
        if not isinstance(style, str):
            QMessageBox.warning(self, "New song", "Pick a style.")
            return

        setup_src = self._custom_setup_path or self._setup_combo.currentData()
        if not isinstance(setup_src, Path):
            QMessageBox.warning(self, "New song", "Pick a setup.")
            return
        if not setup_src.exists():
            QMessageBox.critical(self, "New song", f"Setup not found:\n{setup_src}")
            return

        try:
            setup = load_setup(setup_src)
            song = build_song(style, title, setup.id)
        except Exception as exc:  # noqa: BLE001 — surface verbatim
            QMessageBox.critical(self, "New song", f"Couldn't create song:\n{exc}")
            return

        self._result = (song, setup)
        self.accept()
