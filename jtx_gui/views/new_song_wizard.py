"""Three-step new-song wizard.

Page 1: title.
Page 2: style template (acid / deep_techno / psytrance).
Page 3: bundled setup (iac / ableton / pick a custom .jtx-setup).

On finish, asks the user for a target directory, writes the song +
a copy of the chosen setup beside it, and hands the resulting path
back to the caller via ``picked_path``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from jtx.model import Song
from jtx.persist import load_setup, save_song
from jtx_gui import theme
from jtx_gui.bundles import bundled_setups
from templates import STYLES
from templates import build as build_song

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "song"


# --------------------------------------------------------------------------
#                              wizard pages
# --------------------------------------------------------------------------


class _TitlePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("NEW SONG  ·  TITLE")
        self.setSubTitle("The title seeds the song's deterministic PRNG.")
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("e.g. Phuture Lines")
        self.registerField("title*", self._title_edit)
        form = QFormLayout(self)
        form.addRow("TITLE", self._title_edit)


class _StylePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("NEW SONG  ·  STYLE")
        self.setSubTitle(
            "Style picks the starting arrangement. It is *not* stored on the "
            "resulting song — swap algorithms / knobs freely later."
        )
        self._buttons: dict[str, QRadioButton] = {}
        layout = QVBoxLayout(self)
        descriptions = {
            "acid": "Four-on-floor, 303 lead bass, chord stab, filter LFO. 126 BPM A minor.",
            "deep_techno": "Sub drone, dub stab, sparse top-end. 122 BPM C minor.",
            "psytrance": "Rolling offbeat bass, fast arp leads. 145 BPM F# minor.",
        }
        for index, style in enumerate(STYLES.keys()):
            btn = QRadioButton(style.replace("_", " ").upper())
            btn.setStyleSheet(
                f"QRadioButton {{ color: {theme.INK.name()}; font-weight: 800;"
                "letter-spacing: 1px; padding: 4px 0; }}"
            )
            blurb = QLabel(descriptions.get(style, ""))
            blurb.setStyleSheet(f"color: {theme.INK_DIM.name()}; padding-left: 24px;")
            blurb.setWordWrap(True)
            self._buttons[style] = btn
            if index == 0:
                btn.setChecked(True)
            layout.addWidget(btn)
            layout.addWidget(blurb)
        layout.addStretch(1)

    def selected_style(self) -> str:
        for style, btn in self._buttons.items():
            if btn.isChecked():
                return style
        return next(iter(STYLES.keys()))


class _SetupPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("NEW SONG  ·  SETUP")
        self.setSubTitle(
            "Pick a bundled setup (it'll be copied next to your song) "
            "or browse to a custom .jtx-setup."
        )

        self._radios: dict[str, QRadioButton] = {}
        self._setup_paths: dict[str, Path] = {}
        self._custom_path: Path | None = None

        layout = QVBoxLayout(self)

        for index, path in enumerate(bundled_setups()):
            label = f"BUNDLED  ·  {path.stem.upper()}  ·  {path.name}"
            btn = QRadioButton(label)
            btn.setStyleSheet(
                f"QRadioButton {{ color: {theme.INK.name()}; font-weight: 700;"
                "letter-spacing: 1px; padding: 4px 0; }}"
            )
            self._radios[path.stem] = btn
            self._setup_paths[path.stem] = path
            if index == 0:
                btn.setChecked(True)
            layout.addWidget(btn)

        custom_row = QHBoxLayout()
        self._custom_radio = QRadioButton("CUSTOM .jtx-setup")
        self._custom_radio.setStyleSheet(
            f"QRadioButton {{ color: {theme.INK.name()}; font-weight: 700;"
            "letter-spacing: 1px; padding: 4px 0; }}"
        )
        browse_btn = QPushButton("BROWSE…")
        browse_btn.clicked.connect(self._on_browse)
        self._custom_label = QLabel("(none selected)")
        self._custom_label.setStyleSheet(f"color: {theme.INK_DIM.name()};")
        custom_row.addWidget(self._custom_radio)
        custom_row.addWidget(browse_btn)
        custom_row.addWidget(self._custom_label, 1)
        layout.addLayout(custom_row)
        layout.addStretch(1)

    def selected_setup_path(self) -> Path | None:
        if self._custom_radio.isChecked():
            return self._custom_path
        for name, btn in self._radios.items():
            if btn.isChecked():
                return self._setup_paths[name]
        return None

    def _on_browse(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Pick a .jtx-setup",
            str(Path.home()),
            "Setup files (*.jtx-setup)",
        )
        if not path:
            return
        self._custom_path = Path(path)
        self._custom_label.setText(self._custom_path.name)
        self._custom_radio.setChecked(True)


# --------------------------------------------------------------------------
#                                 wizard
# --------------------------------------------------------------------------


class NewSongWizard(QWizard):
    """Drives the three pages and assembles a saved song on finish."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Jamtronix — New Song")
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        self._title_page = _TitlePage()
        self._style_page = _StylePage()
        self._setup_page = _SetupPage()
        self.addPage(self._title_page)
        self.addPage(self._style_page)
        self.addPage(self._setup_page)
        self.resize(560, 460)
        self._created_path: Path | None = None

    def created_path(self) -> Path | None:
        return self._created_path

    def accept(self) -> None:  # called on Finish click
        try:
            self._created_path = self._finish_create()
        except Exception as exc:  # noqa: BLE001 — surface verbatim
            QMessageBox.critical(self, "Couldn't create song", str(exc))
            return
        super().accept()

    def _finish_create(self) -> Path:
        title = str(self.field("title")).strip()
        if not title:
            raise ValueError("Title is required.")
        style = self._style_page.selected_style()
        setup_src = self._setup_page.selected_setup_path()
        if setup_src is None:
            raise ValueError("Pick a setup, or pick Custom and browse to one.")
        if not setup_src.exists():
            raise FileNotFoundError(f"Setup not found: {setup_src}")

        # Validate the setup before we let the user save anywhere.
        setup = load_setup(setup_src)

        slug = _slug(title)
        suggested_dir = Path.home() / "Documents" / "Jamtronix"
        suggested = suggested_dir / f"{slug}.jtx"
        target_str, _filter = QFileDialog.getSaveFileName(
            self,
            "Save new Jamtronix song",
            str(suggested),
            "Jamtronix song (*.jtx)",
        )
        if not target_str:
            raise ValueError("Save cancelled.")
        target = Path(target_str)
        target.parent.mkdir(parents=True, exist_ok=True)

        # The song references the setup by id; copy the setup file beside
        # the song so AppState.open() picks it up via the sibling rule.
        setup_dest = target.parent / f"{setup.id}.jtx-setup"
        if setup_dest != setup_src:
            setup_dest.write_text(
                json.dumps(asdict(setup), indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
            )

        song: Song = build_song(style, title, setup.id)
        save_song(song, target)
        return target
