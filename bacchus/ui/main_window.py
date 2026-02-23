"""
Main window for Bacchus application.

Central UI component containing menu bar, sidebar, chat area, and status bar.
Split into mixins for maintainability:
  - InferenceMixin  (_inference_mixin.py)
  - RAGMixin        (_rag_mixin.py)
  - ConversationMixin (_conversation_mixin.py)
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QMainWindow,
    QWidget,
)

from bacchus import locales
from bacchus.config import load_settings, save_settings
from bacchus.ui._inference_mixin import InferenceMixin
from bacchus.ui._rag_mixin import RAGMixin
from bacchus.ui._conversation_mixin import ConversationMixin


logger = logging.getLogger(__name__)


class MainWindow(InferenceMixin, RAGMixin, ConversationMixin, QMainWindow):
    """
    Main application window for Bacchus.

    Contains:
    - Menu bar (File, Help)
    - Sidebar with project sections and conversation history
    - Chat area with message display
    - Prompt input area
    - Status bar
    """

    def __init__(self, model_manager=None, mcp_manager=None):
        """
        Initialize the main window.

        Args:
            model_manager: ModelManager instance (optional)
            mcp_manager: MCPManager instance (optional)
        """
        super().__init__()

        # Store managers
        self.model_manager = model_manager
        self.mcp_manager = mcp_manager

        # Load settings
        self._settings = load_settings()

        # Initialize database
        from bacchus.config import get_conversations_dir
        from bacchus.database import Database

        db_path = get_conversations_dir() / "bacchus.db"
        self.database = Database(str(db_path))

        # Set window properties
        self.setWindowTitle(locales.get_string("app.name", "Bacchus"))
        self.setMinimumWidth(900)

        # Restore window state from settings
        self._restore_window_state()

        # Create UI components
        self._create_menu_bar()
        self._create_status_bar()
        self._create_central_widget()

        # Track current conversation
        self._current_conversation_id: Optional[int] = None

        # Track inference state
        self._inference_worker: Optional['InferenceWorker'] = None
        self._current_response: str = ""
        self._inference_conversation_id: Optional[int] = None
        self._tool_iteration_count: int = 0
        self._max_tool_iterations: int = 5
        self._seen_tool_calls: set = set()
        self._in_response_phase: bool = False
        self._in_argument_phase: bool = False
        self._pending_tool_name: str = ""

        # Update UI based on model state
        if model_manager:
            current_model = model_manager.get_current_chat_model()
            if current_model:
                display_name = model_manager.get_model_display_name(current_model)
                device = model_manager.get_active_device()
                self.status_bar_widget.set_model(display_name, device)
                self.prompt_area.set_model_loaded(True)
                self.prompt_area.set_vlm_mode(model_manager.is_vl_pipeline_loaded())
            else:
                self.status_bar_widget.set_model(None)
                self.prompt_area.set_model_loaded(False)
                self.prompt_area.set_vlm_mode(False)

        # Track document processing worker
        self._doc_process_worker = None

        # Track settings dialog to prevent multiple instances
        self._settings_dialog = None
        self._model_is_loading: bool = False

        # Tools allowed for the rest of this session (cleared on restart)
        self._session_allowed_tools: set = set()

        # Update MCP status in status bar
        self._update_mcp_status()

        logger.info("Main window initialized")

    def _restore_window_state(self) -> None:
        """Restore window size, position, and maximized state from settings."""
        window_settings = self._settings.get("window", {})

        width = window_settings.get("width", 1280)
        height = window_settings.get("height", 800)
        x = window_settings.get("x", 100)
        y = window_settings.get("y", 100)
        maximized = window_settings.get("maximized", False)

        self.resize(width, height)
        self.move(x, y)

        if maximized:
            self.showMaximized()

    def _save_window_state(self) -> None:
        """Save window size, position, and maximized state to settings."""
        self._settings["window"] = {
            "width": self.width(),
            "height": self.height(),
            "x": self.x(),
            "y": self.y(),
            "maximized": self.isMaximized()
        }
        save_settings(self._settings)

    def _create_menu_bar(self) -> None:
        """Create the menu bar with File and Help menus."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu(locales.get_string("menu.file", "File"))

        new_action = file_menu.addAction(
            locales.get_string("menu.new_conversation", "New Conversation")
        )
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._on_new_conversation)

        export_action = file_menu.addAction(
            locales.get_string("menu.export_current", "Export Current")
        )
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._on_export_conversation)

        file_menu.addSeparator()

        settings_action = file_menu.addAction(
            locales.get_string("menu.settings", "Settings")
        )
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._on_open_settings)

        file_menu.addSeparator()

        exit_action = file_menu.addAction(
            locales.get_string("menu.exit", "Exit")
        )
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)

        help_menu = menubar.addMenu(locales.get_string("menu.help", "Help"))

        data_folder_action = help_menu.addAction(
            locales.get_string("menu.open_data_folder", "Open Data Folder")
        )
        data_folder_action.triggered.connect(self._on_open_data_folder)

        about_action = help_menu.addAction(
            locales.get_string("menu.about", "About Bacchus")
        )
        about_action.triggered.connect(self._on_show_about)

    def _create_central_widget(self) -> None:
        """Create the central widget with sidebar and chat area."""
        from bacchus.ui.sidebar import Sidebar
        from bacchus.ui.chat_widget import ChatWidget
        from bacchus.ui.prompt_area import PromptArea

        central = QWidget()
        central.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_widget = QWidget()
        top_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.sidebar = Sidebar(self.database)
        self.sidebar.new_conversation_requested.connect(self._on_new_conversation)
        self.sidebar.conversation_selected.connect(self._on_conversation_selected)
        self.sidebar.export_requested.connect(self._on_export_conversation_by_id)
        self.sidebar.delete_requested.connect(self._on_delete_conversation)
        self.sidebar.new_project_requested.connect(self._on_new_project)
        self.sidebar.edit_project_requested.connect(self._on_edit_project)
        self.sidebar.delete_project_requested.connect(self._on_delete_project)
        self.sidebar.new_conversation_in_project_requested.connect(self._on_new_conversation)
        top_layout.addWidget(self.sidebar)

        right_widget = QWidget()
        right_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.chat_widget = ChatWidget(self.database)
        right_layout.addWidget(self.chat_widget, 1)

        self.prompt_area = PromptArea()
        self.prompt_area.send_message_requested.connect(self._on_send_message)
        self.prompt_area.document_attached.connect(self._on_document_attached)
        self.prompt_area.document_removed.connect(self._on_document_removed)
        right_layout.addWidget(self.prompt_area, 0)

        right_widget.setLayout(right_layout)
        top_layout.addWidget(right_widget, 1)

        top_widget.setLayout(top_layout)
        main_layout.addWidget(top_widget, 1)

        main_layout.addWidget(self.status_bar_widget)

        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def _create_status_bar(self) -> None:
        """Create the status bar."""
        from bacchus.ui.status_bar import StatusBar

        self.setStatusBar(None)

        self.status_bar_widget = StatusBar()
        self.status_bar_widget.model_clicked.connect(self._on_status_bar_model_clicked)
        self.status_bar_widget.mcp_clicked.connect(self._on_status_bar_mcp_clicked)

        logger.info("Status bar created")

    def _on_send_message(self, text: str):
        """Handle send message from prompt area."""
        if self._current_conversation_id is None:
            logger.warning("Cannot send message: no conversation selected")
            return

        if text.startswith("/"):
            self._handle_slash_command(text)
            return

        if not self.model_manager or not self.model_manager.is_chat_model_loaded():
            logger.warning("Cannot send message: no model loaded")
            return

        if self._model_is_loading:
            self.prompt_area.restore_after_blocked_send(text)
            self.prompt_area.show_notice(
                "⏳ Model is still loading — please hold on. Your message has been kept."
            )
            return

        if self._inference_worker is not None and self._inference_worker.isRunning():
            logger.warning("Cannot send message: inference is already running")
            return

        logger.info(f"Sending message to conversation {self._current_conversation_id}")

        self._tool_iteration_count = 0
        self._seen_tool_calls = set()
        self._in_response_phase = False
        self._in_argument_phase = False
        self._pending_tool_name = ""

        image_path: Optional[str] = None
        raw_image = self.prompt_area.get_attached_image()
        if raw_image:
            import shutil
            import uuid
            from pathlib import Path as _Path
            from bacchus.constants import IMAGES_DIR
            conv_images_dir = IMAGES_DIR / str(self._current_conversation_id)
            conv_images_dir.mkdir(parents=True, exist_ok=True)
            src = _Path(raw_image)
            dest = conv_images_dir / f"{uuid.uuid4().hex}{src.suffix.lower()}"
            try:
                shutil.copy2(str(src), str(dest))
                image_path = str(dest)
                logger.info(f"Image copied to: {dest}")
            except Exception as e:
                logger.error(f"Failed to copy image: {e}")
            self.prompt_area.clear_attached_image()

        self.database.add_message(
            conversation_id=self._current_conversation_id,
            role="user",
            content=text,
            image_path=image_path
        )

        conversation = self.database.get_conversation(self._current_conversation_id)
        if conversation and conversation.title == "New Conversation":
            title = text[:100]
            self.database.update_conversation(
                conversation_id=self._current_conversation_id,
                title=title
            )
            self.sidebar.refresh()

        self.chat_widget.load_conversation(self._current_conversation_id)
        self.prompt_area.set_generating(True)
        self.status_bar_widget.set_active(True)

        self._start_inference(conversation)

    def _handle_slash_command(self, text: str):
        """Handle slash commands for MCP tool invocation."""
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        logger.info(f"Slash command: {command} args={args}")

        if command == "/help":
            help_text = (
                "Available commands:\n"
                "  /read <path>    - Read file contents\n"
                "  /list <path>    - List directory contents\n"
                "  /run <command>  - Execute shell command\n"
                "  /help           - Show this help"
            )
            self._add_tool_message(command="/help", result=help_text)
            return

        if not self.mcp_manager:
            self._add_tool_message(
                command=text,
                result="Error: MCP manager not available",
                success=False
            )
            return

        if command == "/read":
            self._execute_mcp_tool("filesystem", "read_file", {"path": args.strip()}, text)
        elif command == "/list":
            self._execute_mcp_tool("filesystem", "list_directory", {"path": args.strip()}, text)
        elif command == "/run":
            self._execute_mcp_tool("cmd", "execute_command", {"command": args.strip()}, text)
        else:
            self._add_tool_message(
                command=text,
                result=f"Unknown command: {command}\nType /help for available commands.",
                success=False
            )

    def _execute_mcp_tool(
        self, server_name: str, tool_name: str, arguments: dict, original_command: str
    ):
        """Execute an MCP tool and display the result."""
        client = self.mcp_manager.get_client(server_name)

        if not client:
            server = self.mcp_manager.get_server(server_name)
            if server and server.status == "error":
                error_msg = f"Server '{server_name}' is in error state: {server.error_message}"
            elif server and server.status == "stopped":
                error_msg = f"Server '{server_name}' is not running. Start it from Settings > MCP."
            else:
                error_msg = f"Server '{server_name}' is not available."
            self._add_tool_message(command=original_command, result=error_msg, success=False)
            return

        logger.info(f"Executing MCP tool: {server_name}.{tool_name} with {arguments}")

        try:
            call = client.call_tool(tool_name, arguments, timeout=30.0)

            if call.success:
                self._add_tool_message(
                    command=original_command,
                    result=call.result or "(no output)",
                    success=True,
                    mcp_call={
                        "server": server_name,
                        "tool": tool_name,
                        "params": arguments,
                        "result": call.result,
                        "duration_ms": call.duration_ms
                    }
                )
            else:
                self._add_tool_message(
                    command=original_command,
                    result=f"Error: {call.error}",
                    success=False
                )

        except Exception as e:
            logger.error(f"MCP tool execution failed: {e}")
            self._add_tool_message(
                command=original_command,
                result=f"Execution failed: {str(e)}",
                success=False
            )

    def _add_tool_message(
        self, command: str, result: str, success: bool = True, mcp_call: dict = None
    ):
        """Add a tool result message to the conversation."""
        if self._current_conversation_id is None:
            return

        mcp_calls_list = [mcp_call] if mcp_call else None

        if mcp_call:
            tool_name = mcp_call.get("tool", "unknown")
            content = f"[TOOL:{tool_name}] {command}"
        else:
            content = f"[TOOL] {command}"

        self.database.add_message(
            conversation_id=self._current_conversation_id,
            role="tool",
            content=content,
            mcp_calls=mcp_calls_list
        )

        self.chat_widget.load_conversation(self._current_conversation_id)
        logger.info(f"Tool message added: {command} success={success}")

    def _on_open_settings(self, initial_tab: int = 0) -> None:
        """Handle Settings action."""
        from bacchus.ui.settings_dialog import SettingsDialog

        logger.info(f"Opening settings dialog (tab {initial_tab})")

        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.tab_list.setCurrentRow(initial_tab)
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        dialog = SettingsDialog(
            self,
            model_manager=self.model_manager,
            mcp_manager=self.mcp_manager,
            initial_tab=initial_tab
        )
        dialog.model_changed.connect(self._on_model_changed)
        dialog.model_load_started.connect(self._on_model_load_started)
        dialog.mcp_status_changed.connect(self._update_mcp_status)

        if self.model_manager:
            current_model = self.model_manager.get_current_chat_model()
            if current_model:
                display_name = self.model_manager.get_model_display_name(current_model)
                dialog.set_current_model(display_name)
            else:
                dialog.set_current_model(None)

        self._settings_dialog = dialog
        dialog.finished.connect(lambda: setattr(self, '_settings_dialog', None))
        dialog.show()

    def _on_model_load_started(self, model_folder_name: str) -> None:
        """Handle model load beginning."""
        self._model_is_loading = True
        self.prompt_area.set_model_loaded(False)
        if self.model_manager:
            display_name = self.model_manager.get_model_display_name(model_folder_name)
        else:
            display_name = model_folder_name
        self.status_bar_widget.set_loading(True, display_name)
        logger.info(f"Model load started: {model_folder_name}")

    def _on_model_changed(self, model_folder_name: str):
        """Handle model change from settings (load or unload)."""
        logger.info(f"Model changed to: {model_folder_name!r}")

        self._model_is_loading = False
        self.status_bar_widget.set_loading(False)

        if not self.model_manager:
            return

        if model_folder_name:
            display_name = self.model_manager.get_model_display_name(model_folder_name)
            device = self.model_manager.get_active_device()
            self.status_bar_widget.set_model(display_name, device)
            self.prompt_area.set_model_loaded(True)
            self.prompt_area.set_vlm_mode(self.model_manager.is_vl_pipeline_loaded())
            self._settings["last_model"] = model_folder_name
            save_settings(self._settings)
        else:
            self.status_bar_widget.set_model(None)
            self.prompt_area.set_model_loaded(False)
            self.prompt_area.set_vlm_mode(False)

    def _on_open_data_folder(self) -> None:
        """Handle Open Data Folder action."""
        from bacchus.config import get_app_data_dir
        import os
        import subprocess

        data_dir = get_app_data_dir()

        try:
            if os.name == 'nt':
                os.startfile(str(data_dir))
            else:
                subprocess.run(['xdg-open', str(data_dir)])
        except Exception as e:
            logger.error(f"Failed to open data folder: {e}")

    def _on_show_about(self) -> None:
        """Handle About action."""
        from PyQt6.QtWidgets import QMessageBox

        about_text = locales.get_string("dialog.about_text",
            "Bacchus v0.1.0\n\nLocal LLM Chat Application\nPowered by OpenVINO\n\n© 2025")

        QMessageBox.about(
            self,
            locales.get_string("dialog.about_title", "About Bacchus"),
            about_text
        )

    def _on_status_bar_model_clicked(self):
        """Handle status bar model section click."""
        self._on_open_settings(initial_tab=1)

    def _on_status_bar_mcp_clicked(self):
        """Handle status bar MCP section click."""
        self._on_open_settings(initial_tab=3)

    def _update_mcp_status(self):
        """Update MCP server status in status bar."""
        if not self.mcp_manager:
            return

        servers = self.mcp_manager.list_servers()
        status_dict = {}

        for server in servers:
            if server.status == "running":
                status_dict[server.name] = "running"
            elif server.status == "error":
                status_dict[server.name] = "failed"
            else:
                status_dict[server.name] = "stopped"

        self.status_bar_widget.set_mcp_servers(status_dict)
        logger.debug(f"MCP status updated: {status_dict}")

    # ── Project handlers ───────────────────────────────────────────────────────

    def _on_new_project(self) -> None:
        """Open ProjectDialog in create mode."""
        from bacchus.ui.project_dialog import ProjectDialog
        from PyQt6.QtWidgets import QMessageBox

        if not self.model_manager or not self.model_manager.is_chat_model_loaded():
            QMessageBox.warning(
                self,
                "Model Not Loaded",
                "Please load a chat model from Settings > Models before creating a project."
            )
            return

        dialog = ProjectDialog(
            parent=self,
            database=self.database,
            model_manager=self.model_manager
        )
        dialog.project_saved.connect(self._on_project_saved)
        dialog.show()

    def _on_edit_project(self, project_id: int) -> None:
        """Open ProjectDialog in edit mode."""
        from bacchus.ui.project_dialog import ProjectDialog

        dialog = ProjectDialog(
            parent=self,
            database=self.database,
            model_manager=self.model_manager,
            project_id=project_id
        )
        dialog.project_saved.connect(self._on_project_saved)
        dialog.show()

    def _on_delete_project(self, project_id: int) -> None:
        """Delete a project: unassign conversations, remove files, refresh sidebar."""
        import shutil
        from bacchus.constants import PROJECTS_DIR

        self.database.delete_project(project_id)

        project_dir = PROJECTS_DIR / str(project_id)
        if project_dir.exists():
            try:
                shutil.rmtree(str(project_dir))
            except Exception as e:
                logger.warning(f"Could not remove project directory {project_dir}: {e}")

        self.sidebar.refresh()
        logger.info(f"Deleted project {project_id}")

    def _on_project_saved(self, project_id: int) -> None:
        """Refresh sidebar after a project is created or edited."""
        self.sidebar.refresh()
        logger.info(f"Project {project_id} saved — sidebar refreshed")

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        self._save_window_state()

        if self.mcp_manager:
            logger.info("Stopping MCP servers...")
            self.mcp_manager.stop_all_servers()
            logger.info("MCP servers stopped")

        if self.model_manager:
            self.model_manager.unload_chat_model()

        event.accept()
        logger.info("Main window closed")
