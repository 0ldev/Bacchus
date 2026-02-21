"""
Settings dialog for Bacchus.

Modal dialog with 5 tabs: General, Models, Performance, MCP Servers, Permissions.
Fixed size 700x500 pixels.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bacchus import constants, locales
from bacchus.config import load_settings, save_settings, get_config_dir, load_secrets, save_secrets

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """
    Settings dialog with tabbed interface.

    Tabs: General, Models, Performance, MCP Servers
    """

    model_changed = pyqtSignal(str)  # Emits model folder name
    mcp_status_changed = pyqtSignal()  # Emits when MCP server status changes

    def __init__(self, parent=None, model_manager=None, mcp_manager=None, initial_tab=0):
        """
        Initialize settings dialog.

        Args:
            parent: Parent widget
            model_manager: ModelManager instance (optional)
            mcp_manager: MCPManager instance (optional)
            initial_tab: Index of tab to show initially (0=General, 1=Models, 2=Performance, 3=MCP, 4=Permissions)
        """
        super().__init__(parent)

        self.model_manager = model_manager
        self.mcp_manager = mcp_manager
        self._initial_tab = initial_tab
        
        self.setWindowTitle(locales.get_string("settings.title", "Settings"))
        self.setFixedSize(700, 580)
        self.setModal(True)
        
        # Load settings
        self._settings = load_settings()
        
        # Track active downloads
        self._active_downloads: Dict[str, 'DownloadWorker'] = {}
        
        # Main layout
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left sidebar with tab buttons — colours depend on active theme
        self.tab_list = QListWidget()
        self.tab_list.setFixedWidth(150)
        is_dark = self._settings.get("theme", "light") == "dark"
        if is_dark:
            self.tab_list.setStyleSheet("""
                QListWidget {
                    background-color: #252525;
                    border: none;
                    border-right: 1px solid #3d3d3d;
                }
                QListWidget::item {
                    padding: 12px;
                    border-bottom: 1px solid #2d2d2d;
                    color: #e0e0e0;
                }
                QListWidget::item:selected {
                    background-color: #3d5a80;
                    color: #ffffff;
                }
                QListWidget::item:hover {
                    background-color: #2a2a2a;
                }
            """)
        else:
            self.tab_list.setStyleSheet("""
                QListWidget {
                    background-color: #f5f5f5;
                    border: none;
                    border-right: 1px solid #ddd;
                }
                QListWidget::item {
                    padding: 12px;
                    border-bottom: 1px solid #e0e0e0;
                }
                QListWidget::item:selected {
                    background-color: #e3f2fd;
                    color: #1976d2;
                }
                QListWidget::item:hover {
                    background-color: #eeeeee;
                }
            """)
        
        # Add tab items
        self.tab_list.addItem(locales.get_string("settings.tab_general", "General"))
        self.tab_list.addItem(locales.get_string("settings.tab_models", "Models"))
        self.tab_list.addItem(locales.get_string("settings.tab_performance", "Performance"))
        self.tab_list.addItem(locales.get_string("settings.tab_mcp", "MCP Servers"))
        self.tab_list.addItem(locales.get_string("settings.tab_permissions", "Permissions"))
        
        self.tab_list.setCurrentRow(0)
        self.tab_list.currentRowChanged.connect(self._on_tab_changed)
        
        main_layout.addWidget(self.tab_list)
        
        # Right content area with stacked pages
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        
        # Create tab pages
        self.general_tab = self._create_general_tab()
        self.models_tab = self._create_models_tab()
        self.performance_tab = self._create_performance_tab()
        self.mcp_tab = self._create_mcp_tab()
        self.permissions_tab = self._create_permissions_tab()

        # Add all tabs to layout (only one visible at a time)
        self.content_layout.addWidget(self.general_tab)
        self.content_layout.addWidget(self.models_tab)
        self.content_layout.addWidget(self.performance_tab)
        self.content_layout.addWidget(self.mcp_tab)
        self.content_layout.addWidget(self.permissions_tab)

        # Show only first tab initially
        self.general_tab.show()
        self.models_tab.hide()
        self.performance_tab.hide()
        self.mcp_tab.hide()
        self.permissions_tab.hide()
        
        self.content_widget.setLayout(self.content_layout)
        main_layout.addWidget(self.content_widget, 1)
        
        self.setLayout(main_layout)
        
        # Set initial tab
        if self._initial_tab != 0:
            self.tab_list.setCurrentRow(self._initial_tab)
        
        logger.info("Settings dialog initialized")
    
    def _on_tab_changed(self, index: int):
        """Handle tab selection change."""
        # Hide all tabs
        self.general_tab.hide()
        self.models_tab.hide()
        self.performance_tab.hide()
        self.mcp_tab.hide()
        self.permissions_tab.hide()

        # Show selected tab
        if index == 0:
            self.general_tab.show()
        elif index == 1:
            self.models_tab.show()
        elif index == 2:
            self.performance_tab.show()
        elif index == 3:
            self.mcp_tab.show()
        elif index == 4:
            self.permissions_tab.show()
    
    def _create_general_tab(self) -> QWidget:
        """Create General tab content."""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Language Section
        lang_group = QGroupBox(
            locales.get_string("settings.language_section", "Interface Language")
        )
        lang_layout = QVBoxLayout()
        
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Português (Brasil)", "pt-BR")
        
        # Set current language
        current_lang = self._settings.get("language", "en")
        index = self.language_combo.findData(current_lang)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addWidget(self.language_combo)
        
        # Warning label
        warning_label = QLabel(
            "⚠ " + locales.get_string("settings.restart_required", 
                                     "Restart required to apply language change")
        )
        warning_label.setStyleSheet("color: #f57c00; font-size: 11px;")
        lang_layout.addWidget(warning_label)
        
        lang_group.setLayout(lang_layout)
        layout.addWidget(lang_group)
        
        # Theme Section
        theme_group = QGroupBox(
            locales.get_string("settings.theme_section", "Theme")
        )
        theme_layout = QVBoxLayout()
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(locales.get_string("settings.theme_light", "Light"), "light")
        self.theme_combo.addItem(locales.get_string("settings.theme_dark", "Dark"), "dark")
        
        # Set current theme
        current_theme = self._settings.get("theme", "light")
        index = self.theme_combo.findData(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(self.theme_combo)
        
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # Data Folders Section
        folders_group = QGroupBox(
            locales.get_string("settings.data_folders", "Data Folders")
        )
        folders_layout = QVBoxLayout()
        
        # Conversations folder button
        conv_button = QPushButton(
            "📁 " + locales.get_string("settings.open_conversations", 
                                      "Open Conversations Folder")
        )
        conv_button.clicked.connect(lambda: self._open_folder(constants.CONVERSATIONS_DIR))
        folders_layout.addWidget(conv_button)
        
        # Models folder button
        models_button = QPushButton(
            "📁 " + locales.get_string("settings.open_models", "Open Models Folder")
        )
        models_button.clicked.connect(lambda: self._open_folder(constants.MODELS_DIR))
        folders_layout.addWidget(models_button)
        
        # Logs folder button
        logs_button = QPushButton(
            "📁 " + locales.get_string("settings.open_logs", "Open Logs Folder")
        )
        logs_button.clicked.connect(lambda: self._open_folder(constants.LOGS_DIR))
        folders_layout.addWidget(logs_button)

        # Prompts folder button
        prompts_button = QPushButton(
            "📁 " + locales.get_string("settings.open_prompts", "Open Prompts Folder")
        )
        from pathlib import Path
        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompts_button.clicked.connect(lambda: self._open_folder(prompts_dir))
        folders_layout.addWidget(prompts_button)

        # Config folder button
        config_button = QPushButton(
            "📁 " + locales.get_string("settings.open_config", "Open Config Folder")
        )
        config_button.clicked.connect(lambda: self._open_folder(get_config_dir()))
        folders_layout.addWidget(config_button)

        folders_group.setLayout(folders_layout)
        layout.addWidget(folders_group)
        
        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def _create_models_tab(self) -> QWidget:
        """Create Models tab content."""
        from bacchus.constants import CONTEXT_SIZE_OPTIONS, DEFAULT_CONTEXT_SIZE

        tab = QWidget()
        layout = QVBoxLayout()

        # ── Active Model Section ────────────────────────────────────────────
        active_group = QGroupBox(
            locales.get_string("settings.active_model", "Active Model")
        )
        active_layout = QVBoxLayout()
        active_layout.setSpacing(6)

        # Currently loaded label
        self.current_model_label = QLabel(
            locales.get_string("settings.currently_loaded", "Currently loaded: ") + "None"
        )
        active_layout.addWidget(self.current_model_label)

        # Model switcher row
        switch_layout = QHBoxLayout()
        switch_layout.addWidget(QLabel(locales.get_string("settings.switch_to", "Switch to:")))

        self.model_combo = QComboBox()
        self._populate_model_combo()
        self.model_combo.currentIndexChanged.connect(self._on_model_selection_changed)
        switch_layout.addWidget(self.model_combo, 1)

        self.apply_model_button = QPushButton(locales.get_string("settings.apply", "Apply"))
        self.apply_model_button.setEnabled(False)
        self.apply_model_button.clicked.connect(self._on_apply_model)
        switch_layout.addWidget(self.apply_model_button)

        active_layout.addLayout(switch_layout)

        # Context size row
        context_layout = QHBoxLayout()
        context_layout.addWidget(QLabel(
            locales.get_string("settings.context_size", "Context size:")
        ))

        self.context_combo = QComboBox()
        for size in CONTEXT_SIZE_OPTIONS:
            self.context_combo.addItem(f"{size:,} tokens", size)
        self._sync_context_combo(DEFAULT_CONTEXT_SIZE)

        context_help = QLabel(
            locales.get_string("settings.context_size_help",
                               "(saved per model, applied on load)")
        )
        context_help.setStyleSheet("color: #888888; font-size: 11px;")

        context_layout.addWidget(self.context_combo)
        context_layout.addWidget(context_help)
        context_layout.addStretch()
        active_layout.addLayout(context_layout)

        # Startup model row
        startup_layout = QHBoxLayout()

        startup_folder = self._settings.get("startup_model")
        if startup_folder and self.model_manager:
            startup_display = self.model_manager.get_model_display_name(startup_folder)
        elif startup_folder:
            startup_display = startup_folder
        else:
            startup_display = locales.get_string("settings.none", "None")

        self.startup_model_label = QLabel(
            locales.get_string("settings.startup_model", "Startup model: ") + startup_display
        )
        startup_layout.addWidget(self.startup_model_label, 1)

        set_startup_btn = QPushButton(
            locales.get_string("settings.set_startup", "Set as startup")
        )
        set_startup_btn.setFixedWidth(120)
        set_startup_btn.clicked.connect(self._on_set_startup_model)
        startup_layout.addWidget(set_startup_btn)

        clear_startup_btn = QPushButton(
            locales.get_string("settings.clear_startup", "Clear")
        )
        clear_startup_btn.setFixedWidth(60)
        clear_startup_btn.clicked.connect(self._on_clear_startup_model)
        startup_layout.addWidget(clear_startup_btn)

        active_layout.addLayout(startup_layout)
        active_group.setLayout(active_layout)
        layout.addWidget(active_group)

        # ── Download Manager Section ────────────────────────────────────────
        download_group = QGroupBox(
            locales.get_string("settings.download_models", "Download Models")
        )
        download_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_widget = QWidget()
        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(10)

        self._create_model_cards()

        self.cards_layout.addStretch()
        self.cards_widget.setLayout(self.cards_layout)
        scroll.setWidget(self.cards_widget)
        download_layout.addWidget(scroll)

        download_group.setLayout(download_layout)
        layout.addWidget(download_group)

        tab.setLayout(layout)
        return tab
    
    def _create_model_cards(self):
        """Create model cards from CHAT_MODELS constant."""
        from bacchus.ui.model_card import ModelCard
        from bacchus.constants import CHAT_MODELS

        # Build card list directly from constants so the two never diverge
        models = [
            {
                "id": folder,
                "display_name": info["display_name"],
                "size": f"~{info['approx_size_gb']:.1f} GB",
                "repo_id": info["huggingface_repo"],
                "folder_name": folder,
            }
            for folder, info in CHAT_MODELS.items()
        ]
        
        self.model_cards = {}
        
        for model_info in models:
            card = ModelCard(
                model_id=model_info["id"],
                display_name=model_info["display_name"],
                size_str=model_info["size"],
                repo_id=model_info["repo_id"],
                folder_name=model_info["folder_name"]
            )
            
            card.download_requested.connect(self._on_download_requested)
            card.cancel_requested.connect(self._on_cancel_requested)
            card.delete_requested.connect(self._on_delete_requested)
            
            self.cards_layout.addWidget(card)
            self.model_cards[model_info["id"]] = card
    
    def _on_download_requested(self, model_id: str):
        """Handle download request for a model."""
        from bacchus.ui.download_worker import DownloadWorker
        
        logger.info(f"Download requested: {model_id}")
        
        card = self.model_cards.get(model_id)
        if not card:
            return
        
        # Set downloading state
        card.set_downloading(True)
        card.set_progress(0, None)
        
        # Create and start download worker
        worker = DownloadWorker(
            repo_id=card.repo_id,
            local_dir=card.model_path
        )
        
        # Connect signals
        worker.progress_updated.connect(
            lambda pct, speed: self._on_download_progress(model_id, pct, speed)
        )
        worker.download_completed.connect(
            lambda success: self._on_download_completed(model_id, success)
        )
        
        # Track active download
        self._active_downloads[model_id] = worker
        
        # Start download
        worker.start()
        
        logger.info(f"Download started: {model_id}")
    
    def _on_download_progress(self, model_id: str, percentage: int, speed: str):
        """Handle download progress update."""
        card = self.model_cards.get(model_id)
        if card:
            card.set_progress(percentage, speed)
    
    def _on_download_completed(self, model_id: str, success: bool):
        """Handle download completion."""
        logger.info(f"Download completed: {model_id} (success={success})")
        
        card = self.model_cards.get(model_id)
        worker = self._active_downloads.pop(model_id, None)
        
        if not card:
            return
        
        if success:
            card.set_downloaded(True)
            # Refresh model combo box so new model appears in dropdown
            self._populate_model_combo()
        else:
            card.set_downloading(False)

            # Show error message
            from PyQt6.QtWidgets import QMessageBox
            from PyQt6.QtCore import Qt

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle(locales.get_string("error.download_failed", "Download Failed"))
            msg.setText(locales.get_string("error.download_failed_msg",
                f"Failed to download {card.display_name}. Check logs for details."))
            msg.setWindowModality(Qt.WindowModality.ApplicationModal)
            msg.exec()

        # Clean up worker
        if worker:
            worker.deleteLater()
    
    def _on_cancel_requested(self, model_id: str):
        """Handle download cancellation."""
        logger.info(f"Cancel requested: {model_id}")
        
        worker = self._active_downloads.get(model_id)
        card = self.model_cards.get(model_id)
        
        if worker:
            worker.cancel()
            # Note: Worker will clean up and emit completion signal
        
        if card:
            card.set_downloading(False)
    
    def _on_delete_requested(self, model_id: str):
        """Handle model deletion."""
        logger.info(f"Delete requested: {model_id}")
        
        card = self.model_cards.get(model_id)
        if not card:
            return
        
        try:
            # Delete model folder
            import shutil
            if card.model_path.exists():
                shutil.rmtree(card.model_path)
                logger.info(f"Deleted model: {card.model_path}")
            
            # Update card state
            card.set_downloaded(False)
            
        except Exception as e:
            logger.error(f"Failed to delete model: {e}")
            from PyQt6.QtWidgets import QMessageBox
            from PyQt6.QtCore import Qt
            
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle(locales.get_string("error.generic", "Error"))
            msg.setText(f"Failed to delete model: {str(e)}")
            msg.setWindowModality(Qt.WindowModality.ApplicationModal)
            msg.exec()
    
    def _create_performance_tab(self) -> QWidget:
        """Create Performance tab content."""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # NPU Configuration Section
        npu_group = QGroupBox(
            locales.get_string("settings.npu_config", "NPU Configuration")
        )
        npu_layout = QVBoxLayout()
        
        self.npu_turbo_checkbox = QCheckBox(
            locales.get_string("settings.enable_turbo", "Enable NPU Turbo Mode")
        )
        self.npu_turbo_checkbox.setChecked(
            self._settings.get("performance", {}).get("npu_turbo", True)
        )
        self.npu_turbo_checkbox.stateChanged.connect(self._on_npu_turbo_changed)
        npu_layout.addWidget(self.npu_turbo_checkbox)
        
        turbo_help = QLabel(
            locales.get_string("settings.turbo_help", 
                             "Higher performance, higher power consumption")
        )
        turbo_help.setStyleSheet("color: #888888; font-size: 11px; margin-left: 24px;")
        npu_layout.addWidget(turbo_help)
        
        npu_group.setLayout(npu_layout)
        layout.addWidget(npu_group)

        # Startup Section
        startup_group = QGroupBox(
            locales.get_string("settings.startup", "Startup")
        )
        startup_layout = QVBoxLayout()

        self.autoload_model_checkbox = QCheckBox(
            locales.get_string("settings.autoload_model", "Auto-load last used model on startup")
        )
        self.autoload_model_checkbox.setChecked(
            self._settings.get("performance", {}).get("autoload_model", False)
        )
        self.autoload_model_checkbox.stateChanged.connect(self._on_autoload_changed)
        startup_layout.addWidget(self.autoload_model_checkbox)

        startup_help = QLabel(
            locales.get_string("settings.autoload_help",
                             "When enabled, the last used model will be loaded automatically")
        )
        startup_help.setStyleSheet("color: #888888; font-size: 11px; margin-left: 24px;")
        startup_layout.addWidget(startup_help)

        startup_group.setLayout(startup_layout)
        layout.addWidget(startup_group)

        # Memory Management Section
        memory_group = QGroupBox(
            locales.get_string("settings.memory_mgmt", "Memory Management")
        )
        memory_layout = QVBoxLayout()
        
        memory_layout.addWidget(QLabel(
            locales.get_string("settings.when_exceeds", 
                             "When conversation exceeds available memory:")
        ))
        
        self.fifo_radio = QRadioButton(
            locales.get_string("settings.fifo", "Remove oldest messages (FIFO)")
        )
        self.fifo_radio.setChecked(True)
        memory_layout.addWidget(self.fifo_radio)
        
        self.compact_radio = QRadioButton(
            locales.get_string("settings.compact", 
                             "Compact older messages (summarize) - Coming Soon")
        )
        self.compact_radio.setEnabled(False)
        memory_layout.addWidget(self.compact_radio)
        
        memory_group.setLayout(memory_layout)
        layout.addWidget(memory_group)

        # Tool Calling Mode Section
        tools_group = QGroupBox(
            locales.get_string("settings.tool_calling_mode", "Tool Calling Mode")
        )
        tools_layout = QVBoxLayout()

        tools_layout.addWidget(QLabel(
            locales.get_string("settings.tool_calling_desc",
                             "How should the assistant use MCP tools?")
        ))

        self.llm_driven_radio = QRadioButton(
            locales.get_string("settings.llm_driven",
                             "LLM-driven (Recommended) - Model decides when to call tools")
        )
        self.user_initiated_radio = QRadioButton(
            locales.get_string("settings.user_initiated",
                             "User-initiated - Use /call commands only")
        )

        # Load saved setting
        tool_mode = self._settings.get("performance", {}).get("tool_calling_mode", "llm_driven")
        if tool_mode == "user_initiated":
            self.user_initiated_radio.setChecked(True)
        else:
            self.llm_driven_radio.setChecked(True)

        self.llm_driven_radio.toggled.connect(self._on_tool_mode_changed)

        tools_layout.addWidget(self.llm_driven_radio)
        tools_layout.addWidget(self.user_initiated_radio)

        # Help text for LLM-driven
        llm_help = QLabel(
            locales.get_string("settings.llm_driven_help",
                             "The model will automatically use tools when appropriate")
        )
        llm_help.setStyleSheet("color: #888888; font-size: 11px; margin-left: 24px;")
        tools_layout.addWidget(llm_help)

        tools_group.setLayout(tools_layout)
        layout.addWidget(tools_group)

        layout.addStretch()
        tab.setLayout(layout)
        return tab
    
    def _create_mcp_tab(self) -> QWidget:
        """Create MCP Servers tab content."""
        tab = QWidget()
        layout = QVBoxLayout()

        # MCP Servers Section
        mcp_group = QGroupBox(
            locales.get_string("settings.mcp_servers", "MCP Servers")
        )
        mcp_layout = QVBoxLayout()

        # Server table
        self.mcp_table = QTableWidget()
        self.mcp_table.setColumnCount(4)
        self.mcp_table.setHorizontalHeaderLabels([
            locales.get_string("settings.server_name", "Name"),
            locales.get_string("settings.server_status", "Status"),
            locales.get_string("settings.autostart", "Autostart"),
            locales.get_string("settings.actions", "Actions")
        ])
        self.mcp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.mcp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.mcp_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.mcp_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.mcp_table.verticalHeader().setVisible(False)
        self.mcp_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mcp_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        mcp_layout.addWidget(self.mcp_table)

        # Buttons
        btn_layout = QHBoxLayout()
        
        add_button = QPushButton(
            locales.get_string("settings.add_mcp_server", "+ Add MCP Server")
        )
        add_button.clicked.connect(self._on_add_mcp_server)
        btn_layout.addWidget(add_button)
        
        open_config_button = QPushButton(
            locales.get_string("settings.open_mcp_config", "Open Config File")
        )
        open_config_button.clicked.connect(lambda: self._open_file(self.mcp_manager._config_path))
        btn_layout.addWidget(open_config_button)
        
        mcp_layout.addLayout(btn_layout)

        mcp_group.setLayout(mcp_layout)
        layout.addWidget(mcp_group)

        # Help text
        help_label = QLabel(
            locales.get_string("settings.mcp_help",
                "MCP servers provide tools the assistant can use. "
                "Built-in servers (filesystem, cmd) cannot be deleted.")
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #888888; font-size: 11px; margin-top: 10px;")
        layout.addWidget(help_label)

        layout.addStretch()
        tab.setLayout(layout)

        # Populate table
        self._refresh_mcp_table()

        return tab

    def _create_permissions_tab(self) -> QWidget:
        """Create Permissions tab content."""
        from bacchus.config import expand_path
        from bacchus.constants import SANDBOX_DIR

        tab = QWidget()
        outer_layout = QVBoxLayout()

        # --- Scripts Directory group ---
        scripts_group = QGroupBox(
            locales.get_string("settings.permissions_scripts_dir", "Scripts Directory")
        )
        scripts_layout = QVBoxLayout()

        help_label = QLabel(
            locales.get_string(
                "settings.permissions_scripts_help",
                "Default location where the assistant saves generated scripts."
            )
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #888888; font-size: 11px;")
        scripts_layout.addWidget(help_label)

        dir_row = QHBoxLayout()
        current_scripts_dir = self._settings.get("permissions", {}).get(
            "scripts_dir", "%APPDATA%/Bacchus/scripts"
        )
        self._scripts_dir_edit = QLineEdit(current_scripts_dir)
        dir_row.addWidget(self._scripts_dir_edit, 1)

        browse_btn = QPushButton(
            locales.get_string("settings.permissions_browse", "Browse")
        )

        def _browse_scripts():
            folder = QFileDialog.getExistingDirectory(
                self,
                locales.get_string("settings.permissions_scripts_dir", "Scripts Directory"),
                expand_path(self._scripts_dir_edit.text())
            )
            if folder:
                self._scripts_dir_edit.setText(folder)

        browse_btn.clicked.connect(_browse_scripts)
        dir_row.addWidget(browse_btn)

        open_scripts_btn = QPushButton(
            locales.get_string("settings.permissions_open", "Open")
        )
        open_scripts_btn.clicked.connect(
            lambda: self._open_folder(Path(expand_path(self._scripts_dir_edit.text())))
        )
        dir_row.addWidget(open_scripts_btn)
        scripts_layout.addLayout(dir_row)
        scripts_group.setLayout(scripts_layout)
        outer_layout.addWidget(scripts_group)

        # --- Tool Permissions group ---
        policy_group = QGroupBox(
            locales.get_string("settings.permissions_tool_policy", "Tool Permissions")
        )
        policy_layout = QVBoxLayout()

        self._perm_table = QTableWidget()
        self._perm_table.setColumnCount(2)
        self._perm_table.setHorizontalHeaderLabels([
            locales.get_string("settings.permissions_tool_col", "Tool"),
            locales.get_string("settings.permissions_policy_col", "Permission"),
        ])
        self._perm_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._perm_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._perm_table.verticalHeader().setVisible(False)
        self._perm_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._perm_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        # Tool order: risky first, safe second
        tool_order = [
            "execute_command",
            "write_file",
            "edit_file",
            "create_directory",
            "read_file",
            "list_directory",
            "search_web",
            "fetch_webpage",
        ]
        policy_keys = ["ask", "always_allow", "sandbox_always", "always_deny"]
        policy_labels = [
            locales.get_string("settings.permissions_ask", "Ask"),
            locales.get_string("settings.permissions_always_allow", "Always allow"),
            locales.get_string("settings.permissions_sandbox_always", "Sandbox always"),
            locales.get_string("settings.permissions_always_deny", "Always deny"),
        ]

        saved_policies = self._settings.get("permissions", {}).get("tool_policy", {})
        self._perm_table.setRowCount(len(tool_order))
        self._perm_combos: dict[str, QComboBox] = {}

        for row, tool in enumerate(tool_order):
            self._perm_table.setItem(row, 0, QTableWidgetItem(tool))
            combo = QComboBox()
            for label in policy_labels:
                combo.addItem(label)

            saved = saved_policies.get(tool, "ask")
            if saved in policy_keys:
                combo.setCurrentIndex(policy_keys.index(saved))

            self._perm_table.setCellWidget(row, 1, combo)
            self._perm_combos[tool] = combo

        policy_layout.addWidget(self._perm_table)

        # Save button
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_perm_btn = QPushButton(
            locales.get_string("settings.permissions_save", "Save")
        )
        save_perm_btn.clicked.connect(
            lambda: self._save_permissions(tool_order, policy_keys)
        )
        save_row.addWidget(save_perm_btn)
        policy_layout.addLayout(save_row)
        policy_group.setLayout(policy_layout)
        outer_layout.addWidget(policy_group)

        # --- Bottom buttons ---
        bottom_row = QHBoxLayout()

        open_sandbox_btn = QPushButton(
            locales.get_string("settings.permissions_open_sandbox", "Open Sandbox Folder")
        )
        open_sandbox_btn.clicked.connect(lambda: self._open_folder(SANDBOX_DIR))
        bottom_row.addWidget(open_sandbox_btn)

        bottom_row.addStretch()

        reset_btn = QPushButton(
            locales.get_string("settings.permissions_reset", "Reset all to defaults")
        )

        def _reset_permissions():
            s = load_settings()
            if "permissions" in s and "tool_policy" in s["permissions"]:
                del s["permissions"]["tool_policy"]
            save_settings(s)
            # Reload combos
            defaults = {
                "search_web": "always_allow", "fetch_webpage": "always_allow",
            }
            for t, combo in self._perm_combos.items():
                default = defaults.get(t, "ask")
                combo.setCurrentIndex(policy_keys.index(default))

        reset_btn.clicked.connect(_reset_permissions)
        bottom_row.addWidget(reset_btn)
        outer_layout.addLayout(bottom_row)

        tab.setLayout(outer_layout)
        return tab

    def _save_permissions(self, tool_order: list, policy_keys: list):
        """Save permission settings to settings.yaml."""
        s = load_settings()
        perms = s.setdefault("permissions", {})
        perms["scripts_dir"] = self._scripts_dir_edit.text().strip()
        tool_policy = perms.setdefault("tool_policy", {})
        for tool in tool_order:
            combo = self._perm_combos.get(tool)
            if combo:
                tool_policy[tool] = policy_keys[combo.currentIndex()]
        save_settings(s)
        logger.info("Permissions saved")

    def _refresh_mcp_table(self):
        """Refresh the MCP server table with current data."""
        if not self.mcp_manager:
            return

        servers = self.mcp_manager.list_servers()
        self.mcp_table.setRowCount(len(servers))

        for row, server in enumerate(servers):
            # Name
            name_item = QTableWidgetItem(server.name)
            self.mcp_table.setItem(row, 0, name_item)

            # Status with colored indicator
            status_text = self._get_status_display(server.status)
            status_item = QTableWidgetItem(status_text)
            self.mcp_table.setItem(row, 1, status_item)

            # Autostart checkbox
            autostart_widget = QWidget()
            autostart_layout = QHBoxLayout()
            autostart_layout.setContentsMargins(5, 0, 5, 0)
            autostart_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            autostart_cb = QCheckBox()
            autostart_cb.setChecked(server.autostart)
            autostart_cb.stateChanged.connect(
                lambda state, s=server.name: self._on_autostart_changed(s, state)
            )
            autostart_layout.addWidget(autostart_cb)
            autostart_widget.setLayout(autostart_layout)
            self.mcp_table.setCellWidget(row, 2, autostart_widget)

            # Actions buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            # Start/Stop button
            if server.status == "running":
                stop_btn = QPushButton(locales.get_string("settings.stop", "Stop"))
                stop_btn.setFixedWidth(50)
                stop_btn.clicked.connect(lambda _, s=server.name: self._on_stop_server(s))
                actions_layout.addWidget(stop_btn)
            else:
                start_btn = QPushButton(locales.get_string("settings.start", "Start"))
                start_btn.setFixedWidth(50)
                start_btn.clicked.connect(lambda _, s=server.name: self._on_start_server(s))
                actions_layout.addWidget(start_btn)

            # Configure button (only for builtin servers filesystem and cmd and web_search)
            if server.builtin and server.name in ("filesystem", "cmd", "web_search"):
                cfg_btn = QPushButton(locales.get_string("settings.configure", "Configure"))
                cfg_btn.setFixedWidth(65)
                cfg_btn.clicked.connect(lambda _, s=server.name: self._on_configure_server(s))
                actions_layout.addWidget(cfg_btn)

            # Delete button (only for non-builtin)
            if not server.builtin:
                del_btn = QPushButton(locales.get_string("settings.delete", "Delete"))
                del_btn.setFixedWidth(50)
                del_btn.setStyleSheet("color: #d32f2f;")
                del_btn.clicked.connect(lambda _, s=server.name: self._on_delete_server(s))
                actions_layout.addWidget(del_btn)

            actions_widget.setLayout(actions_layout)
            self.mcp_table.setCellWidget(row, 3, actions_widget)

    def _get_status_display(self, status: str) -> str:
        """Get display text for server status."""
        if status == "running":
            return "● " + locales.get_string("settings.running", "Running")
        elif status == "error":
            return "✗ " + locales.get_string("settings.error", "Error")
        else:
            return "○ " + locales.get_string("settings.stopped", "Stopped")

    def _on_start_server(self, server_name: str):
        """Handle start server button click."""
        if not self.mcp_manager:
            return

        logger.info(f"Starting MCP server: {server_name}")
        success = self.mcp_manager.start_server(server_name)

        if success:
            logger.info(f"Server {server_name} started successfully")
        else:
            server = self.mcp_manager.get_server(server_name)
            error_msg = server.error_message if server else "Unknown error"
            QMessageBox.warning(
                self,
                locales.get_string("error.server_start_failed", "Server Start Failed"),
                f"{server_name}: {error_msg}"
            )

        self._refresh_mcp_table()
        self.mcp_status_changed.emit()

    def _on_stop_server(self, server_name: str):
        """Handle stop server button click."""
        if not self.mcp_manager:
            return

        logger.info(f"Stopping MCP server: {server_name}")
        self.mcp_manager.stop_server(server_name)
        self._refresh_mcp_table()
        self.mcp_status_changed.emit()

    def _on_autostart_changed(self, server_name: str, state: int):
        """Handle autostart checkbox change."""
        # TODO: Update server config and save to mcp_servers.yaml
        logger.info(f"Autostart changed for {server_name}: {state}")

    def _on_add_mcp_server(self):
        """Handle add MCP server button click."""
        dialog = AddMCPServerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.server_name
            command = dialog.command
            autostart = dialog.autostart

            # TODO: Add server to mcp_manager and save config
            logger.info(f"Add server requested: {name}, {command}, autostart={autostart}")

            self._refresh_mcp_table()
            self.mcp_status_changed.emit()

    def _on_configure_server(self, server_name: str):
        """Open configuration dialog for a builtin server."""
        if not self.mcp_manager:
            return

        server = self.mcp_manager.get_server(server_name)
        if not server:
            return

        if server_name == "filesystem":
            dialog = ConfigureFilesystemDialog(server.config, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.mcp_manager.save_server_config(server_name, dialog.get_config())
                self._refresh_mcp_table()
                self.mcp_status_changed.emit()
        elif server_name == "cmd":
            dialog = ConfigureCmdDialog(server.config, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.mcp_manager.save_server_config(server_name, dialog.get_config())
                self._refresh_mcp_table()
                self.mcp_status_changed.emit()
        elif server_name == "web_search":
            ws_secrets = load_secrets().get("web_search", {})
            dialog = ConfigureWebSearchDialog(server.config, ws_secrets, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.mcp_manager.save_server_config(server_name, dialog.get_config())
                all_secrets = load_secrets()
                all_secrets["web_search"] = dialog.get_secrets()
                save_secrets(all_secrets)
                self._refresh_mcp_table()
                self.mcp_status_changed.emit()

    def _on_delete_server(self, server_name: str):
        """Handle delete server button click."""
        reply = QMessageBox.question(
            self,
            locales.get_string("settings.delete_server", "Delete Server?"),
            locales.get_string("settings.delete_server_confirm",
                f"Delete MCP server '{server_name}'? This cannot be undone."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # TODO: Remove server from mcp_manager and save config
            logger.info(f"Delete server requested: {server_name}")
            self._refresh_mcp_table()
            self.mcp_status_changed.emit()
    
    def _on_language_changed(self, index: int):
        """Handle language selection change."""
        new_lang = self.language_combo.currentData()
        old_lang = self._settings.get("language", "en")
        
        if new_lang == old_lang:
            return
        
        # Save to settings
        self._settings["language"] = new_lang
        save_settings(self._settings)
        
        logger.info(f"Language changed from {old_lang} to {new_lang}")
        
        # Show restart dialog
        from PyQt6.QtWidgets import QMessageBox
        
        msg = QMessageBox(self)
        msg.setWindowTitle(locales.get_string("settings.restart_title", "Restart Required"))
        msg.setText(locales.get_string("settings.restart_message", 
                          "Restart Bacchus to apply language change?"))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        reply = msg.exec()
        
        if reply == QMessageBox.StandardButton.Yes:
            # Restart application
            logger.info("Restarting application for language change")
            # Close all windows
            self.parent().close()
            # Restart
            os.execl(sys.executable, sys.executable, *sys.argv)
    
    def _on_theme_changed(self, index: int):
        """Handle theme selection change."""
        from bacchus.theme import get_theme_stylesheet
        from PyQt6.QtWidgets import QApplication
        
        new_theme = self.theme_combo.currentData()
        old_theme = self._settings.get("theme", "light")
        
        if new_theme == old_theme:
            return
        
        # Save to settings
        self._settings["theme"] = new_theme
        save_settings(self._settings)
        
        logger.info(f"Theme changed from {old_theme} to {new_theme}")
        
        # Apply theme immediately
        stylesheet = get_theme_stylesheet(new_theme)
        QApplication.instance().setStyleSheet(stylesheet)
    
    def _on_npu_turbo_changed(self, state: int):
        """Handle NPU turbo mode toggle."""
        enabled = state == Qt.CheckState.Checked.value

        # Save to settings
        if "performance" not in self._settings:
            self._settings["performance"] = {}
        self._settings["performance"]["npu_turbo"] = enabled
        save_settings(self._settings)

        logger.info(f"NPU turbo mode: {enabled}")

    def _on_tool_mode_changed(self, checked: bool):
        """Handle tool calling mode change."""
        if not checked:
            return  # Only handle when radio button is checked

        mode = "llm_driven" if self.llm_driven_radio.isChecked() else "user_initiated"

        # Save to settings
        if "performance" not in self._settings:
            self._settings["performance"] = {}
        self._settings["performance"]["tool_calling_mode"] = mode
        save_settings(self._settings)

        logger.info(f"Tool calling mode: {mode}")

    def _on_autoload_changed(self, state: int):
        """Handle auto-load model on startup toggle."""
        enabled = state == Qt.CheckState.Checked.value

        # Save to settings
        if "performance" not in self._settings:
            self._settings["performance"] = {}
        self._settings["performance"]["autoload_model"] = enabled
        save_settings(self._settings)

        logger.info(f"Auto-load model on startup: {enabled}")

    def _open_folder(self, folder_path: Path):
        """Open folder in system file explorer."""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(str(folder_path))
            else:  # Linux/Mac
                subprocess.run(['xdg-open', str(folder_path)])
            logger.info(f"Opened folder: {folder_path}")
        except Exception as e:
            logger.error(f"Failed to open folder {folder_path}: {e}")

    def _open_file(self, file_path: Path):
        """Open file in system default editor."""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(str(file_path))
            else:  # Linux/Mac
                subprocess.run(['xdg-open', str(file_path)])
            logger.info(f"Opened file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to open file {file_path}: {e}")
    
    def _populate_model_combo(self):
        """Populate model switcher combo box with available models."""
        self.model_combo.clear()
        
        if not self.model_manager:
            self.model_combo.addItem(
                locales.get_string("settings.no_models", "No models downloaded")
            )
            return
        
        available_models = self.model_manager.get_available_chat_models()
        
        if not available_models:
            self.model_combo.addItem(
                locales.get_string("settings.no_models", "No models downloaded")
            )
        else:
            for folder_name in available_models:
                display_name = self.model_manager.get_model_display_name(folder_name)
                self.model_combo.addItem(display_name, folder_name)
    
    def _sync_context_combo(self, size: int):
        """Set the context combo to the closest matching size value."""
        for i in range(self.context_combo.count()):
            if self.context_combo.itemData(i) == size:
                self.context_combo.setCurrentIndex(i)
                return
        # If exact match not found, select last (largest) option
        self.context_combo.setCurrentIndex(self.context_combo.count() - 1)

    def _on_model_selection_changed(self, index: int):
        """Handle model selection change — update apply button and context combo."""
        if not self.model_manager:
            return

        selected_folder = self.model_combo.currentData()
        current_model = self.model_manager.get_current_chat_model()

        self.apply_model_button.setEnabled(
            selected_folder is not None and selected_folder != current_model
        )

        # Sync context combo to the saved size for this model
        if selected_folder:
            from bacchus.constants import DEFAULT_CONTEXT_SIZE
            saved_size = self._settings.get("model_context_sizes", {}).get(
                selected_folder, DEFAULT_CONTEXT_SIZE
            )
            self._sync_context_combo(saved_size)

    def _on_apply_model(self):
        """Save context size, then load the selected model."""
        if not self.model_manager:
            return

        selected_folder = self.model_combo.currentData()
        if not selected_folder:
            return

        # Persist the chosen context size before loading (model_manager reads it)
        context_size = self.context_combo.currentData()
        if context_size:
            self._settings.setdefault("model_context_sizes", {})[selected_folder] = context_size
            save_settings(self._settings)
            logger.info(f"Saved context size {context_size} for {selected_folder}")

        logger.info(f"Applying model switch: {selected_folder}")

        self.apply_model_button.setEnabled(False)
        self.apply_model_button.setText(locales.get_string("settings.loading", "Loading..."))

        try:
            success = self.model_manager.load_chat_model(selected_folder)
        except Exception as e:
            logger.error(f"Unexpected error loading model: {e}", exc_info=True)
            success = False

        if success:
            display_name = self.model_manager.get_model_display_name(selected_folder)
            self.set_current_model(display_name)
            self.model_changed.emit(selected_folder)
            logger.info(f"Model switched successfully to: {selected_folder}")
        else:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle(locales.get_string("error.model_load_failed", "Model Load Failed"))
            msg.setText(locales.get_string("error.model_load_failed_msg",
                f"Failed to load {self.model_combo.currentText()}.\n\n"
                "Check the logs for details. The model files may be incomplete or "
                "incompatible with your hardware."))
            msg.setWindowModality(Qt.WindowModality.ApplicationModal)
            msg.exec()

        self.apply_model_button.setText(locales.get_string("settings.apply", "Apply"))
        # Re-evaluate whether Apply should remain enabled
        self._on_model_selection_changed(self.model_combo.currentIndex())

    def _on_set_startup_model(self):
        """Set the selected model as the startup model."""
        selected_folder = self.model_combo.currentData()
        if not selected_folder:
            return

        self._settings["startup_model"] = selected_folder
        save_settings(self._settings)

        if self.model_manager:
            display_name = self.model_manager.get_model_display_name(selected_folder)
        else:
            display_name = selected_folder

        self.startup_model_label.setText(
            locales.get_string("settings.startup_model", "Startup model: ") + display_name
        )
        logger.info(f"Startup model set to: {selected_folder}")

    def _on_clear_startup_model(self):
        """Remove the configured startup model."""
        self._settings["startup_model"] = None
        save_settings(self._settings)
        self.startup_model_label.setText(
            locales.get_string("settings.startup_model", "Startup model: ") +
            locales.get_string("settings.none", "None")
        )
        logger.info("Startup model cleared")
    
    def set_current_model(self, model_name: Optional[str]):
        """
        Set the currently loaded model display.
        
        Args:
            model_name: Display name of loaded model, or None
        """
        if model_name:
            text = locales.get_string("settings.currently_loaded", "Currently loaded: ")
            text += model_name
        else:
            text = locales.get_string("settings.currently_loaded", "Currently loaded: ")
            text += locales.get_string("settings.no_model", "None")
        
        self.current_model_label.setText(text)

        # Refresh combo box
        self._populate_model_combo()


class AddMCPServerDialog(QDialog):
    """Dialog for adding a new MCP server."""

    def __init__(self, parent=None):
        """Initialize add MCP server dialog."""
        super().__init__(parent)

        self.server_name = ""
        self.command = ""
        self.autostart = False

        self.setWindowTitle(
            locales.get_string("settings.add_mcp_server_title", "Add MCP Server")
        )
        self.setFixedSize(450, 200)
        self.setModal(True)

        layout = QVBoxLayout()

        # Server name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel(
            locales.get_string("settings.server_name", "Server Name") + ":"
        ))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("my-server")
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # Command
        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(QLabel(
            locales.get_string("settings.command", "Command") + ":"
        ))
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("python -m my_mcp_server")
        cmd_layout.addWidget(self.command_edit)
        layout.addLayout(cmd_layout)

        # Autostart checkbox
        self.autostart_cb = QCheckBox(
            locales.get_string("settings.autostart_with_app",
                "Start automatically with Bacchus")
        )
        layout.addWidget(self.autostart_cb)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton(locales.get_string("settings.cancel", "Cancel"))
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton(locales.get_string("settings.save", "Save"))
        save_btn.clicked.connect(self._on_save)
        save_btn.setDefault(True)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _on_save(self):
        """Handle save button click."""
        name = self.name_edit.text().strip()
        command = self.command_edit.text().strip()

        # Validation
        if not name:
            QMessageBox.warning(
                self,
                locales.get_string("error.validation", "Validation Error"),
                locales.get_string("error.name_required", "Server name is required.")
            )
            return

        if not command:
            QMessageBox.warning(
                self,
                locales.get_string("error.validation", "Validation Error"),
                locales.get_string("error.command_required", "Command is required.")
            )
            return

        # Check for valid name (alphanumeric and hyphens)
        import re
        if not re.match(r'^[a-zA-Z0-9-]+$', name):
            QMessageBox.warning(
                self,
                locales.get_string("error.validation", "Validation Error"),
                locales.get_string("error.invalid_name",
                    "Server name can only contain letters, numbers, and hyphens.")
            )
            return

        self.server_name = name
        self.command = command
        self.autostart = self.autostart_cb.isChecked()
        self.accept()


class ConfigureFilesystemDialog(QDialog):
    """Dialog for configuring filesystem server allowed paths."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = dict(config)

        self.setWindowTitle("Configure Filesystem Server")
        self.setFixedSize(480, 320)
        self.setModal(True)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Allowed paths (the AI can read/write within these directories):"))

        self.list_widget = QListWidget()
        for path in self._config.get("allowed_paths", []):
            self.list_widget.addItem(path)
        layout.addWidget(self.list_widget)

        # Add/remove controls
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("%USERPROFILE%/Documents")
        row.addWidget(self.path_edit)

        add_btn = QPushButton("Add")
        add_btn.setFixedWidth(50)
        add_btn.clicked.connect(self._add_path)
        row.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setFixedWidth(60)
        remove_btn.clicked.connect(self._remove_selected)
        row.addWidget(remove_btn)

        layout.addLayout(row)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def _add_path(self):
        path = self.path_edit.text().strip()
        if path:
            self.list_widget.addItem(path)
            self.path_edit.clear()

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_config(self) -> dict:
        paths = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        result = dict(self._config)
        result["allowed_paths"] = paths
        return result


class ConfigureCmdDialog(QDialog):
    """Dialog for configuring cmd server blocked commands."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = dict(config)

        self.setWindowTitle("Configure Command Server")
        self.setFixedSize(400, 300)
        self.setModal(True)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Blocked commands (the AI cannot run these):"))

        self.list_widget = QListWidget()
        for cmd in self._config.get("blocked_commands", []):
            self.list_widget.addItem(cmd)
        layout.addWidget(self.list_widget)

        row = QHBoxLayout()
        self.cmd_edit = QLineEdit()
        self.cmd_edit.setPlaceholderText("rm")
        row.addWidget(self.cmd_edit)

        add_btn = QPushButton("Add")
        add_btn.setFixedWidth(50)
        add_btn.clicked.connect(self._add_cmd)
        row.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setFixedWidth(60)
        remove_btn.clicked.connect(self._remove_selected)
        row.addWidget(remove_btn)

        layout.addLayout(row)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def _add_cmd(self):
        cmd = self.cmd_edit.text().strip()
        if cmd:
            self.list_widget.addItem(cmd)
            self.cmd_edit.clear()

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_config(self) -> dict:
        cmds = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        result = dict(self._config)
        result["blocked_commands"] = cmds
        return result


class ConfigureWebSearchDialog(QDialog):
    """Dialog for configuring web search provider and settings."""

    # (provider_key, label, extra_field_key, extra_field_label, extra_placeholder)
    _PROVIDERS = [
        ("duckduckgo", "DuckDuckGo (Free)", None, None, None),
        ("brave",      "Brave Search",       None, None, None),
        ("google",     "Google Custom Search", "cx", "CX ID:", "Search Engine ID"),
        ("serpapi",    "SerpAPI",             None, None, None),
        ("tavily",     "Tavily AI",           None, None, None),
        ("openai",     "OpenAI",              "model", "Model:", "gpt-4o-mini-search-preview"),
        ("gemini",     "Gemini",              "model", "Model:", "gemini-1.5-flash"),
        ("firecrawl",  "Firecrawl",           None, None, None),
        ("exa",        "Exa (Metaphor)",      None, None, None),
        ("serper",     "Serper.dev",          None, None, None),
        ("searchapi",  "SearchApi",           None, None, None),
    ]

    def __init__(self, config: dict, ws_secrets: dict, parent=None):
        """
        Args:
            config: Current mcp_servers.yaml config for web_search.
            ws_secrets: Current secrets under the "web_search" key from secrets.yaml.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._config = dict(config)
        self._ws_secrets = ws_secrets  # {provider: {api_key: ..., cx/model: ...}}

        self.setWindowTitle("Configure Web Search")
        self.setFixedSize(520, 580)
        self.setModal(True)

        layout = QVBoxLayout()

        # Provider selector
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        for p_key, p_label, *_ in self._PROVIDERS:
            self.provider_combo.addItem(p_label, p_key)
        current = self._config.get("provider", "duckduckgo")
        idx = self.provider_combo.findData(current)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        provider_row.addWidget(self.provider_combo, 1)
        layout.addLayout(provider_row)

        # API Keys scroll area
        keys_group = QGroupBox("API Keys")
        keys_outer = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._key_fields: dict = {}  # provider_key -> {key: QLineEdit, [cx|model]: QLineEdit}

        for p_key, p_label, extra_key, extra_label, extra_placeholder in self._PROVIDERS:
            if p_key == "duckduckgo":
                continue  # no API key needed

            p_secrets = self._ws_secrets.get(p_key, {})

            # API key row
            key_field = QLineEdit()
            key_field.setEchoMode(QLineEdit.EchoMode.Password)
            key_field.setPlaceholderText("API Key")
            key_field.setText(p_secrets.get("api_key", ""))

            show_cb = QCheckBox("Show")
            show_cb.stateChanged.connect(
                lambda state, f=key_field: f.setEchoMode(
                    QLineEdit.EchoMode.Normal if state else QLineEdit.EchoMode.Password
                )
            )

            key_row_widget = QWidget()
            key_row = QHBoxLayout()
            key_row.setContentsMargins(0, 0, 0, 0)
            key_row.addWidget(key_field)
            key_row.addWidget(show_cb)
            key_row_widget.setLayout(key_row)

            form.addRow(f"{p_label}:", key_row_widget)
            self._key_fields[p_key] = {"key": key_field}

            # Extra field (cx or model)
            if extra_key and extra_label:
                extra_field = QLineEdit()
                extra_field.setPlaceholderText(extra_placeholder or "")
                if extra_key == "model":
                    extra_field.setText(p_secrets.get("model", extra_placeholder or ""))
                elif extra_key == "cx":
                    extra_field.setText(p_secrets.get("cx", ""))
                form.addRow(f"  {extra_label}", extra_field)
                self._key_fields[p_key][extra_key] = extra_field

        scroll_widget.setLayout(form)
        scroll.setWidget(scroll_widget)
        keys_outer.addWidget(scroll)
        keys_group.setLayout(keys_outer)
        layout.addWidget(keys_group)

        # Settings
        settings_group = QGroupBox("Settings")
        settings_form = QFormLayout()

        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 50)
        self.max_results_spin.setValue(int(self._config.get("max_results", 10)))
        settings_form.addRow("Max Results:", self.max_results_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 120)
        self.timeout_spin.setSuffix(" seconds")
        self.timeout_spin.setValue(int(self._config.get("timeout", 10)))
        settings_form.addRow("Request Timeout:", self.timeout_spin)

        self.fetch_len_spin = QSpinBox()
        self.fetch_len_spin.setRange(500, 100000)
        self.fetch_len_spin.setSingleStep(500)
        self.fetch_len_spin.setSuffix(" chars")
        self.fetch_len_spin.setValue(int(self._config.get("fetch_max_length", 8000)))
        settings_form.addRow("Max Fetch Length:", self.fetch_len_spin)

        settings_group.setLayout(settings_form)
        layout.addWidget(settings_group)

        layout.addStretch()

        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def get_config(self) -> dict:
        """Return config dict (no api_key — that lives in secrets)."""
        result = dict(self._config)
        result["provider"] = self.provider_combo.currentData()
        result["max_results"] = self.max_results_spin.value()
        result["timeout"] = self.timeout_spin.value()
        result["fetch_max_length"] = self.fetch_len_spin.value()
        # Strip any leftover secret fields from config
        for field in ("api_key", "cx", "model"):
            result.pop(field, None)
        return result

    def get_secrets(self) -> dict:
        """Return nested secrets dict: {provider: {api_key: ..., ...}}."""
        secrets = {}
        for p_key, fields in self._key_fields.items():
            p_secrets: dict = {"api_key": fields["key"].text().strip()}
            if "cx" in fields:
                p_secrets["cx"] = fields["cx"].text().strip()
            if "model" in fields:
                p_secrets["model"] = fields["model"].text().strip()
            secrets[p_key] = p_secrets
        return secrets
