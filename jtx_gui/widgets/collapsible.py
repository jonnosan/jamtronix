"""CollapsibleSection — header bar with disclosure arrow, hides content body."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from jtx_gui import theme


class CollapsibleSection(QFrame):
    """A pane with a clickable header that shows or hides its body."""

    def __init__(
        self,
        title: str,
        *,
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._toggle = QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setStyleSheet(
            f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {theme.INK_HOT.name()};
                font-weight: bold;
                letter-spacing: 1px;
                padding: 4px 0;
            }}
            QToolButton:hover {{
                color: {theme.ACCENT_AMBER.name()};
            }}
            """
        )
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow,
        )
        self._toggle.clicked.connect(self._on_toggle)

        self._header_label = QLabel("", self)  # right-side hint text (e.g. count)
        self._header_label.setObjectName("FieldLabel")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)
        header.addStretch(1)
        header.addWidget(self._header_label, 0, Qt.AlignmentFlag.AlignRight)

        self._body = QWidget(self)
        self._body.setVisible(expanded)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 4, 0, 0)
        self._body_layout.setSpacing(4)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 8)
        root.setSpacing(4)
        root.addLayout(header)
        root.addWidget(self._body)

    def set_header_hint(self, text: str) -> None:
        self._header_label.setText(text)

    def set_title(self, title: str) -> None:
        self._toggle.setText(title)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_widget(self, w: QWidget) -> None:
        self._body_layout.addWidget(w)

    def _on_toggle(self, checked: bool) -> None:
        self._body.setVisible(checked)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow,
        )
