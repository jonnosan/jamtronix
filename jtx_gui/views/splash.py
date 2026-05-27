"""Splash dialog shown at launch — pick New or Open."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jtx_gui import theme


class SplashDialog(QDialog):
    """Modal startup dialog. Result: ``"new"``, ``"open"``, or rejected."""

    RESULT_NEW = "new"
    RESULT_OPEN = "open"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Jamtronix")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._result: str | None = None

        title = QLabel("JAMTRONIX")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {theme.INK_HOT.name()}; font-size: 28pt; font-weight: bold;"
            "letter-spacing: 6px; padding-top: 8px;"
        )
        subtitle = QLabel("MIDI JAM TOOL — V1")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {theme.INK_DIM.name()}; font-size: 10pt; letter-spacing: 4px;"
            "padding-bottom: 24px;"
        )

        new_btn = QPushButton("NEW SONG")
        new_btn.setMinimumHeight(56)
        open_btn = QPushButton("OPEN SONG…")
        open_btn.setMinimumHeight(56)
        open_btn.setDefault(True)

        new_btn.clicked.connect(lambda: self._pick(self.RESULT_NEW))
        open_btn.clicked.connect(lambda: self._pick(self.RESULT_OPEN))

        button_row = QHBoxLayout()
        button_row.setSpacing(14)
        button_row.addWidget(new_btn, 1)
        button_row.addWidget(open_btn, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addLayout(button_row)

    def picked(self) -> str | None:
        return self._result

    def _pick(self, which: str) -> None:
        self._result = which
        self.accept()
