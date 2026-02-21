"""
Sidebar widget for Bacchus.

Displays conversation history with date grouping and new conversation button.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QScrollArea,
    QLabel,
    QMenu,
    QMessageBox,
    QFileDialog,
)
from PyQt6.QtGui import QAction, QCursor

from bacchus import locales
from bacchus.constants import SIDEBAR_WIDTH, CONVERSATION_LIST_TITLE_LENGTH
from bacchus.database import Database, Conversation


logger = logging.getLogger(__name__)


class ConversationListItem(QWidget):
    """
    Single conversation item in the sidebar list.
    
    Displays title, timestamp, and optional document indicator.
    """
    
    clicked = pyqtSignal(int)  # Emits conversation_id
    
    def __init__(self, conversation: Conversation, parent=None):
        """
        Initialize conversation list item.
        
        Args:
            conversation: Conversation object from database
            parent: Parent widget
        """
        super().__init__(parent)
        self.conversation_id = conversation.id
        self.has_document = conversation.document_path is not None
        
        # Truncate title to 30 characters
        title = conversation.title
        if len(title) > CONVERSATION_LIST_TITLE_LENGTH:
            title = title[:CONVERSATION_LIST_TITLE_LENGTH] + "..."
        
        # Format timestamp
        timestamp = self._format_timestamp(conversation.updated_at)
        
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(2)
        
        # Title with optional document icon — no inline color so theme QLabel rule applies
        title_text = f"📎 {title}" if self.has_document else title
        self.title_label = QLabel(title_text)
        self.title_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(self.title_label)

        # Timestamp — neutral mid-gray readable on both light and dark backgrounds
        self.time_label = QLabel(timestamp)
        self.time_label.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(self.time_label)

        self.setLayout(layout)

        # Only set structural styles here; colours come from theme.py rules
        # (ConversationListItem and ConversationListItem:hover)
        self.setStyleSheet("""
            ConversationListItem {
                border-radius: 6px;
                border-bottom: 1px solid rgba(128, 128, 128, 0.12);
                margin: 1px 2px;
            }
        """)
        
        # Enable mouse tracking for hover
        self.setMouseTracking(True)
    
    def _format_timestamp(self, updated_at: str) -> str:
        """
        Format timestamp for display.
        
        Args:
            updated_at: ISO format timestamp string
            
        Returns:
            Formatted timestamp string
        """
        try:
            dt = datetime.fromisoformat(updated_at)
            now = datetime.now()
            
            # If today, show time only (HH:MM)
            if dt.date() == now.date():
                return dt.strftime("%H:%M")
            else:
                # Otherwise show date (MMM DD)
                return dt.strftime("%b %d")
        except Exception:
            return ""
    
    def mousePressEvent(self, event):
        """Handle mouse click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.conversation_id)


class ConversationList(QWidget):
    """
    Scrollable list of conversations grouped by date.
    """
    
    conversation_selected = pyqtSignal(int)  # Emits conversation_id
    
    def __init__(self, database: Database, parent=None):
        """
        Initialize conversation list.
        
        Args:
            database: Database instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.database = database
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        # Container for conversation items
        self.container = QWidget()
        self.container_layout = QVBoxLayout()
        self.container_layout.setContentsMargins(5, 5, 5, 5)
        self.container_layout.setSpacing(2)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container.setLayout(self.container_layout)
        
        scroll_area.setWidget(self.container)
        main_layout.addWidget(scroll_area)
        
        self.setLayout(main_layout)
        
        # Load conversations
        self.refresh()
    
    def refresh(self):
        """Reload conversation list from database."""
        # Clear existing items
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Get conversations from database
        conversations = self.database.list_conversations()
        
        if not conversations:
            # Show empty state
            empty_label = QLabel(locales.get_string("sidebar.no_conversations", 
                                                    "No conversations yet"))
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #888; padding: 20px;")
            self.container_layout.addWidget(empty_label)
            return
        
        # Group conversations by date
        grouped = self._group_by_date(conversations)
        
        # Add groups in order
        for group_name in ["today", "yesterday", "last_7_days", "last_30_days", "older"]:
            if group_name in grouped and grouped[group_name]:
                # Add group header
                header_text = locales.get_string(f"sidebar.{group_name}", 
                                                 group_name.replace("_", " ").title())
                header = QLabel(header_text)
                header.setStyleSheet("""
                    font-size: 11px;
                    font-weight: bold;
                    color: #888888;
                    padding: 8px 10px 4px 10px;
                    letter-spacing: 0.5px;
                """)
                self.container_layout.addWidget(header)
                
                # Add conversation items
                for conv in grouped[group_name]:
                    item = ConversationListItem(conv)
                    item.clicked.connect(self._on_conversation_clicked)
                    self.container_layout.addWidget(item)
    
    def _group_by_date(self, conversations: List[Conversation]) -> dict:
        """
        Group conversations by date categories.
        
        Args:
            conversations: List of Conversation objects
            
        Returns:
            Dictionary with date category keys and conversation lists
        """
        now = datetime.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)
        
        groups = {
            "today": [],
            "yesterday": [],
            "last_7_days": [],
            "last_30_days": [],
            "older": []
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
    
    def _on_conversation_clicked(self, conversation_id: int):
        """Handle conversation click."""
        self.conversation_selected.emit(conversation_id)


class Sidebar(QWidget):
    """
    Sidebar widget with new conversation button and conversation list.
    """
    
    new_conversation_requested = pyqtSignal()
    conversation_selected = pyqtSignal(int)  # Emits conversation_id
    export_requested = pyqtSignal(int)  # Emits conversation_id
    delete_requested = pyqtSignal(int)  # Emits conversation_id
    
    def __init__(self, database: Database, parent=None):
        """
        Initialize sidebar.
        
        Args:
            database: Database instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.database = database
        
        # Set fixed width; border-right colour comes from theme.py (Sidebar rule)
        self.setFixedWidth(SIDEBAR_WIDTH)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # New conversation button
        self.new_button = QPushButton(
            locales.get_string("sidebar.new_conversation", "+ New Conversation")
        )
        self.new_button.setMinimumHeight(40)
        self.new_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 8px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.new_button.clicked.connect(self._on_new_conversation)
        layout.addWidget(self.new_button)
        
        # Conversation list
        self.conversation_list = ConversationList(database)
        self.conversation_list.conversation_selected.connect(self._on_conversation_selected)
        layout.addWidget(self.conversation_list)
        
        self.setLayout(layout)
        
        # Enable context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Track last right-clicked conversation
        self._context_menu_conversation_id: Optional[int] = None
    
    def _on_new_conversation(self):
        """Handle new conversation button click."""
        logger.info("New conversation requested from sidebar")
        self.new_conversation_requested.emit()
    
    def _on_conversation_selected(self, conversation_id: int):
        """Handle conversation selection."""
        logger.info(f"Conversation {conversation_id} selected")
        self.conversation_selected.emit(conversation_id)
    
    def _show_context_menu(self, position):
        """Show context menu for conversation item."""
        # Find which conversation item was right-clicked
        widget = self.childAt(position)
        
        # Traverse up to find ConversationListItem
        while widget and not isinstance(widget, ConversationListItem):
            widget = widget.parent()
        
        if not isinstance(widget, ConversationListItem):
            return
        
        self._context_menu_conversation_id = widget.conversation_id
        
        # Create context menu
        menu = QMenu(self)
        
        # Export action
        export_action = QAction(
            locales.get_string("sidebar.export_as_txt", "Export as TXT"),
            self
        )
        export_action.triggered.connect(self._on_export_conversation)
        menu.addAction(export_action)
        
        # Delete action
        delete_action = QAction(
            locales.get_string("sidebar.delete", "Delete"),
            self
        )
        delete_action.triggered.connect(self._on_delete_conversation)
        menu.addAction(delete_action)
        
        # Show menu at cursor position
        menu.exec(QCursor.pos())
    
    def _on_export_conversation(self):
        """Handle export conversation action."""
        if self._context_menu_conversation_id is None:
            return
        
        logger.info(f"Export requested for conversation {self._context_menu_conversation_id}")
        self.export_requested.emit(self._context_menu_conversation_id)
    
    def _on_delete_conversation(self):
        """Handle delete conversation action."""
        if self._context_menu_conversation_id is None:
            return
        
        # Show confirmation dialog
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
    
    def refresh(self):
        """Refresh the conversation list."""
        self.conversation_list.refresh()
