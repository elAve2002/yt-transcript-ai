"""Tema claro/oscuro y QSS de la aplicación."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QGuiApplication, QPalette


@dataclass(frozen=True)
class Palette:
    window: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str = "#ffffff"


def get_palette(theme: str = "system", accent: str = "#4f46e5") -> Palette:
    dark = QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
    if theme == "dark" or (theme == "system" and dark):
        return Palette("#111318", "#191c23", "#222631", "#303644", "#f3f4f6", "#a5adbd", accent)
    return Palette("#f5f6f8", "#ffffff", "#f0f1f5", "#dfe2e8", "#17191d", "#616875", accent)


def stylesheet(theme: str = "system", accent: str = "#4f46e5") -> str:
    p = get_palette(theme, accent)
    return f"""
    * {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', sans-serif;
         font-size: 13px; color: {p.text}; }}
    QMainWindow, QDialog {{ background: {p.window}; }}
    QWidget#central, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {p.window}; }}
    QFrame#sidebar {{ background: {p.surface}; border-right: 1px solid {p.border}; }}
    QFrame#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
    QFrame#previewCard {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px; }}
    QLabel#title {{ font-size: 25px; font-weight: 700; }}
    QLabel#subtitle, QLabel[muted="true"] {{ color: {p.muted}; }}
    QLabel#sectionTitle {{ font-size: 16px; font-weight: 600; }}
    QLabel#badge {{ background: {p.accent}; color: white; border-radius: 9px; padding: 1px 6px; font-size: 11px; }}
    QPushButton {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 7px;
                  padding: 7px 12px; min-height: 18px; }}
    QPushButton:hover {{ border-color: {p.accent}; }}
    QPushButton:focus {{ border: 2px solid {p.accent}; }}
    QPushButton:disabled {{ color: {p.muted}; background: {p.surface}; }}
    QPushButton#primary {{ background: {p.accent}; color: {p.accent_text}; border: none; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {p.accent}; border: 1px solid {p.accent_text}; }}
    QPushButton#danger {{ color: #dc2626; }}
    QPushButton#navButton {{ text-align: left; border: none; background: transparent; padding: 10px 12px; }}
    QPushButton#navButton:checked {{ background: {p.accent}; color: white; }}
    QPushButton#segment {{ border-radius: 6px; }}
    QPushButton#segment:checked {{ background: {p.accent}; color: white; border-color: {p.accent}; }}
    QLineEdit, QComboBox, QSpinBox {{ background: {p.surface}; border: 1px solid {p.border};
        border-radius: 7px; padding: 7px 9px; selection-background-color: {p.accent}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {p.accent}; }}
    QComboBox::drop-down {{ border: none; width: 25px; }}
    QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
        selection-background-color: {p.accent}; }}
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; }}
    QProgressBar {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 6px;
                   height: 11px; text-align: center; font-size: 10px; }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 5px; }}
    QPlainTextEdit {{ background: #101216; color: #d8dee9; border: 1px solid {p.border};
                     border-radius: 8px; padding: 7px; font-family: 'SF Mono', Menlo, monospace; font-size: 12px; }}
    QTableWidget {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px;
                   gridline-color: {p.border}; alternate-background-color: {p.surface_alt}; }}
    QHeaderView::section {{ background: {p.surface_alt}; border: none; border-bottom: 1px solid {p.border};
                           padding: 8px; font-weight: 600; }}
    QTableWidget::item {{ padding: 5px; }}
    QTableWidget::item:selected {{ background: {p.accent}; color: white; }}
    QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 5px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 25px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    """
