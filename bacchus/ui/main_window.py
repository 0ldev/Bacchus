"""
Main window for Bacchus application.

Central UI component containing menu bar, sidebar, chat area, and status bar.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QMainWindow,
    QMenuBar,
    QWidget,
)

from bacchus import locales
from bacchus.config import load_settings, save_settings


logger = logging.getLogger(__name__)


def _describe_tool_call(tool_name: str, arguments: dict) -> tuple[str, str]:
    """Return (action_description, detail) for a tool call."""
    mapping = {
        "read_file":        ("read a file",        arguments.get("path", "")),
        "write_file":       ("write a file",       arguments.get("path", "")),
        "edit_file":        ("edit a file",        arguments.get("path", "")),
        "list_directory":   ("list a directory",   arguments.get("path", "")),
        "create_directory": ("create a directory", arguments.get("path", "")),
        "execute_command":  ("execute a command",  arguments.get("command", "")),
        "search_web":       ("search the web",     arguments.get("query", "")),
        "fetch_webpage":    ("fetch a webpage",    arguments.get("url", "")),
    }
    return mapping.get(tool_name, (f"use tool '{tool_name}'", str(arguments)))


class MainWindow(QMainWindow):
    """
    Main application window for Bacchus.

    Contains:
    - Menu bar (File, Help)
    - Sidebar with conversation history
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
        self.setMinimumSize(1024, 768)
        
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
        self._inference_conversation_id: Optional[int] = None  # Conversation ID for active inference
        self._tool_iteration_count: int = 0  # Track tool calling iterations
        self._max_tool_iterations: int = 5  # Prevent infinite tool loops
        self._seen_tool_calls: set = set()  # (tool_name, args_hash) pairs to detect duplicates
        
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
        
        # Track settings dialog to prevent multiple instances
        self._settings_dialog = None

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
        
        # File menu
        file_menu = menubar.addMenu(locales.get_string("menu.file", "File"))
        
        # New Conversation
        new_action = file_menu.addAction(
            locales.get_string("menu.new_conversation", "New Conversation")
        )
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._on_new_conversation)
        
        # Export Current
        export_action = file_menu.addAction(
            locales.get_string("menu.export_current", "Export Current")
        )
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._on_export_conversation)
        
        file_menu.addSeparator()
        
        # Settings
        settings_action = file_menu.addAction(
            locales.get_string("menu.settings", "Settings")
        )
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._on_open_settings)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = file_menu.addAction(
            locales.get_string("menu.exit", "Exit")
        )
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        
        # Help menu
        help_menu = menubar.addMenu(locales.get_string("menu.help", "Help"))
        
        # Open Data Folder
        data_folder_action = help_menu.addAction(
            locales.get_string("menu.open_data_folder", "Open Data Folder")
        )
        data_folder_action.triggered.connect(self._on_open_data_folder)
        
        # About
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
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top section: sidebar + chat area
        top_widget = QWidget()
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        
        # Add sidebar
        self.sidebar = Sidebar(self.database)
        self.sidebar.new_conversation_requested.connect(self._on_new_conversation)
        self.sidebar.conversation_selected.connect(self._on_conversation_selected)
        self.sidebar.export_requested.connect(self._on_export_conversation_by_id)
        self.sidebar.delete_requested.connect(self._on_delete_conversation)
        top_layout.addWidget(self.sidebar)
        
        # Right side: chat area + prompt area in vertical layout
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Add chat widget
        self.chat_widget = ChatWidget(self.database)
        right_layout.addWidget(self.chat_widget, 1)  # Stretch factor 1 - takes available space
        
        # Add prompt area (no stretch - uses minimum height)
        self.prompt_area = PromptArea()
        self.prompt_area.send_message_requested.connect(self._on_send_message)
        self.prompt_area.document_attached.connect(self._on_document_attached)
        self.prompt_area.document_removed.connect(self._on_document_removed)
        right_layout.addWidget(self.prompt_area, 0)  # Stretch factor 0 - fixed size
        
        right_widget.setLayout(right_layout)
        top_layout.addWidget(right_widget, 1)  # Stretch factor 1
        
        top_widget.setLayout(top_layout)
        main_layout.addWidget(top_widget, 1)  # Stretch factor 1
        
        # Add status bar at bottom
        main_layout.addWidget(self.status_bar_widget)
        
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def _create_status_bar(self) -> None:
        """Create the status bar."""
        from bacchus.ui.status_bar import StatusBar
        
        # Remove default status bar
        self.setStatusBar(None)
        
        # Create custom status bar widget
        self.status_bar_widget = StatusBar()
        self.status_bar_widget.model_clicked.connect(self._on_status_bar_model_clicked)
        self.status_bar_widget.mcp_clicked.connect(self._on_status_bar_mcp_clicked)
        
        # Add to main window (needs to be added to central widget layout)
        # Will be added in _create_central_widget
        
        logger.info("Status bar created")

    # Menu action handlers
    def _on_new_conversation(self) -> None:
        """Handle New Conversation action."""
        logger.info("New conversation requested")
        
        # Create new conversation in database
        title = "New Conversation"  # Will be updated with first message
        conv_id = self.database.create_conversation(title=title)
        
        # Refresh sidebar
        self.sidebar.refresh()
        
        # Select the new conversation
        self._current_conversation_id = conv_id
        
        # Clear chat area (will show "no messages yet")
        self.chat_widget.load_conversation(conv_id)
        
        # Focus input area
        self.prompt_area.focus_input()
        
        logger.info(f"Created new conversation {conv_id}")
    
    def _on_conversation_selected(self, conversation_id: int):
        """Handle conversation selection from sidebar."""
        logger.info(f"Loading conversation {conversation_id}")
        self._current_conversation_id = conversation_id
        
        # Load conversation messages into chat area
        self.chat_widget.load_conversation(conversation_id)
        
        # Enable prompt area
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
        from PyQt6.QtWidgets import QFileDialog
        
        # Get conversation details
        conversation = self.database.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversation {conversation_id} not found")
            return
        
        # Open save dialog
        default_filename = f"conversation_{conversation_id}.txt"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            locales.get_string("menu.export_current", "Export Conversation"),
            default_filename,
            "Text Files (*.txt)"
        )
        
        if not filepath:
            return  # User cancelled
        
        # Export conversation
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
            from PyQt6.QtWidgets import QMessageBox
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
            
            # Refresh sidebar
            self.sidebar.refresh()
            
            # If deleted conversation was current, clear selection
            if self._current_conversation_id == conversation_id:
                self._current_conversation_id = None
                self.chat_widget.clear()
                self.prompt_area.set_enabled(False)
            
            logger.info(f"Deleted conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")

    def _on_open_settings(self, initial_tab: int = 0) -> None:
        """
        Handle Settings action.
        
        Args:
            initial_tab: Index of tab to show initially (0=General, 1=Models, 2=Performance, 3=MCP)
        """
        from bacchus.ui.settings_dialog import SettingsDialog
        
        logger.info(f"Opening settings dialog (tab {initial_tab})")
        
        # If dialog already exists and is visible, just switch tab
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.tab_list.setCurrentRow(initial_tab)
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        
        # Create new dialog
        dialog = SettingsDialog(
            self,
            model_manager=self.model_manager,
            mcp_manager=self.mcp_manager,
            initial_tab=initial_tab
        )
        dialog.model_changed.connect(self._on_model_changed)
        dialog.mcp_status_changed.connect(self._update_mcp_status)
        
        # Set current model in dialog
        if self.model_manager:
            current_model = self.model_manager.get_current_chat_model()
            if current_model:
                display_name = self.model_manager.get_model_display_name(current_model)
                dialog.set_current_model(display_name)
            else:
                dialog.set_current_model(None)
        
        # Track dialog
        self._settings_dialog = dialog
        
        # Clear reference when closed
        dialog.finished.connect(lambda: setattr(self, '_settings_dialog', None))
        
        dialog.exec()
    
    def _on_model_changed(self, model_folder_name: str):
        """Handle model change from settings."""
        logger.info(f"Model changed to: {model_folder_name}")

        if not self.model_manager:
            return

        # Update status bar with display name and device
        display_name = self.model_manager.get_model_display_name(model_folder_name)
        device = self.model_manager.get_active_device()
        self.status_bar_widget.set_model(display_name, device)

        # Enable/disable prompt area
        self.prompt_area.set_model_loaded(True)
        self.prompt_area.set_vlm_mode(self.model_manager.is_vl_pipeline_loaded())

        # Save last model to settings
        from bacchus.config import save_settings
        self._settings["last_model"] = model_folder_name
        save_settings(self._settings)

    def _on_open_data_folder(self) -> None:
        """Handle Open Data Folder action."""
        from bacchus.config import get_app_data_dir
        import os
        import subprocess
        
        data_dir = get_app_data_dir()
        
        try:
            if os.name == 'nt':  # Windows
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


    def _on_send_message(self, text: str):
        """Handle send message from prompt area."""
        if self._current_conversation_id is None:
            logger.warning("Cannot send message: no conversation selected")
            return

        # Check if this is a slash command
        if text.startswith("/"):
            self._handle_slash_command(text)
            return

        if not self.model_manager or not self.model_manager.is_chat_model_loaded():
            logger.warning("Cannot send message: no model loaded")
            return

        # Prevent sending while inference is running
        if self._inference_worker is not None and self._inference_worker.isRunning():
            logger.warning("Cannot send message: inference is already running")
            return

        logger.info(f"Sending message to conversation {self._current_conversation_id}")

        # Reset tool iteration state for new user message
        self._tool_iteration_count = 0
        self._seen_tool_calls = set()

        # Collect attached image (VLM mode) and copy to permanent storage
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

        # Add user message to database
        self.database.add_message(
            conversation_id=self._current_conversation_id,
            role="user",
            content=text,
            image_path=image_path
        )

        # Update conversation title if this is first message
        conversation = self.database.get_conversation(self._current_conversation_id)
        if conversation and conversation.title == "New Conversation":
            # Use first 100 chars of message as title
            title = text[:100]
            self.database.update_conversation(
                conversation_id=self._current_conversation_id,
                title=title
            )
            # Refresh sidebar to show new title
            self.sidebar.refresh()

        # Reload conversation to show new message
        self.chat_widget.load_conversation(self._current_conversation_id)

        # Disable input during generation
        self.prompt_area.set_generating(True)
        self.status_bar_widget.set_active(True)

        # Start inference
        self._start_inference(conversation)

    def _handle_slash_command(self, text: str):
        """
        Handle slash commands for MCP tool invocation.

        Supported commands:
        - /read <path>   - Read file contents
        - /list <path>   - List directory contents
        - /run <command> - Execute shell command
        - /help          - Show available commands
        """
        import json
        import shlex

        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        logger.info(f"Slash command: {command} args={args}")

        # Help command
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

        # Check MCP manager
        if not self.mcp_manager:
            self._add_tool_message(
                command=text,
                result="Error: MCP manager not available",
                success=False
            )
            return

        # Route to appropriate tool
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

    def _execute_mcp_tool(self, server_name: str, tool_name: str, arguments: dict, original_command: str):
        """
        Execute an MCP tool and display the result.

        Args:
            server_name: Name of MCP server
            tool_name: Name of tool to call
            arguments: Tool arguments
            original_command: Original command text for display
        """
        import json

        # Get client
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

        # Execute tool
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

    def _add_tool_message(self, command: str, result: str, success: bool = True, mcp_call: dict = None):
        """
        Add a tool result message to the conversation.

        Args:
            command: The command that was executed
            result: The result text
            success: Whether execution succeeded
            mcp_call: Optional MCP call details for storage
        """
        if self._current_conversation_id is None:
            return

        # Store MCP call details as list (database will convert to JSON)
        mcp_calls_list = [mcp_call] if mcp_call else None

        # Format content with metadata for rich display
        # The chat widget will use mcp_calls to create rich display
        if mcp_call:
            tool_name = mcp_call.get("tool", "unknown")
            content = f"[TOOL:{tool_name}] {command}"
        else:
            content = f"[TOOL] {command}"

        # Add to database with role="tool"
        self.database.add_message(
            conversation_id=self._current_conversation_id,
            role="tool",
            content=content,
            mcp_calls=mcp_calls_list
        )

        # Reload conversation to show new message
        self.chat_widget.load_conversation(self._current_conversation_id)

        logger.info(f"Tool message added: {command} success={success}")
    
    def _on_document_attached(self, file_path: str):
        """Handle document attachment."""
        if self._current_conversation_id is None:
            logger.warning("Cannot attach document: no conversation selected")
            return
        
        logger.info(f"Document attached: {file_path}")
        
        # TODO: Process document with RAG pipeline
        # TODO: Update conversation in database with document_path
        # For now, just log
        logger.info("Document processing not yet implemented")
    
    def _on_document_removed(self):
        """Handle document removal."""
        if self._current_conversation_id is None:
            return
        
        logger.info("Document removed from conversation")
        
        # TODO: Update conversation in database (clear document fields)
        # For now, just log
        logger.info("Document removal not yet fully implemented")
    
    def _on_status_bar_model_clicked(self):
        """Handle status bar model section click."""
        logger.info("Status bar model clicked - opening Settings > Models")
        self._on_open_settings(initial_tab=1)  # Models tab
    
    def _on_status_bar_mcp_clicked(self):
        """Handle status bar MCP section click."""
        logger.info("Status bar MCP clicked - opening Settings > MCP")
        self._on_open_settings(initial_tab=3)  # MCP tab

    def _update_mcp_status(self):
        """Update MCP server status in status bar."""
        if not self.mcp_manager:
            return

        servers = self.mcp_manager.list_servers()
        status_dict = {}

        for server in servers:
            # Map internal status to status bar format
            if server.status == "running":
                status_dict[server.name] = "running"
            elif server.status == "error":
                status_dict[server.name] = "failed"
            else:
                status_dict[server.name] = "stopped"

        self.status_bar_widget.set_mcp_servers(status_dict)
        logger.debug(f"MCP status updated: {status_dict}")
    
    def _start_inference(self, conversation):
        """
        Start inference for the current conversation.

        Args:
            conversation: Conversation dataclass
            tool_results: Optional tool results to inject into context
        """
        from bacchus.inference.chat import (
            construct_prompt,
            trim_context_fifo,
            estimate_tokens
        )
        from bacchus.inference.inference_worker import InferenceWorker

        # Get conversation messages
        messages = self.database.get_conversation_messages(self._current_conversation_id)

        # Convert to format expected by inference
        # For messages with an image, prepend the stored description so both the
        # LLM path and VLM-with-no-file path have textual image context.
        formatted_messages = [
            {
                "role": msg.role,
                "content": (
                    f"[Image: {msg.image_description}]\n{msg.content}"
                    if msg.image_description
                    else msg.content
                )
            }
            for msg in messages
        ]

        # Get system message from dynamic prompt manager
        # System prompt is always English — LLMs follow English instructions more reliably
        # regardless of the user's conversation language.
        from bacchus.prompts import get_prompt_manager

        prompt_manager = get_prompt_manager()
        system_message = prompt_manager.get_system_prompt(self.mcp_manager)

        logger.debug(f"Loaded dynamic system prompt ({len(system_message)} chars)")

        # TODO: Check if RAG is needed and build RAG context
        rag_context = None
        document_name = None

        # Get context window from model manager (reads from constants.CHAT_MODELS)
        model_folder = self.model_manager.get_current_chat_model()
        context_window = self.model_manager.get_context_window()

        # Trim context if needed
        system_tokens = estimate_tokens(system_message)
        rag_tokens = estimate_tokens(rag_context) if rag_context else 0

        logger.info(
            f"Context window: {context_window} tokens | "
            f"model={model_folder} | "
            f"history={len(formatted_messages)} messages"
        )

        trimmed_messages = trim_context_fifo(
            formatted_messages,
            max_tokens=context_window,
            system_tokens=system_tokens,
            rag_tokens=rag_tokens
        )

        # Construct prompt (pass model folder for correct chat template)
        prompt = construct_prompt(
            messages=trimmed_messages,
            system_message=system_message,
            rag_context=rag_context,
            document_name=document_name,
            model_folder=model_folder
        )

        logger.debug(f"Prompt constructed, length: {len(prompt)} chars")

        # Get LLM pipeline
        llm_pipeline = self.model_manager.get_llm_pipeline()

        # Calculate max_new_tokens based on remaining context budget
        estimated_used = system_tokens + sum(estimate_tokens(m.get("content", "")) for m in trimmed_messages)
        max_new_tokens = context_window - estimated_used - 512  # 512 token safety buffer
        max_new_tokens = max(512, max_new_tokens)  # At least 512 tokens

        # VLM path: uses VLMInferenceWorker with full context replay and tool-call support
        if self.model_manager.is_vl_pipeline_loaded():
            from bacchus.inference.vlm_worker import VLMInferenceWorker

            vlm_pipeline = self.model_manager.get_vlm_pipeline()

            # Build decision-schema generation config — same logic as the LLM path below.
            # full system_message is passed (16k context has plenty of room).
            vlm_generation_config = None
            last_msg = messages[-1] if messages else None
            if last_msg and last_msg.role in ("user", "system"):
                is_last_iteration = self._tool_iteration_count >= self._max_tool_iterations - 1
                if not is_last_iteration:
                    from bacchus.inference.decision_schema import create_decision_config

                    tool_names = []
                    if self.mcp_manager:
                        for server in self.mcp_manager.list_servers():
                            if server.status == "running" and server.client:
                                for tool in server.client._tools:
                                    tool_names.append(tool.name)

                    if tool_names:
                        vlm_generation_config = create_decision_config(
                            tool_names, max_tokens=max_new_tokens
                        )
                        logger.info(f"VLM using decision schema with {len(tool_names)} tools (iteration {self._tool_iteration_count + 1}/{self._max_tool_iterations})")
                    else:
                        logger.info("No tools available for VLM, using plain generation")
                else:
                    vlm_generation_config = None
                    logger.info(f"VLM final iteration: forcing plain generation for summary")

            self._inference_worker = VLMInferenceWorker(
                vlm_pipeline=vlm_pipeline,
                system_message=system_message,
                messages=messages,
                max_tokens=max_new_tokens,
                temperature=0.7,
                generation_config=vlm_generation_config,
            )

            # VLM context accounting (no trim — full history replayed via KV-cache)
            vlm_system_tokens = estimate_tokens(system_message)
            vlm_history_tokens = sum(estimate_tokens(m.content or "") + 4 for m in messages)
            vlm_total = vlm_system_tokens + vlm_history_tokens
            images_in_history = sum(1 for m in messages if m.image_path)
            logger.info(
                f"VLM context: {context_window} window | "
                f"system={vlm_system_tokens} history={vlm_history_tokens} "
                f"({len(messages)} messages, {images_in_history} with images) | "
                f"estimate={vlm_total} ({100 * vlm_total / context_window:.1f}%) | "
                f"response_budget={max_new_tokens}"
            )

            self._current_response = ""
            self._inference_conversation_id = self._current_conversation_id

            self._inference_worker.image_described.connect(self._on_image_described)
            self._inference_worker.generation_completed.connect(self._on_generation_completed)
            self._inference_worker.generation_failed.connect(self._on_generation_failed)
            self._inference_worker.start()
            logger.info(f"VLM inference worker started (max_tokens={max_new_tokens})")
            return
        # For initial response: use decision schema to force valid tool call or response
        # For continuation: use regular generation or citation schema
        generation_config = None
        last_message = formatted_messages[-1] if formatted_messages else None

        if last_message and last_message["role"] in ("user", "system"):
            is_last_iteration = self._tool_iteration_count >= self._max_tool_iterations - 1
            if not is_last_iteration:
                # Allow chaining: offer tool choice via decision schema
                from bacchus.inference.decision_schema import create_decision_config

                tool_names = []
                if self.mcp_manager:
                    for server in self.mcp_manager.list_servers():
                        if server.status == "running" and server.client:
                            for tool in server.client._tools:
                                tool_names.append(tool.name)

                if tool_names:
                    generation_config = create_decision_config(tool_names, max_tokens=max_new_tokens)
                    logger.info(f"Using decision schema with {len(tool_names)} tools (iteration {self._tool_iteration_count + 1}/{self._max_tool_iterations})")
                else:
                    logger.info("No tools available, using plain generation")
            else:
                # Last allowed iteration: force plain generation for final summary
                generation_config = None
                logger.info(f"Final iteration ({self._max_tool_iterations}): forcing plain generation for summary")

        self._inference_worker = InferenceWorker(
            llm_pipeline=llm_pipeline,
            prompt=prompt,
            max_tokens=max_new_tokens,
            temperature=0.7,
            generation_config=generation_config  # None for regular, or decision schema
        )

        if generation_config:
            logger.info(f"Starting STRUCTURED generation with decision schema (max_tokens={max_new_tokens})")
        else:
            logger.info(f"Starting generation with max_tokens={max_new_tokens} (context_window={context_window})")

        # Track response for database
        self._current_response = ""
        # Capture conversation ID for this inference (prevents bug if user switches conversations)
        self._inference_conversation_id = self._current_conversation_id

        # Connect signals
        self._inference_worker.token_generated.connect(self._on_token_generated)
        self._inference_worker.generation_completed.connect(self._on_generation_completed)
        self._inference_worker.generation_failed.connect(self._on_generation_failed)

        # Start generation
        self._inference_worker.start()
        logger.info("Inference worker started")
    
    def _on_image_described(self, message_id: int, description: str) -> None:
        """Store auto-generated image description produced by VLMInferenceWorker."""
        try:
            self.database.update_message_image_description(message_id, description)
            logger.info(f"Stored image description for message {message_id} ({len(description)} chars)")
        except Exception as e:
            logger.warning(f"Failed to store image description for message {message_id}: {e}")

    def _on_token_generated(self, token: str):
        """Handle token generation (streaming)."""
        # Accumulate response
        self._current_response += token
        
        # TODO: Update chat widget with streaming response
        # For now, just accumulate
    
    def _strip_thinking_tags(self, response: str) -> str:
        """
        Strip <think>...</think> tags from reasoning model responses.

        DeepSeek R1 and similar models output their reasoning process in think tags.
        We remove these for cleaner display while keeping the final answer.
        """
        import re
        # Remove <think>...</think> blocks (including multiline)
        cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
        # Clean up extra whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned.strip())
        return cleaned

    def _on_generation_completed(self, response: str):
        """Handle generation completion and autonomous tool execution."""
        logger.info(f"Generation completed, length: {len(response)} chars")

        # Strip thinking tags from reasoning models (DeepSeek R1, etc.)
        if self.model_manager:
            model_folder = self.model_manager.get_current_chat_model() or ""
            if "deepseek" in model_folder.lower() or "r1" in model_folder.lower():
                original_len = len(response)
                response = self._strip_thinking_tags(response)
                if len(response) < original_len:
                    logger.info(f"Stripped thinking tags, {original_len} -> {len(response)} chars")

        # Check if this is a structured decision output (from decision schema)
        from bacchus.inference.decision_schema import parse_decision
        from bacchus.inference.autonomous_tools import execute_tool_call, format_tool_result, ToolCall

        decision = parse_decision(response)

        if decision["action"] == "tool_call" and self._tool_iteration_count < self._max_tool_iterations:
            # LLM wants to use a tool via structured decision!
            tool_name = decision["tool"]
            arguments = decision["arguments"]

            # Detect duplicate calls (same tool + same args) to break infinite loops
            import hashlib
            call_key = (tool_name, hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest())
            if call_key in self._seen_tool_calls:
                logger.warning(f"Duplicate tool call detected: {tool_name} with same args — forcing summary")
                response = decision.get("response", f"[Searched for information and found results above.]")
                decision = {"action": "respond", "response": response}
                # fall through to final response handling below
            else:
                self._seen_tool_calls.add(call_key)
                logger.info(f"Tool call detected (structured): {tool_name} (iteration {self._tool_iteration_count + 1}/{self._max_tool_iterations})")
                self._tool_iteration_count += 1

            # Create ToolCall object
            tool_call = ToolCall(
                tool_name=tool_name,
                arguments=arguments,
                raw_text=response
            )

            # Save the tool request to database (as JSON for clarity)
            tool_json = json.dumps({"tool": tool_name, "arguments": arguments}, indent=2)
            if self._inference_conversation_id is not None:
                self.database.add_message(
                    conversation_id=self._inference_conversation_id,
                    role="assistant",
                    content=tool_json,
                    mcp_calls=[{"tool": tool_name, "params": arguments}]
                )

            # Check permission before executing
            if self.mcp_manager:
                permission = self._check_tool_permission(tool_name, arguments)

                if permission == "deny":
                    # User denied — inject a denial message and let LLM respond
                    deny_msg = f"Permission denied by user for {tool_name}."
                    formatted_result = format_tool_result(tool_name, False, deny_msg)
                    if self._inference_conversation_id is not None:
                        self.database.add_message(
                            conversation_id=self._inference_conversation_id,
                            role="system",
                            content=formatted_result,
                            mcp_calls=[{"tool": tool_name, "params": arguments,
                                        "result": deny_msg, "success": False}]
                        )
                    if self._current_conversation_id == self._inference_conversation_id:
                        self.chat_widget.load_conversation(self._current_conversation_id)
                    if self._inference_worker:
                        self._inference_worker.deleteLater()
                        self._inference_worker = None
                    conversation = self.database.get_conversation(self._inference_conversation_id)
                    if conversation:
                        self._start_inference(conversation)
                    return

                elif permission == "sandbox":
                    # Run in OS-level sandbox
                    from bacchus.sandbox.runner import SandboxRunner
                    from bacchus.constants import SANDBOX_DIR
                    runner = SandboxRunner(SANDBOX_DIR)

                    if tool_name == "execute_command":
                        success, result = runner.run_command(arguments.get("command", ""))
                    elif tool_name in ("write_file", "edit_file", "create_directory"):
                        sandboxed_args = dict(arguments)
                        if "path" in sandboxed_args:
                            sandboxed_args["path"] = runner.sandbox_path(sandboxed_args["path"])
                        # Ensure the filesystem server allows writes into SANDBOX_DIR
                        self.mcp_manager.ensure_path_allowed(
                            "filesystem", str(SANDBOX_DIR), persist=False
                        )
                        sandboxed_call = ToolCall(
                            tool_name=tool_name,
                            arguments=sandboxed_args,
                            raw_text=response
                        )
                        success, result = execute_tool_call(sandboxed_call, self.mcp_manager)
                    else:
                        success, result = execute_tool_call(tool_call, self.mcp_manager)

                    logger.info(
                        f"Sandboxed tool execution {'succeeded' if success else 'failed'}"
                    )
                    formatted_result = format_tool_result(
                        tool_name, success, f"[SANDBOXED] {result}"
                    )

                else:
                    # Normal execution
                    success, result = execute_tool_call(tool_call, self.mcp_manager)
                    logger.info(
                        f"Tool execution {'succeeded' if success else 'failed'}, "
                        f"result length: {len(result)} chars"
                    )
                    formatted_result = format_tool_result(tool_name, success, result)

                # Add tool result to database as system message (with structured mcp_calls for UI)
                if self._inference_conversation_id is not None:
                    self.database.add_message(
                        conversation_id=self._inference_conversation_id,
                        role="system",
                        content=formatted_result,
                        mcp_calls=[{"tool": tool_name, "params": arguments,
                                    "result": result, "success": success}]
                    )

                # Reload conversation to show tool call and result
                if self._current_conversation_id == self._inference_conversation_id:
                    self.chat_widget.load_conversation(self._current_conversation_id)

                # Clean up previous worker
                if self._inference_worker:
                    self._inference_worker.deleteLater()
                    self._inference_worker = None

                # Start another generation with tool result
                # Get the conversation object to restart inference
                conversation = self.database.get_conversation(self._inference_conversation_id)
                if conversation:
                    self._start_inference(conversation)
                    return  # Don't complete yet - wait for next generation
                else:
                    logger.error(f"Failed to get conversation {self._inference_conversation_id} for tool iteration")
                    # Fall through to normal completion

            else:
                logger.warning("No MCP manager available for tool execution")
                # Fall through to normal completion

        elif decision["action"] == "tool_call" and self._tool_iteration_count >= self._max_tool_iterations:
            # Hit iteration limit
            logger.warning(f"Max tool iterations ({self._max_tool_iterations}) reached, stopping")
            error_msg = f"[System: Maximum tool iterations reached. Response may be incomplete.]"
            # Extract the response from decision or use error message
            response = decision.get("response", error_msg)

        elif decision["action"] == "respond":
            # Direct response - extract the text
            logger.info("Direct response (no tool needed)")
            response = decision.get("response", response)

        # No tool call or max iterations reached - this is the final response
        logger.info(f"Final response (action={decision['action']})")

        # Reset tool iteration state
        self._tool_iteration_count = 0
        self._seen_tool_calls = set()

        # Save final response using the captured conversation ID
        if self._inference_conversation_id is not None:
            self.database.add_message(
                conversation_id=self._inference_conversation_id,
                role="assistant",
                content=response
            )
        else:
            logger.warning("No conversation ID captured for inference - response not saved")

        # Reload conversation to show response
        if self._current_conversation_id == self._inference_conversation_id:
            self.chat_widget.load_conversation(self._current_conversation_id)
        else:
            # User switched conversations - just refresh sidebar
            self.sidebar.refresh_conversations()

        # Re-enable input
        self.prompt_area.set_generating(False)
        self.status_bar_widget.set_active(False)

        # Clean up worker
        if self._inference_worker:
            self._inference_worker.deleteLater()
            self._inference_worker = None
        self._current_response = ""

        logger.info("Generation cycle complete")
    
    _SAFE_TOOLS = {"search_web", "fetch_webpage", "read_file", "list_directory"}
    _RISKY_TOOLS = {"write_file", "edit_file", "create_directory", "execute_command"}
    _POLICY_DEFAULTS = {
        "search_web": "always_allow",
        "fetch_webpage": "always_allow",
    }

    def _check_tool_permission(self, tool_name: str, arguments: dict) -> str:
        """
        Check if a tool action is permitted, asking the user if not.

        Returns 'allow', 'sandbox', or 'deny'.
        """
        from bacchus.ui.permission_dialog import (
            ask_permission, ALLOW_ALWAYS, ALLOW_SESSION, SANDBOX, DENY, ALLOW_ONCE
        )

        # 1. Session memory — tools allowed for this session
        if tool_name in self._session_allowed_tools:
            return "allow"

        # 2. Saved policy from settings
        settings = load_settings()
        policy = (
            settings.get("permissions", {})
            .get("tool_policy", {})
            .get(tool_name, self._POLICY_DEFAULTS.get(tool_name, "ask"))
        )

        if policy == "always_allow":
            return "allow"
        if policy == "always_deny":
            return "deny"
        if policy == "sandbox_always":
            return "sandbox"

        # 3. Show permission dialog
        risky = tool_name not in self._SAFE_TOOLS
        action_desc, detail = _describe_tool_call(tool_name, arguments)
        result = ask_permission(tool_name, action_desc, detail, self, risky=risky)

        if result == DENY:
            return "deny"
        if result == SANDBOX:
            return "sandbox"

        # User granted access — update tool policy and expand filesystem allowed_paths
        persist_path = (result == ALLOW_ALWAYS)

        if result == ALLOW_SESSION:
            self._session_allowed_tools.add(tool_name)
        elif result == ALLOW_ALWAYS:
            s = load_settings()
            s.setdefault("permissions", {}).setdefault("tool_policy", {})[tool_name] = "always_allow"
            save_settings(s)

        # Expand the filesystem server's allowed_paths so the subprocess accepts the path
        if tool_name in ("read_file", "write_file", "edit_file",
                         "list_directory", "create_directory") and self.mcp_manager:
            import os
            from pathlib import Path as _P
            raw_path = arguments.get("path", "")
            if raw_path:
                try:
                    resolved = _P(os.path.expandvars(raw_path)).resolve()
                    parent = str(resolved.parent if tool_name != "list_directory"
                                 else resolved)
                    self.mcp_manager.ensure_path_allowed(
                        "filesystem", parent, persist=persist_path
                    )
                except Exception as e:
                    logger.warning(f"Could not expand allowed_paths for {raw_path}: {e}")

        return "allow"  # ALLOW_ONCE, ALLOW_SESSION, or ALLOW_ALWAYS

    def _on_generation_failed(self, error: str):
        """Handle generation failure."""
        logger.error(f"Generation failed: {error}")
        
        # Re-enable input
        self.prompt_area.set_generating(False)
        self.status_bar_widget.set_active(False)
        
        # Show error to user
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            self,
            locales.get_string("error.generation_failed", "Generation Failed"),
            locales.get_string("error.generation_failed_msg",
                f"Failed to generate response: {error}")
        )
        
        # Clean up worker
        if self._inference_worker:
            self._inference_worker.deleteLater()
            self._inference_worker = None
        self._current_response = ""

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Save window state before closing
        self._save_window_state()

        # Stop MCP servers
        if self.mcp_manager:
            logger.info("Stopping MCP servers...")
            self.mcp_manager.stop_all_servers()
            logger.info("MCP servers stopped")

        # TODO: Unload model

        event.accept()
        logger.info("Main window closed")
