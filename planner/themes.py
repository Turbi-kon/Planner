"""Общие цвета окна, диалогов, календаря и выпадающих списков."""
from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


DEFAULT_THEME = "gray"
THEME_NAMES = {"gray": "Серая", "white": "Белая", "dark": "Тёмная"}
THEMES = {
    "gray": dict(
        background="#B4B8BE", surface="#C5C9CE", field="#D1D4D8", text="#252B32",
        muted="#505B66", border="#9BA3AC", hover="#D3D7DC", pressed="#A6AFB7",
        accent_surface="#BACAC3", accent_border="#9AAFA5", accent_text="#244A3E",
        primary="#345E53", primary_hover="#284D43", primary_text="#F2F5F3",
        selection="#AEC6BC", selected_text="#203D33", focus="#477667",
        disabled_text="#707A84", disabled_surface="#BFC4CA", danger="#8D3C36",
        scroll="#929DA5", overdue="#80522F", upcoming="#2E604A",
    ),
    "white": dict(
        background="#F5F6F7", surface="#FFFFFF", field="#F8F9FA", text="#27313A",
        muted="#64717B", border="#D7DEE3", hover="#EDF2EF", pressed="#DCE6DF",
        accent_surface="#E8F0EA", accent_border="#D1DFD5", accent_text="#234B3B",
        primary="#2B604C", primary_hover="#1F4B3B", primary_text="#FFFFFF",
        selection="#D9E9DF", selected_text="#1B4030", focus="#4C876A",
        disabled_text="#8C969F", disabled_surface="#F0F2F3", danger="#A0463B",
        scroll="#C1CBC5", overdue="#8C5B36", upcoming="#316E4C",
    ),
    "dark": dict(
        background="#202327", surface="#292D33", field="#23272D", text="#E4E7EB",
        muted="#A3ADB9", border="#444B55", hover="#373E47", pressed="#414B55",
        accent_surface="#2B3D37", accent_border="#425D51", accent_text="#B4D5C6",
        primary="#356B59", primary_hover="#427F6C", primary_text="#F2F6F4",
        selection="#3D594D", selected_text="#F0F7F3", focus="#7FAE99",
        disabled_text="#78838F", disabled_surface="#2D3239", danger="#EDA49A",
        scroll="#525E69", overdue="#DDB082", upcoming="#97C8AC",
    ),
}


STYLE = Template("""
QWidget { color: $text; font-family: 'Segoe UI', 'Segoe UI Emoji', 'Segoe UI Symbol'; font-size: 13px; }
QMainWindow, QDialog, QWidget#root { background: $background; }
QTabWidget::pane { background: $background; border: 1px solid $border; border-radius: 8px; padding: 10px; }
QTabBar::tab { background: $surface; color: $muted; border: 1px solid $border; padding: 10px 15px; margin-right: 4px; }
QTabBar::tab:selected { background: $accent_surface; color: $accent_text; border-bottom-color: $accent_surface; }
QLabel#eyebrow { color: $muted; font-size: 11px; font-weight: 700; }
QLabel#heading { font-size: 30px; font-weight: 700; color: $accent_text; }
QLabel#subtitle, QLabel#muted { color: $muted; }
QLabel#section { font-size: 18px; font-weight: 650; }
QLabel#statValue { font-size: 23px; font-weight: 700; color: $accent_text; }
QLabel#nextValue { font-size: 16px; font-weight: 650; color: $accent_text; }
QFrame#card, QFrame#editor { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#nextCard { background: $accent_surface; border: 1px solid $accent_border; border-radius: 14px; }
QLabel#banner { background: $accent_surface; color: $accent_text; border-radius: 8px; padding: 10px 14px; }
QPushButton { background: $surface; border: 1px solid $border; border-radius: 8px; padding: 9px 15px; font-weight: 600; }
QPushButton:hover { background: $hover; border-color: $focus; }
QPushButton:pressed { background: $pressed; }
QPushButton:disabled { color: $disabled_text; background: $disabled_surface; }
QPushButton#primary { background: $primary; color: $primary_text; border-color: $primary; }
QPushButton#primary:hover { background: $primary_hover; }
QPushButton#danger { color: $danger; }
QLineEdit, QTextEdit, QDateEdit, QTimeEdit, QComboBox, QSpinBox {
    background: $field; color: $text; border: 1px solid $border; border-radius: 7px;
    padding: 8px; selection-background-color: $selection; selection-color: $selected_text;
}
QLineEdit:focus, QTextEdit:focus, QDateEdit:focus, QTimeEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: $focus; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: $field; color: $text; selection-background-color: $selection; selection-color: $selected_text; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QTableWidget { background: $surface; alternate-background-color: $surface; border: none; gridline-color: $border; border-radius: 10px; outline: none; }
QTableWidget::item { padding: 10px; border-bottom: 1px solid $border; }
QTableWidget::item:selected { background: $selection; color: $selected_text; }
QHeaderView::section { background: $background; color: $muted; padding: 11px; border: none; font-size: 11px; font-weight: 650; }
QScrollBar:vertical { background: $background; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: $scroll; min-height: 25px; border-radius: 5px; }
QStatusBar { background: $background; color: $muted; }
QMenu { background: $surface; color: $text; border: 1px solid $border; }
QMenu::item:selected { background: $selection; color: $selected_text; }
QToolTip { background: $surface; color: $text; border: 1px solid $border; padding: 5px; }
QCalendarWidget QWidget { background: $surface; color: $text; }
QCalendarWidget QToolButton { background: $surface; color: $text; padding: 5px; }
QCalendarWidget QAbstractItemView { background: $field; color: $text; selection-background-color: $selection; selection-color: $selected_text; }
""")


def apply_theme(theme: str) -> str:
    theme = theme if theme in THEMES else DEFAULT_THEME
    colors = THEMES[theme]
    app = QApplication.instance()
    # Fusion позволяет палитре окрашивать и нативные элементы, например флажки.
    app.setStyle("Fusion")
    palette = QPalette()
    roles = {
        "Window": "background", "WindowText": "text", "Base": "field",
        "AlternateBase": "surface", "Text": "text", "Button": "surface",
        "ButtonText": "text", "ToolTipBase": "surface", "ToolTipText": "text",
        "Highlight": "selection", "HighlightedText": "selected_text",
        "PlaceholderText": "muted", "Light": "hover", "Midlight": "surface",
        "Mid": "border", "Dark": "border", "Shadow": "background", "Link": "focus",
    }
    for role, key in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(colors[key]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["disabled_text"]))
    app.setPalette(palette)
    app.setStyleSheet(STYLE.substitute(colors))
    return theme
