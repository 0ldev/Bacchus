"""
Conversation mixin for MainWindow.

Extracted from main_window.py. Contains conversation CRUD handlers.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ConversationMixin:
    """
    Mixin providing conversation management methods for MainWindow.

    Requires self to have:
        - self.database (Database)
        - self.sidebar (Sidebar)
        - self.chat_widget (ChatWidget)
        - self.prompt_area (PromptArea)
        - self._current_conversation_id (Optional[int])
    """

    def _on_new_conversation(self, project_id: Optional[int] = None) -> None:
        """Handle New Conversation action.

        Args:
            project_id: If provided, assign the new conversation to this project.
        """
        from PyQt6.QtWidgets import QMessageBox

        if not self.model_manager or not self.model_manager.is_chat_model_loaded():
            QMessageBox.warning(
                self,
                "Model Not Loaded",
                "Please load a chat model from Settings > Models before creating a conversation."
            )
            return

        logger.info("New conversation requested")

        title = "New Conversation"
        conv_id = self.database.create_conversation(title=title)

        if project_id is not None:
            self.database.assign_conversation_to_project(conv_id, project_id)
            logger.info(f"Assigned new conversation {conv_id} to project {project_id}")

        self.sidebar.refresh()

        self._current_conversation_id = conv_id
        self.chat_widget.load_conversation(conv_id)
        self.prompt_area.set_enabled(True)
        self.prompt_area.focus_input()

        logger.info(f"Created new conversation {conv_id}")

    def _on_conversation_selected(self, conversation_id: int):
        """Handle conversation selection from sidebar."""
        logger.info(f"Loading conversation {conversation_id}")
        self._current_conversation_id = conversation_id
        self.chat_widget.load_conversation(conversation_id)
        self.prompt_area.set_enabled(True)
        self.prompt_area.focus_input()

    def _on_export_conversation(self) -> None:
        """Handle Export Current action from menu."""
        if self._current_conversation_id is None:
            logger.warning("No conversation selected for export")
            return
        self._on_export_conversation_by_id(self._current_conversation_id)

    def _on_export_conversation_by_id(self, conversation_id: int):
        """Handle export conversation by ID (from context menu)."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from bacchus import locales

        conversation = self.database.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversation {conversation_id} not found")
            return

        default_filename = f"conversation_{conversation_id}.txt"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            locales.get_string("menu.export_current", "Export Conversation"),
            default_filename,
            "Text Files (*.txt)"
        )

        if not filepath:
            return

        try:
            messages = self.database.get_conversation_messages(conversation_id)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {conversation.title}\n")
                f.write(f"# Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                for msg in messages:
                    f.write(f"[{msg.role.upper()}] {msg.created_at}\n")
                    f.write(f"{msg.content}\n\n")

            logger.info(f"Exported conversation {conversation_id} to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export conversation: {e}")
            QMessageBox.critical(
                self,
                locales.get_string("error.generic", "Error"),
                f"Failed to export conversation: {str(e)}"
            )

    def _on_delete_conversation(self, conversation_id: int):
        """Handle delete conversation action."""
        logger.info(f"Deleting conversation {conversation_id}")

        try:
            self.database.delete_conversation(conversation_id)
            self.sidebar.refresh()

            if self._current_conversation_id == conversation_id:
                self._current_conversation_id = None
                self.chat_widget.clear()
                self.prompt_area.set_enabled(False)

            logger.info(f"Deleted conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")
