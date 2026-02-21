"""
Chat widget for Bacchus.

Displays conversation messages in a scrollable area with markdown rendering.
"""

import json
import logging
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QFrame,
    QApplication,
    QMenu,
)
from PyQt6.QtGui import QFont, QAction, QPixmap

from bacchus import locales
from bacchus.database import Database, Message
from bacchus.ui.tool_result_widget import ToolResultWidget


logger = logging.getLogger(__name__)


# Per-theme bubble colour palettes
_BUBBLE_COLORS = {
    "light": {
        "user":      {"bg": "#dbeafe", "text": "#1e3a5f", "meta": "#5a85c0"},
        "assistant": {"bg": "#f3f4f6", "text": "#111827", "meta": "#6b7280"},
        "tool":      {"bg": "#f0fdf4", "text": "#14532d", "meta": "#22863a"},
        "system":    {"bg": "#f8fafc", "text": "#475569", "meta": "#94a3b8"},
    },
    "dark": {
        "user":      {"bg": "#1a3a5e", "text": "#cce5ff", "meta": "#7ab3e8"},
        "assistant": {"bg": "#252525", "text": "#e0e0e0", "meta": "#888888"},
        "tool":      {"bg": "#162616", "text": "#b8e0b8", "meta": "#6aaf6a"},
        "system":    {"bg": "#1e1e2a", "text": "#8090a0", "meta": "#606878"},
    },
}


class MessageWidget(QFrame):
    """
    Widget representing a single message in the chat.

    User messages are styled with a blue bubble; assistant with neutral.
    """

    edit_requested = pyqtSignal(int)       # Emits message_id
    regenerate_requested = pyqtSignal(int)  # Emits message_id

    def __init__(
        self,
        message: Message,
        is_last_user_message: bool = False,
        theme: str = "light",
        parent=None,
    ):
        """
        Initialize message widget.

        Args:
            message: Message object from database
            is_last_user_message: True if this is the last user message
            theme: Current theme name ("light" or "dark")
            parent: Parent widget
        """
        super().__init__(parent)
        self.message = message
        self.is_last_user_message = is_last_user_message

        # No native frame border — we draw our own rounded bubble
        self.setFrameShape(QFrame.Shape.NoFrame)

        # Pick colour palette
        palette = _BUBBLE_COLORS.get(theme, _BUBBLE_COLORS["light"])
        role_key = message.role if message.role in palette else "assistant"
        colors = palette[role_key]
        bg, text_color, meta_color = colors["bg"], colors["text"], colors["meta"]

        self.setStyleSheet(f"""
            MessageWidget {{
                background-color: {bg};
                border-radius: 14px;
            }}
        """)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # ── Header: role icon + timestamp on one line ──────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(0)

        role_label = QLabel(self._get_role_label(message.role))
        role_label.setStyleSheet(
            f"color: {meta_color}; font-size: 11px; font-weight: 600;"
            " background: transparent;"
        )
        header_row.addWidget(role_label)
        header_row.addStretch()

        timestamp = self._format_timestamp(message.created_at)
        if timestamp:
            time_label = QLabel(timestamp)
            time_label.setStyleSheet(
                f"color: {meta_color}; font-size: 10px; background: transparent;"
            )
            header_row.addWidget(time_label)

        layout.addLayout(header_row)

        # ── Image thumbnail (VLM user messages) ─────────────────────────────
        if message.role == "user" and getattr(message, "image_path", None):
            from pathlib import Path as _Path
            img_path = message.image_path
            if _Path(img_path).exists():
                pixmap = QPixmap(img_path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaledToWidth(
                        280, Qt.TransformationMode.SmoothTransformation
                    )
                    img_label = QLabel()
                    img_label.setPixmap(pixmap)
                    img_label.setStyleSheet(
                        "border-radius: 6px; background: transparent;"
                    )
                    img_label.setToolTip(str(_Path(img_path).name))
                    layout.addWidget(img_label)

        # ── Text content ───────────────────────────────────────────────────
        # Skip plain content for messages where mcp_calls provides richer display:
        _hide_content = bool(message.mcp_calls) and message.role in ("system", "assistant")
        if message.content and not _hide_content:
            content_label = QLabel(message.content)
            content_label.setWordWrap(True)
            content_label.setTextFormat(Qt.TextFormat.PlainText)
            content_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            content_label.setStyleSheet(
                f"color: {text_color}; background: transparent; padding: 0;"
            )
            layout.addWidget(content_label)

        # ── Tool calls / results ───────────────────────────────────────────
        if message.mcp_calls:
            try:
                calls = (
                    json.loads(message.mcp_calls)
                    if isinstance(message.mcp_calls, str)
                    else message.mcp_calls
                )
                if not isinstance(calls, list):
                    calls = [calls]

                for call in calls:
                    if message.role in ("tool", "system"):
                        # Slash-command results (role=tool) and autonomous tool results
                        # (role=system) both render as ToolResultWidget
                        tool_widget = ToolResultWidget(
                            tool_name=call.get("tool", "unknown"),
                            arguments=call.get("params", {}),
                            result=call.get("result", ""),
                            success=call.get("success", True),
                            duration_ms=call.get("duration_ms"),
                            theme=theme,
                        )
                        layout.addWidget(tool_widget)
                    else:
                        # Collapsible tool-call request
                        call_frame = QFrame()
                        call_frame.setStyleSheet("""
                            QFrame {
                                background-color: rgba(251,192,45,0.15);
                                border: 1px dashed #FBC02D;
                                border-radius: 6px;
                                padding: 4px;
                                margin-top: 4px;
                            }
                        """)
                        call_layout = QVBoxLayout(call_frame)
                        call_layout.setSpacing(3)

                        header_inner = QFrame()
                        header_inner.setStyleSheet(
                            "QFrame { border: none; background: transparent; }"
                        )
                        hi_layout = QHBoxLayout(header_inner)
                        hi_layout.setContentsMargins(0, 0, 0, 0)
                        hi_layout.setSpacing(4)

                        toggle_lbl = QLabel("▶")
                        toggle_lbl.setStyleSheet(
                            "color: #F57F17; font-size: 10px; background: transparent;"
                        )
                        hi_layout.addWidget(toggle_lbl)

                        call_text = locales.get_string("chat.calling_tool", "Calling Tool:")
                        call_label = QLabel(
                            f"<b>{call_text}</b> {call.get('tool', 'unknown')}"
                        )
                        call_label.setStyleSheet(
                            "color: #F57F17; background: transparent;"
                        )
                        hi_layout.addWidget(call_label)
                        hi_layout.addStretch()
                        call_layout.addWidget(header_inner)

                        params = call.get("params", {})
                        params_widget = None
                        if params:
                            params_str = json.dumps(params, indent=2)
                            params_label = QLabel(f"<code>{params_str}</code>")
                            params_label.setStyleSheet(
                                "font-size: 10px; color: #616161; background: transparent;"
                            )
                            params_label.setWordWrap(True)
                            params_label.setVisible(False)
                            call_layout.addWidget(params_label)
                            params_widget = params_label

                        def _make_toggle(tgl, pw):
                            def _toggle(_event):
                                if pw is None:
                                    return
                                visible = pw.isVisible()
                                pw.setVisible(not visible)
                                tgl.setText("▼" if not visible else "▶")
                            return _toggle

                        header_inner.mousePressEvent = _make_toggle(toggle_lbl, params_widget)
                        if params_widget:
                            from PyQt6.QtGui import QCursor
                            header_inner.setCursor(
                                QCursor(Qt.CursorShape.PointingHandCursor)
                            )

                        layout.addWidget(call_frame)

            except Exception as e:
                logger.error(f"Failed to render tool calls: {e}")
                if not message.content:
                    error_label = QLabel(f"Error rendering tool info: {e}")
                    layout.addWidget(error_label)

        self.setLayout(layout)

    def _get_role_label(self, role: str) -> str:
        """Get display label for message role."""
        if role == "user":
            return f"👤 {locales.get_string('chat.you', 'You')}"
        elif role == "tool":
            return f"🛠️ {locales.get_string('chat.tool', 'Tool')}"
        elif role == "system":
            return "⚙️ System"
        else:
            return "🤖 Assistant"

    def get_text_content(self) -> str:
        """Get the text content of this message for copying."""
        role = self.message.role.upper()
        content = self.message.content or ""

        tool_info = ""
        if self.message.mcp_calls:
            try:
                calls = (
                    json.loads(self.message.mcp_calls)
                    if isinstance(self.message.mcp_calls, str)
                    else self.message.mcp_calls
                )
                if not isinstance(calls, list):
                    calls = [calls]
                for call in calls:
                    tool_name = call.get("tool", "unknown")
                    if self.message.role == "tool":
                        result = call.get("result", "")
                        tool_info += f"\n[TOOL RESULT: {tool_name}]\n{result}\n"
                    else:
                        params = json.dumps(call.get("params", {}))
                        tool_info += f"\n[TOOL CALL: {tool_name}({params})]\n"
            except Exception:
                pass

        return f"[{role}] {content}{tool_info}\n"

    def _format_timestamp(self, created_at: str) -> str:
        """Format timestamp for display (HH:MM)."""
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(created_at)
            return dt.strftime("%H:%M")
        except Exception:
            return ""


class ChatWidget(QWidget):
    """
    Chat area widget displaying conversation messages.

    Scrollable list of messages with auto-scroll to bottom.
    User messages are right-aligned; assistant/tool messages are left-aligned.
    """

    def __init__(self, database: Database, parent=None):
        """
        Initialize chat widget.

        Args:
            database: Database instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.database = database
        self._current_conversation_id: Optional[int] = None
        self._should_auto_scroll = True

        # Load theme once at construction; restart required for theme change
        from bacchus.config import load_settings
        self._theme = load_settings().get("theme", "light")

        # Keep references for copy-all
        self._message_widgets: List[MessageWidget] = []

        # Make widget focusable to receive Ctrl+A
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area — no inline background so theme stylesheet applies
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")

        # Container for messages
        self.container = QWidget()
        self.container_layout = QVBoxLayout()
        self.container_layout.setContentsMargins(12, 12, 12, 12)
        self.container_layout.setSpacing(6)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container.setLayout(self.container_layout)

        self.scroll_area.setWidget(self.container)

        # Connect scroll bar
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.rangeChanged.connect(self._on_scroll_range_changed)
        scrollbar.valueChanged.connect(self._on_scroll_value_changed)

        main_layout.addWidget(self.scroll_area)
        self.setLayout(main_layout)

        # Show empty state initially
        self._show_empty_state()

    def keyPressEvent(self, event):
        """Handle key press events for the chat widget."""
        if (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_A
        ):
            self._copy_all_messages()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu for the chat widget."""
        context_menu = QMenu(self)
        copy_all_action = QAction("Copy All Messages", self)
        copy_all_action.triggered.connect(self._copy_all_messages)
        context_menu.addAction(copy_all_action)
        context_menu.exec(event.globalPos())

    def _copy_all_messages(self):
        """Copy all messages in the current conversation to clipboard."""
        all_text = "\n".join(w.get_text_content() for w in self._message_widgets)
        if all_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(all_text.strip())
            logger.info("All messages copied to clipboard")

    def _show_empty_state(self):
        """Show empty state when no conversation is selected."""
        self._clear_messages()

        empty_label = QLabel(
            locales.get_string(
                "chat.no_conversation",
                "Select a conversation or create a new one",
            )
        )
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("font-size: 14px; color: #999; padding: 40px;")
        self.container_layout.addWidget(empty_label)

    def _clear_messages(self):
        """Remove all message widgets from the container."""
        self._message_widgets = []
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_message_widget(self, message: Message, is_last_user: bool = False):
        """
        Create a MessageWidget, wrap it for L/R alignment, and add to layout.

        User messages are pushed to the right (75 % width), others to the left.
        """
        msg_widget = MessageWidget(
            message,
            is_last_user_message=is_last_user,
            theme=self._theme,
        )
        self._message_widgets.append(msg_widget)

        # Wrapper handles alignment via stretch
        wrapper = QWidget()
        h_layout = QHBoxLayout(wrapper)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        if message.role == "user":
            # Right-aligned: spacer on left
            h_layout.addStretch(1)
            h_layout.addWidget(msg_widget, 3)
        else:
            # Left-aligned: spacer on right
            h_layout.addWidget(msg_widget, 3)
            h_layout.addStretch(1)

        self.container_layout.addWidget(wrapper)

    def load_conversation(self, conversation_id: int):
        """
        Load and display messages for a conversation.

        Args:
            conversation_id: ID of conversation to load
        """
        logger.info(f"Loading conversation {conversation_id} into chat widget")

        self._current_conversation_id = conversation_id
        self._clear_messages()

        messages = self.database.get_conversation_messages(conversation_id)

        if not messages:
            no_messages_label = QLabel(
                locales.get_string("chat.no_messages", "No messages yet. Start typing below!")
            )
            no_messages_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_messages_label.setStyleSheet(
                "font-size: 14px; color: #999; padding: 40px;"
            )
            self.container_layout.addWidget(no_messages_label)
            return

        # Find last user message index
        last_user_index = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == "user":
                last_user_index = i
                break

        for i, message in enumerate(messages):
            self._add_message_widget(message, is_last_user=(i == last_user_index))

        self._should_auto_scroll = True
        QTimer.singleShot(100, self._scroll_to_bottom)

        logger.info(f"Loaded {len(messages)} messages")

    def add_message(self, message: Message):
        """
        Add a new message to the chat display.

        Args:
            message: Message object to add
        """
        # Remove "no messages" placeholder if present
        if self.container_layout.count() == 1:
            widget = self.container_layout.itemAt(0).widget()
            if isinstance(widget, QLabel):
                widget.deleteLater()
                self.container_layout.removeWidget(widget)

        is_last_user = (message.role == "user")
        self._add_message_widget(message, is_last_user)

        if self._should_auto_scroll:
            QTimer.singleShot(100, self._scroll_to_bottom)

    def clear(self):
        """Clear all messages and show empty state."""
        self._current_conversation_id = None
        self._show_empty_state()

    def _scroll_to_bottom(self):
        """Scroll to the bottom of the message list."""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_scroll_range_changed(self, min_val: int, max_val: int):
        """Handle scroll range change (e.g., when messages are added)."""
        if self._should_auto_scroll:
            scrollbar = self.scroll_area.verticalScrollBar()
            scrollbar.setValue(max_val)

    def _on_scroll_value_changed(self, value: int):
        """Handle manual scrolling by user."""
        scrollbar = self.scroll_area.verticalScrollBar()
        if value < scrollbar.maximum() - 10:
            self._should_auto_scroll = False
        else:
            self._should_auto_scroll = True
