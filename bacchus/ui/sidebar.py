"""
Sidebar widget for Bacchus.

Displays project sections (collapsible) above date-grouped unassigned conversations.
Supports creating, editing, and deleting projects via right-click context menus.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QAction, QCursor

from bacchus import locales
from bacchus.constants import SIDEBAR_WIDTH, CONVERSATION_LIST_TITLE_LENGTH
from bacchus.database import Database, Conversation, Project


logger = logging.getLogger(__name__)


# ── ConversationListItem ──────────────────────────────────────────────────────

class ConversationListItem(QWidget):
    """Single conversation item in the sidebar list."""

    clicked = pyqtSignal(int)  # Emits conversation_id

    def __init__(self, conversation: Conversation, parent=None):
        super().__init__(parent)
        self.conversation_id = conversation.id
        self.has_document = conversation.document_path is not None

        title = conversation.title
        if len(title) > CONVERSATION_LIST_TITLE_LENGTH:
            title = title[:CONVERSATION_LIST_TITLE_LENGTH] + "..."

        timestamp = self._format_timestamp(conversation.updated_at)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(2)

        title_text = f"📎 {title}" if self.has_document else title
        self.title_label = QLabel(title_text)
        self.title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(self.title_label)

        self.time_label = QLabel(timestamp)
        self.time_label.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(self.time_label)

        self.setLayout(layout)
        self.setStyleSheet("""
            ConversationListItem {
                border-radius: 6px;
                border-bottom: 1px solid rgba(128, 128, 128, 0.35);
                margin: 1px 2px;
            }
        """)
        self.setMouseTracking(True)

    def _format_timestamp(self, updated_at: str) -> str:
        try:
            dt = datetime.fromisoformat(updated_at)
            now = datetime.now()
            if dt.date() == now.date():
                return dt.strftime("%H:%M")
            else:
                return dt.strftime("%b %d")
        except Exception:
            return ""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.conversation_id)


# ── ProjectSectionHeader ──────────────────────────────────────────────────────

class ProjectSectionHeader(QWidget):
    """
    Header row for a project section.

    Layout: [▶/▼ arrow] [project name label] [stretch] [+ button]
    Right-click → context menu: Edit Project, Delete Project
    """

    toggle_clicked = pyqtSignal()
    new_conversation_requested = pyqtSignal()
    edit_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self._collapsed = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 4, 4)
        layout.setSpacing(4)

        self._arrow_label = QLabel("▶")
        self._arrow_label.setFixedWidth(14)
        self._arrow_label.setStyleSheet("font-size: 10px; color: #888;")
        layout.addWidget(self._arrow_label)

        self._name_label = QLabel(project.name)
        self._name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(self._name_label)

        layout.addStretch()

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedSize(20, 20)
        self._add_btn.setToolTip("New conversation in project")
        self._add_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #888;
                border-radius: 3px;
                font-weight: bold;
                color: #888;
            }
            QPushButton:hover {
                background: rgba(128, 128, 128, 0.2);
                color: #fff;
            }
        """)
        self._add_btn.clicked.connect(self.new_conversation_requested)
        layout.addWidget(self._add_btn)

        self.setStyleSheet("""
            ProjectSectionHeader {
                border-radius: 4px;
                margin: 2px 2px 0px 2px;
            }
            ProjectSectionHeader:hover {
                background: rgba(128, 128, 128, 0.15);
            }
        """)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._arrow_label.setText("▶" if collapsed else "▼")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_clicked.emit()
        else:
            super().mousePressEvent(event)

    def update_name(self, name: str) -> None:
        self._name_label.setText(name)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        edit_action = QAction("Edit Project", self)
        edit_action.triggered.connect(self.edit_requested)
        menu.addAction(edit_action)

        delete_action = QAction("Delete Project", self)
        delete_action.triggered.connect(self.delete_requested)
        menu.addAction(delete_action)

        menu.exec(QCursor.pos())


# ── ProjectSection ────────────────────────────────────────────────────────────

class ProjectSection(QWidget):
    """
    Collapsible section for a single project.

    Contains a ProjectSectionHeader and a body of ConversationListItems.
    """

    conversation_selected = pyqtSignal(int)
    new_conversation_requested = pyqtSignal(int)   # project_id
    edit_requested = pyqtSignal(int)               # project_id
    delete_requested = pyqtSignal(int)             # project_id

    def __init__(self, project: Project, conversations: List[Conversation], parent=None):
        super().__init__(parent)
        self.project_id = project.id
        self._collapsed = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = ProjectSectionHeader(project)
        self._header.toggle_clicked.connect(self._toggle_collapsed)
        self._header.new_conversation_requested.connect(
            lambda: self.new_conversation_requested.emit(self.project_id)
        )
        self._header.edit_requested.connect(
            lambda: self.edit_requested.emit(self.project_id)
        )
        self._header.delete_requested.connect(
            lambda: self.delete_requested.emit(self.project_id)
        )
        outer.addWidget(self._header)

        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(12, 0, 0, 0)
        body_layout.setSpacing(0)

        for conv in conversations:
            item = ConversationListItem(conv)
            item.clicked.connect(self.conversation_selected)
            body_layout.addWidget(item)

        if not conversations:
            empty = QLabel("No conversations yet")
            empty.setStyleSheet("color: #888; font-size: 11px; padding: 4px 10px;")
            body_layout.addWidget(empty)

        body_layout.addStretch()
        outer.addWidget(self._body)
        self._body.setVisible(False)

    def _toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        self._header.set_collapsed(self._collapsed)
        self._body.setVisible(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._header.set_collapsed(collapsed)
        self._body.setVisible(not collapsed)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed


# ── Sidebar ───────────────────────────────────────────────────────────────────

class Sidebar(QWidget):
    """
    Sidebar widget showing projects (collapsible) and unassigned conversations.
    """

    new_conversation_requested = pyqtSignal()
    conversation_selected = pyqtSignal(int)
    export_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    new_project_requested = pyqtSignal()
    new_conversation_in_project_requested = pyqtSignal(int)
    edit_project_requested = pyqtSignal(int)
    delete_project_requested = pyqtSignal(int)

    def __init__(self, database: Database, parent=None):
        super().__init__(parent)
        self.database = database
        self._collapsed_projects: Dict[int, bool] = {}  # project_id → collapsed state
        self._context_menu_conversation_id: Optional[int] = None

        self.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # "New Conversation" button
        self.new_button = QPushButton(
            locales.get_string("sidebar.new_conversation", "+ New Conversation")
        )
        self.new_button.setMinimumHeight(36)
        self.new_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 6px;
                margin: 5px 5px 2px 5px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:pressed { background-color: #3d8b40; }
        """)
        self.new_button.clicked.connect(self.new_conversation_requested)
        layout.addWidget(self.new_button)

        # "New Project" button
        self.new_project_button = QPushButton("+ New Project")
        self.new_project_button.setMinimumHeight(30)
        self.new_project_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #4CAF50;
                border: 1px solid #4CAF50;
                border-radius: 4px;
                font-weight: bold;
                padding: 4px;
                margin: 2px 5px 4px 5px;
            }
            QPushButton:hover { background-color: rgba(76, 175, 80, 0.1); }
            QPushButton:pressed { background-color: rgba(76, 175, 80, 0.2); }
        """)
        self.new_project_button.clicked.connect(self.new_project_requested)
        layout.addWidget(self.new_project_button)

        # Scroll area containing everything
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("QScrollArea { border: none; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 4, 0, 4)
        self._content_layout.setSpacing(0)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scroll_area.setWidget(self._content_widget)
        layout.addWidget(self._scroll_area)

        # Enable right-click context menu on unassigned conversations
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.refresh()

    # ── refresh alias (fixes latent bug where _finalize_response called this) ──
    def refresh_conversations(self):
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the entire sidebar content from database."""
        # Save collapsed state before clearing
        for widget in self._content_widget.findChildren(ProjectSection):
            self._collapsed_projects[widget.project_id] = widget.is_collapsed

        # Clear content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Load projects and their conversations
        projects = self.database.list_projects()
        for project in projects:
            convs = self.database.get_project_conversations(project.id)
            section = ProjectSection(project, convs)

            # Restore collapsed state (default: collapsed)
            was_collapsed = self._collapsed_projects.get(project.id, True)
            section.set_collapsed(was_collapsed)

            section.conversation_selected.connect(self._on_conversation_selected)
            section.new_conversation_requested.connect(
                self.new_conversation_in_project_requested
            )
            section.edit_requested.connect(self.edit_project_requested)
            section.delete_requested.connect(self._on_delete_project_requested)
            self._content_layout.addWidget(section)

        # Separator between projects and unassigned conversations
        unassigned = self.database.list_unassigned_conversations()
        all_convs = self.database.list_conversations()

        if projects and (unassigned or not all_convs):
            sep = QLabel("─── Other conversations ───")
            sep.setStyleSheet(
                "font-size: 10px; color: #888; padding: 6px 8px 2px 8px; "
                "letter-spacing: 0.3px;"
            )
            sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._content_layout.addWidget(sep)

        # Date-grouped unassigned conversations
        if unassigned:
            grouped = self._group_by_date(unassigned)
            for group_name in ["today", "yesterday", "last_7_days", "last_30_days", "older"]:
                if group_name in grouped and grouped[group_name]:
                    header_text = locales.get_string(
                        f"sidebar.{group_name}",
                        group_name.replace("_", " ").title()
                    )
                    header = QLabel(header_text)
                    header.setStyleSheet("""
                        font-size: 11px; font-weight: bold; color: #888888;
                        padding: 8px 10px 4px 10px; letter-spacing: 0.5px;
                    """)
                    self._content_layout.addWidget(header)

                    for conv in grouped[group_name]:
                        item = ConversationListItem(conv)
                        item.clicked.connect(self._on_conversation_selected)
                        self._content_layout.addWidget(item)
        elif not projects:
            # No projects and no unassigned → show empty state
            empty_label = QLabel(
                locales.get_string("sidebar.no_conversations", "No conversations yet")
            )
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #888; padding: 20px;")
            self._content_layout.addWidget(empty_label)

        self._content_layout.addStretch()

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_conversation_selected(self, conversation_id: int) -> None:
        logger.info(f"Conversation {conversation_id} selected")
        self.conversation_selected.emit(conversation_id)

    def _on_delete_project_requested(self, project_id: int) -> None:
        """Confirm deletion before emitting signal."""
        reply = QMessageBox.question(
            self,
            "Delete Project?",
            "Delete this project? Conversations will be kept but unassigned.\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_project_requested.emit(project_id)

    def _show_context_menu(self, position) -> None:
        """Show right-click context menu for unassigned ConversationListItems."""
        widget = self.childAt(position)
        while widget and not isinstance(widget, ConversationListItem):
            widget = widget.parent()

        if not isinstance(widget, ConversationListItem):
            return

        # Only unassigned conversations are handled here; project conversations
        # are inside ProjectSection and context menus are not wired there
        self._context_menu_conversation_id = widget.conversation_id

        menu = QMenu(self)

        export_action = QAction(
            locales.get_string("sidebar.export_as_txt", "Export as TXT"), self
        )
        export_action.triggered.connect(self._on_export_conversation)
        menu.addAction(export_action)

        delete_action = QAction(
            locales.get_string("sidebar.delete", "Delete"), self
        )
        delete_action.triggered.connect(self._on_delete_conversation)
        menu.addAction(delete_action)

        menu.exec(QCursor.pos())

    def _on_export_conversation(self) -> None:
        if self._context_menu_conversation_id is None:
            return
        logger.info(f"Export requested for conversation {self._context_menu_conversation_id}")
        self.export_requested.emit(self._context_menu_conversation_id)

    def _on_delete_conversation(self) -> None:
        if self._context_menu_conversation_id is None:
            return

        reply = QMessageBox.question(
            self,
            locales.get_string("sidebar.delete_conversation", "Delete Conversation?"),
            locales.get_string("sidebar.cannot_undo", "This cannot be undone."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"Delete confirmed for conversation {self._context_menu_conversation_id}")
            self.delete_requested.emit(self._context_menu_conversation_id)
            self._context_menu_conversation_id = None

    # ── helpers ───────────────────────────────────────────────────────────────

    def _group_by_date(self, conversations: List[Conversation]) -> dict:
        now = datetime.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)

        groups: dict = {
            "today": [], "yesterday": [], "last_7_days": [],
            "last_30_days": [], "older": []
        }

        for conv in conversations:
            try:
                dt = datetime.fromisoformat(conv.updated_at)
                conv_date = dt.date()
                if conv_date == today:
                    groups["today"].append(conv)
                elif conv_date == yesterday:
                    groups["yesterday"].append(conv)
                elif conv_date > seven_days_ago:
                    groups["last_7_days"].append(conv)
                elif conv_date > thirty_days_ago:
                    groups["last_30_days"].append(conv)
                else:
                    groups["older"].append(conv)
            except Exception as e:
                logger.warning(f"Failed to parse date for conversation {conv.id}: {e}")
                groups["older"].append(conv)

        return groups
