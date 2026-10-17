"""Visual tokens matching gui-plan/v5."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

BG = "#10151D"
PANEL = "#19222E"
SIDE = "#1F1F23"
SIDE_2 = "#2A2A2F"
INK = "#F1F5FA"
MUTED = "#A7B4C6"
LINE = "#344255"
ACCENT = "#B35128"
ACCENT_HOVER = "#C36236"
ACCENT_SOFT = "#3A2821"
OK = "#75D69D"
WARN = "#EDC16F"
BAD = "#F29B91"
SIDE_TEXT = "#D1D1D6"
SIDE_MUTED = "#8E8E93"


def resources_dir() -> Path:
    return Path(__file__).resolve().parent / "resources"


def load_fonts() -> str:
    """Register Onest and return the family name to use."""
    fonts = resources_dir() / "fonts"
    family = "Onest"
    for path in sorted(fonts.glob("Onest*.ttf")) + sorted(fonts.glob("Onest*.otf")):
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid >= 0:
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                family = families[0]
    return family


def pin_dark_native_chrome(app: QApplication) -> None:
    """Keep native menus dark, matching the window.

    Match native popup appearance to the application palette on macOS/Windows.
    """

    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)


def app_font(family: str, size: int = 13, weight: int = QFont.Weight.Normal) -> QFont:
    font = QFont(family)
    font.setPixelSize(size)
    font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


STYLESHEET = f"""
QMainWindow, QDialog {{
  background: {BG};
  color: {INK};
}}
QWidget {{
  color: {INK};
}}
QMenu {{
  background: {PANEL};
  color: {INK};
  border: 1px solid {LINE};
}}
QMenu::item {{
  background: transparent;
  color: {INK};
  padding: 4px 24px;
}}
QMenu::item:selected {{
  background: {BG};
  color: {INK};
}}
QMenu::item:disabled {{
  color: {MUTED};
}}
QLabel {{
  border: none;
  background: transparent;
}}
QScrollArea {{
  border: none;
  background: transparent;
}}
QLineEdit, QComboBox {{
  background: {PANEL};
  border: 1px solid {LINE};
  border-radius: 6px;
  padding: 4px 8px;
  min-height: 28px;
  selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{
  border: 1px solid {ACCENT};
}}
QPushButton {{
  background: {PANEL};
  border: 1px solid {LINE};
  border-radius: 6px;
  padding: 6px 12px;
  min-height: 28px;
  font-weight: 600;
}}
QPushButton:hover {{
  background: #263448;
}}
QPushButton:disabled {{
  color: {MUTED};
  background: #202C3B;
}}
QPushButton#primary {{
  background: {ACCENT};
  border: 1px solid {ACCENT};
  color: white;
}}
QPushButton#primary:hover {{
  background: {ACCENT_HOVER};
  border-color: {ACCENT_HOVER};
}}
QPushButton#primary:disabled {{
  background: #344255;
  border-color: #344255;
  color: {MUTED};
}}
QPushButton#danger {{
  color: {BAD};
  border-color: #E5B4AE;
}}
QTableWidget {{
  background: {PANEL};
  border: 1px solid {LINE};
  border-radius: 8px;
  gridline-color: #293649;
  selection-background-color: {ACCENT_SOFT};
  selection-color: {INK};
}}
QHeaderView::section {{
  background: #202C3B;
  color: {MUTED};
  border: none;
  border-bottom: 1px solid {LINE};
  padding: 8px 12px;
  font-weight: 600;
}}
QCheckBox {{
  spacing: 8px;
}}
QCheckBox::indicator {{
  width: 15px;
  height: 15px;
}}
QProgressBar {{
  border: 1px solid {LINE};
  border-radius: 4px;
  background: #202C3B;
  text-align: center;
  max-height: 8px;
}}
QProgressBar::chunk {{
  background: {ACCENT};
  border-radius: 3px;
}}
QTextEdit#log {{
  background: #1F1F23;
  color: #D1D1D6;
  border-radius: 8px;
  border: none;
  font-family: ui-monospace, SF Mono, Menlo, Consolas, monospace;
  font-size: 12px;
}}
"""

# Backward-compatible import for older front ends.
pin_light_native_chrome = pin_dark_native_chrome
