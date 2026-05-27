"""Visual theme for Jamtronix — 'mad-scientist 1950s sci-fi' palette.

Charcoal panels, brass-knob faces, cream tick marks, amber-glow accents.
Single source of truth for colours; widgets read constants from here so
the look stays coherent if we retune the palette.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

# ---- palette ---------------------------------------------------------------

PANEL_BG = QColor("#1a1410")  # deep brown-black bakelite
PANEL_BG_ALT = QColor("#221a14")  # row stripe
PANEL_BORDER = QColor("#3d2e22")  # warm bezel edge
INK = QColor("#e8d9b8")  # cream stencil ink
INK_DIM = QColor("#8a7a5e")  # faded label
INK_HOT = QColor("#f4c97a")  # active brass

BRASS_DARK = QColor("#5a4426")
BRASS_MID = QColor("#a07840")
BRASS_LIGHT = QColor("#d4a663")
BRASS_HIGHLIGHT = QColor("#f0d090")

ACCENT_AMBER = QColor("#ffae3d")  # power-on glow
ACCENT_GREEN = QColor("#7dd97a")  # signal lock
ACCENT_RED = QColor("#d94a3d")  # warning lamp
MOD_DOT = QColor("#ff4a6a")  # modulator-bound indicator

# ---- typography ------------------------------------------------------------

# A condensed mechanical-feel sans is the closest stock match for the
# stencil-on-bakelite label style. Helvetica Neue Condensed Bold is on
# every macOS install; we fall back through sensible alternatives.
LABEL_FONT_FAMILY = "Helvetica Neue, Arial Narrow, sans-serif"
MONO_FONT_FAMILY = "Menlo, Monaco, Courier New, monospace"


def label_font(size: int = 10, bold: bool = True) -> QFont:
    f = QFont(LABEL_FONT_FAMILY.split(",")[0].strip())
    f.setPointSize(size)
    f.setBold(bold)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
    return f


def value_font(size: int = 11) -> QFont:
    f = QFont(MONO_FONT_FAMILY.split(",")[0].strip())
    f.setPointSize(size)
    f.setBold(True)
    return f


# ---- application palette + stylesheet --------------------------------------


def apply(app) -> None:  # type: ignore[no-untyped-def]
    """Apply the dark palette + global stylesheet to a QApplication."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, PANEL_BG)
    pal.setColor(QPalette.ColorRole.WindowText, INK)
    pal.setColor(QPalette.ColorRole.Base, PANEL_BG_ALT)
    pal.setColor(QPalette.ColorRole.AlternateBase, PANEL_BG)
    pal.setColor(QPalette.ColorRole.Text, INK)
    pal.setColor(QPalette.ColorRole.Button, PANEL_BG_ALT)
    pal.setColor(QPalette.ColorRole.ButtonText, INK)
    pal.setColor(QPalette.ColorRole.Highlight, BRASS_MID)
    pal.setColor(QPalette.ColorRole.HighlightedText, PANEL_BG)
    pal.setColor(QPalette.ColorRole.ToolTipBase, INK)
    pal.setColor(QPalette.ColorRole.ToolTipText, PANEL_BG)
    pal.setColor(QPalette.ColorRole.PlaceholderText, INK_DIM)
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)


STYLESHEET = f"""
QWidget {{
    background-color: {PANEL_BG.name()};
    color: {INK.name()};
    font-family: "{LABEL_FONT_FAMILY.split(",")[0].strip()}";
    font-size: 11pt;
}}

QMainWindow, QDialog {{
    background-color: {PANEL_BG.name()};
}}

QFrame#Sidebar {{
    background-color: #14100c;
    border-right: 2px solid {PANEL_BORDER.name()};
}}

QPushButton {{
    background-color: {BRASS_DARK.name()};
    color: {INK.name()};
    border: 1px solid {BRASS_MID.name()};
    border-radius: 2px;
    padding: 6px 14px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QPushButton:hover {{
    background-color: {BRASS_MID.name()};
    color: {PANEL_BG.name()};
}}
QPushButton:pressed {{
    background-color: {BRASS_LIGHT.name()};
    color: {PANEL_BG.name()};
}}
QPushButton:disabled {{
    background-color: #2a2018;
    color: {INK_DIM.name()};
    border: 1px solid #3a2c20;
}}
QPushButton#SidebarButton {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 12px 18px;
    text-align: left;
    color: {INK_DIM.name()};
}}
QPushButton#SidebarButton:hover {{
    color: {INK.name()};
    background-color: rgba(255, 174, 61, 24);
}}
QPushButton#SidebarButton:checked {{
    color: {INK_HOT.name()};
    border-left: 3px solid {ACCENT_AMBER.name()};
    background-color: rgba(255, 174, 61, 40);
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background-color: #0e0a07;
    color: {INK.name()};
    border: 1px solid {PANEL_BORDER.name()};
    border-radius: 2px;
    padding: 4px 6px;
    selection-background-color: {BRASS_MID.name()};
    selection-color: {PANEL_BG.name()};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {BRASS_LIGHT.name()};
}}

QComboBox::drop-down {{
    background-color: {BRASS_DARK.name()};
    border-left: 1px solid {PANEL_BORDER.name()};
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: #0e0a07;
    border: 1px solid {BRASS_MID.name()};
    selection-background-color: {BRASS_MID.name()};
    selection-color: {PANEL_BG.name()};
}}

QLabel {{
    color: {INK.name()};
    background: transparent;
}}
QLabel#SectionTitle {{
    color: {INK_HOT.name()};
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 6px 0;
    border-bottom: 1px solid {PANEL_BORDER.name()};
}}
QLabel#FieldLabel {{
    color: {INK_DIM.name()};
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 700;
    font-size: 9pt;
}}

QFrame#Panel, QGroupBox {{
    background-color: {PANEL_BG_ALT.name()};
    border: 1px solid {PANEL_BORDER.name()};
    border-radius: 3px;
    padding: 8px;
    margin-top: 8px;
}}
QGroupBox::title {{
    color: {INK_HOT.name()};
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    background-color: {PANEL_BG.name()};
    text-transform: uppercase;
    letter-spacing: 1px;
}}

QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: #14100c;
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BRASS_DARK.name()};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BRASS_MID.name()};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0; background: none;
}}

QMenuBar {{
    background-color: #14100c;
    color: {INK.name()};
    border-bottom: 1px solid {PANEL_BORDER.name()};
}}
QMenuBar::item:selected {{
    background-color: {BRASS_MID.name()};
    color: {PANEL_BG.name()};
}}
QMenu {{
    background-color: #14100c;
    color: {INK.name()};
    border: 1px solid {BRASS_MID.name()};
}}
QMenu::item:selected {{
    background-color: {BRASS_MID.name()};
    color: {PANEL_BG.name()};
}}

QListWidget {{
    background-color: #0e0a07;
    border: 1px solid {PANEL_BORDER.name()};
    border-radius: 2px;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid #1f1812;
}}
QListWidget::item:selected {{
    background-color: {BRASS_DARK.name()};
    color: {INK_HOT.name()};
}}
"""
