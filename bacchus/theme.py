"""
Theme management for Bacchus.

Provides light and dark theme stylesheets.
"""

LIGHT_THEME = """
QMainWindow {
    background-color: #ffffff;
    color: #333333;
}

QWidget {
    background-color: #ffffff;
    color: #333333;
}

QLabel {
    color: #333333;
}

QPushButton {
    background-color: #f0f0f0;
    color: #333333;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 6px 12px;
}

QPushButton:hover {
    background-color: #e0e0e0;
}

QPushButton:pressed {
    background-color: #d0d0d0;
}

QPushButton:disabled {
    background-color: #f5f5f5;
    color: #999999;
}

QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 4px;
}

QLineEdit {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 4px;
}

QComboBox {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 4px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #333333;
}

QListWidget {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cccccc;
}

QListWidget::item {
    padding: 8px;
}

QListWidget::item:selected {
    background-color: #e3f2fd;
    color: #1976d2;
}

QListWidget::item:hover {
    background-color: #f5f5f5;
}

QScrollBar:vertical {
    background-color: #f0f0f0;
    width: 12px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #cccccc;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #bbbbbb;
}

QScrollBar:horizontal {
    background-color: #f0f0f0;
    height: 12px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #cccccc;
    border-radius: 6px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #bbbbbb;
}

QGroupBox {
    color: #333333;
    border: 1px solid #cccccc;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: #ffffff;
}

QMenuBar {
    background-color: #f0f0f0;
    color: #333333;
    padding: 2px;
}

QMenuBar::item {
    padding: 5px 12px;
    background: transparent;
    border-radius: 3px;
}

QMenuBar::item:selected {
    background-color: #e0e0e0;
}

QMenuBar::item:pressed {
    background-color: #d0d0d0;
}

QMenu {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cccccc;
    padding: 4px 0;
}

QMenu::item {
    padding: 6px 40px 6px 20px;
}

QMenu::item:selected {
    background-color: #e3f2fd;
    color: #1976d2;
}

QMenu::separator {
    height: 1px;
    background-color: #e0e0e0;
    margin: 4px 8px;
}

QCheckBox {
    color: #333333;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #bbbbbb;
    border-radius: 3px;
    background-color: #ffffff;
}

QCheckBox::indicator:checked {
    background-color: #4caf50;
    border-color: #4caf50;
}

QCheckBox::indicator:hover {
    border-color: #888888;
}

QCheckBox::indicator:disabled {
    border-color: #dddddd;
    background-color: #f5f5f5;
}

QRadioButton {
    color: #333333;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #bbbbbb;
    border-radius: 9px;
    background-color: #ffffff;
}

QRadioButton::indicator:checked {
    background-color: #4caf50;
    border-color: #4caf50;
}

QRadioButton::indicator:hover {
    border-color: #888888;
}

QRadioButton::indicator:disabled {
    border-color: #dddddd;
    background-color: #f5f5f5;
}

QProgressBar {
    background-color: #f0f0f0;
    border: 1px solid #cccccc;
    border-radius: 4px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #4caf50;
    border-radius: 3px;
}

QHeaderView::section {
    background-color: #f5f5f5;
    color: #333333;
    border: none;
    border-bottom: 1px solid #cccccc;
    border-right: 1px solid #e0e0e0;
    padding: 6px 8px;
    font-weight: bold;
}

QTableWidget {
    gridline-color: #e8e8e8;
}

ConversationListItem {
    border-radius: 6px;
}

ConversationListItem:hover {
    background-color: #f0f0f0;
}

Sidebar {
    border-right: 1px solid #e0e0e0;
}

PromptArea {
    background-color: #f5f5f5;
    border-top: 1px solid #e0e0e0;
}
"""

DARK_THEME = """
QMainWindow {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
}

QLabel {
    color: #e0e0e0;
}

QPushButton {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 6px 12px;
}

QPushButton:hover {
    background-color: #3d3d3d;
}

QPushButton:pressed {
    background-color: #4d4d4d;
}

QPushButton:disabled {
    background-color: #252525;
    color: #666666;
}

QTextEdit, QPlainTextEdit {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 4px;
}

QLineEdit {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 4px;
}

QComboBox {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 4px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #e0e0e0;
}

QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #e0e0e0;
    selection-background-color: #3d5a80;
}

QListWidget {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
}

QListWidget::item {
    padding: 8px;
}

QListWidget::item:selected {
    background-color: #3d5a80;
    color: #ffffff;
}

QListWidget::item:hover {
    background-color: #353535;
}

QScrollBar:vertical {
    background-color: #2d2d2d;
    width: 12px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #4d4d4d;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #5d5d5d;
}

QScrollBar:horizontal {
    background-color: #2d2d2d;
    height: 12px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #4d4d4d;
    border-radius: 6px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #5d5d5d;
}

QGroupBox {
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: #1e1e1e;
}

QMenuBar {
    background-color: #2d2d2d;
    color: #e0e0e0;
    padding: 2px;
}

QMenuBar::item {
    padding: 5px 12px;
    background: transparent;
    border-radius: 3px;
}

QMenuBar::item:selected {
    background-color: #3d3d3d;
}

QMenuBar::item:pressed {
    background-color: #4d4d4d;
}

QMenu {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
    padding: 4px 0;
}

QMenu::item {
    padding: 6px 40px 6px 20px;
}

QMenu::item:selected {
    background-color: #3d5a80;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background-color: #3d3d3d;
    margin: 4px 8px;
}

QCheckBox {
    color: #e0e0e0;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #5d5d5d;
    border-radius: 3px;
    background-color: #2d2d2d;
}

QCheckBox::indicator:checked {
    background-color: #4caf50;
    border-color: #4caf50;
}

QCheckBox::indicator:hover {
    border-color: #8d8d8d;
}

QCheckBox::indicator:disabled {
    border-color: #3d3d3d;
    background-color: #252525;
}

QRadioButton {
    color: #e0e0e0;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #5d5d5d;
    border-radius: 9px;
    background-color: #2d2d2d;
}

QRadioButton::indicator:checked {
    background-color: #4caf50;
    border-color: #4caf50;
}

QRadioButton::indicator:hover {
    border-color: #8d8d8d;
}

QRadioButton::indicator:disabled {
    border-color: #3d3d3d;
    background-color: #252525;
}

QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    text-align: center;
    color: #e0e0e0;
}

QProgressBar::chunk {
    background-color: #4caf50;
    border-radius: 3px;
}

QHeaderView::section {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: none;
    border-bottom: 1px solid #3d3d3d;
    border-right: 1px solid #3d3d3d;
    padding: 6px 8px;
    font-weight: bold;
}

QTableWidget {
    gridline-color: #3d3d3d;
}

QScrollArea {
    background-color: #1e1e1e;
    border: none;
}

ConversationListItem {
    border-radius: 6px;
}

ConversationListItem:hover {
    background-color: #2a2a2a;
}

Sidebar {
    border-right: 1px solid #2d2d2d;
}

PromptArea {
    background-color: #252525;
    border-top: 1px solid #3d3d3d;
}
"""


def get_theme_stylesheet(theme_name: str) -> str:
    """
    Get stylesheet for the specified theme.

    Args:
        theme_name: Either "light" or "dark"

    Returns:
        CSS stylesheet string
    """
    if theme_name == "dark":
        return DARK_THEME
    else:
        return LIGHT_THEME
