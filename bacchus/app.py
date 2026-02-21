"""
Bacchus application entry point.

This module initializes the PyQt6 application and launches the main window.
"""

# CRITICAL: Import openvino_genai BEFORE PyQt6
# There's a conflict that causes crashes if PyQt6 is imported first
import openvino_genai as ov_genai

import logging
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from bacchus import locales
from bacchus.config import (
    ensure_directories,
    get_app_data_dir,
    get_logs_dir,
    get_settings_path,
    load_settings,
    save_settings,
)
from bacchus.constants import APP_NAME, APP_VERSION


def setup_logging() -> None:
    """Configure application logging."""
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create log file with current date
    log_file = logs_dir / f"bacchus_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"{APP_NAME} {APP_VERSION} starting")
    logger.info(f"Log file: {log_file}")


def is_first_launch() -> bool:
    """
    Check if this is the first application launch.

    Returns:
        True if settings.yaml doesn't exist
    """
    return not get_settings_path().exists()


def detect_npu() -> bool:
    """
    Detect if Intel NPU is available.

    Returns:
        True if NPU is detected
    """
    try:
        from openvino import Core
        
        core = Core()
        devices = core.available_devices
        
        logger = logging.getLogger(__name__)
        logger.info(f"Detected devices: {devices}")
        
        return "NPU" in devices
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to detect NPU: {e}")
        return False


def show_npu_warning(parent=None) -> None:
    """Show warning dialog if NPU not detected."""
    from PyQt6.QtWidgets import QMessageBox
    
    title = locales.get_string("dialog.npu_not_detected_title", "NPU Not Detected")
    text = locales.get_string("dialog.npu_not_detected_text",
        "Intel NPU was not detected on this system.\n\n"
        "Bacchus requires an Intel NPU (Neural Processing Unit) for model inference. "
        "This is available on Intel Core Ultra processors (Meteor Lake, Lunar Lake).\n\n"
        "The application will continue, but chat functionality will be unavailable."
    )
    
    QMessageBox.warning(parent, title, text)


def show_first_launch_wizard(app: QApplication) -> bool:
    """
    Show first launch wizard (language selection and model download).

    Args:
        app: QApplication instance

    Returns:
        True if wizard completed successfully
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel
    
    logger = logging.getLogger(__name__)
    
    # Language selection dialog
    dialog = QDialog()
    dialog.setWindowTitle("Bacchus")
    dialog.setModal(True)
    dialog.setFixedSize(500, 300)
    dialog.setWindowFlags(
        dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    
    layout = QVBoxLayout()
    
    # Welcome labels
    welcome_label = QLabel(locales.get_string("first_launch.welcome", "Welcome to Bacchus"))
    welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    welcome_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
    layout.addWidget(welcome_label)
    
    welcome_pt_label = QLabel(locales.get_string("first_launch.welcome_pt", "Bem-vindo ao Bacchus"))
    welcome_pt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    welcome_pt_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
    layout.addWidget(welcome_pt_label)
    
    # Choose language label
    choose_label = QLabel(
        locales.get_string("first_launch.choose_language",
            "Choose your language / Escolha seu idioma:")
    )
    choose_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    choose_label.setStyleSheet("margin: 20px;")
    layout.addWidget(choose_label)
    
    # Language buttons
    selected_language = ["en"]  # Use list to capture in closure
    
    english_btn = QPushButton(locales.get_string("first_launch.english", "English"))
    english_btn.setMinimumHeight(50)
    english_btn.clicked.connect(lambda: (
        selected_language.__setitem__(0, "en"),
        dialog.accept()
    ))
    layout.addWidget(english_btn)
    
    portuguese_btn = QPushButton(locales.get_string("first_launch.portuguese", "Português (Brasil)"))
    portuguese_btn.setMinimumHeight(50)
    portuguese_btn.clicked.connect(lambda: (
        selected_language.__setitem__(0, "pt-BR"),
        dialog.accept()
    ))
    layout.addWidget(portuguese_btn)
    
    dialog.setLayout(layout)
    
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    
    # Save language selection
    settings = load_settings()
    settings["language"] = selected_language[0]
    save_settings(settings)
    
    # Reload locale with selected language
    locales.load_locale(selected_language[0])
    
    logger.info(f"Language selected: {selected_language[0]}")
    
    # Show model download prompt if no models exist
    from bacchus.config import get_models_dir
    models_dir = get_models_dir()
    
    # Check if any chat models are downloaded
    has_models = False
    if models_dir.exists():
        # Check for known model folders
        from bacchus.constants import CHAT_MODELS
        for model_folder in CHAT_MODELS.keys():
            if (models_dir / model_folder).exists():
                has_models = True
                break
    
    if not has_models:
        # Show "No models found" dialog
        no_models_dialog = QDialog()
        no_models_dialog.setWindowTitle(locales.get_string("app.name", "Bacchus"))
        no_models_dialog.setModal(True)
        no_models_dialog.setFixedSize(400, 200)
        no_models_dialog.setWindowFlags(
            no_models_dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        no_models_layout = QVBoxLayout()
        
        # Message text
        message_label = QLabel(locales.get_string("dialog.no_models_text",
            "No chat models found.\n\n"
            "To get started, please download at least one\n"
            "chat model."
        ))
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("margin: 20px;")
        no_models_layout.addWidget(message_label)
        
        # Open settings button
        open_settings_btn = QPushButton(
            locales.get_string("dialog.open_model_settings", "Open Model Settings")
        )
        open_settings_btn.setMinimumHeight(40)
        open_settings_btn.clicked.connect(no_models_dialog.accept)
        no_models_layout.addWidget(open_settings_btn)
        
        no_models_dialog.setLayout(no_models_layout)
        
        # This dialog cannot be dismissed - must click button
        if no_models_dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        
        # TODO: Open Settings > Models tab directly
        # For now, the main window will handle this
        logger.info("User needs to download models")
    
    return True


def run_application(argv: list) -> int:
    """
    Initialize and run the Bacchus application.

    Args:
        argv: Command line arguments (typically sys.argv)

    Returns:
        Exit code (0 for success)
    """
    # Setup logging first
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # Ensure all directories exist
        ensure_directories()
        logger.info(f"Application data directory: {get_app_data_dir()}")

        # IMPORTANT: Load model BEFORE creating QApplication
        # There's a conflict between PyQt6 and OpenVINO GenAI that causes crashes
        # if QApplication is created first.

        # Load settings early (no Qt needed)
        settings = load_settings()

        # Detect NPU early
        has_npu = detect_npu()

        # Initialize model manager and load model BEFORE Qt
        from bacchus.model_manager import ModelManager

        model_manager = ModelManager()

        # Load startup model if one has been configured (must happen before QApplication!)
        # The startup model is set explicitly by the user in Settings > Models.
        startup_model = settings.get("startup_model")
        if startup_model and not is_first_launch():
            print(f"\n{'='*50}")
            print(f"  {APP_NAME} {APP_VERSION}")
            print(f"{'='*50}")
            logger.info(f"Loading startup model: {startup_model}")
            try:
                loaded = model_manager.load_chat_model(startup_model)
                if loaded:
                    logger.info(f"Startup model loaded: {startup_model}")
                else:
                    logger.warning(
                        f"Startup model '{startup_model}' failed to load — "
                        "continuing without a model"
                    )
            except Exception as e:
                logger.error(
                    f"Unexpected error loading startup model '{startup_model}': {e}",
                    exc_info=True
                )
        else:
            logger.info("No startup model configured — opening without loading a model")

        # NOW create QApplication (after model is loaded)
        app = QApplication(argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)

        # Check for first launch
        first_launch = is_first_launch()

        if first_launch:
            logger.info("First launch detected")

            # Show first launch wizard
            if not show_first_launch_wizard(app):
                logger.info("First launch wizard cancelled")
                return 1

            # Create default MCP configuration
            from bacchus.mcp import MCPManager
            manager = MCPManager()
            manager.load_configuration()

        # Load locale
        language = settings.get("language", "en")
        locales.load_locale(language)
        logger.info(f"Loaded language: {language}")

        # Apply theme
        from bacchus.theme import get_theme_stylesheet

        theme = settings.get("theme", "light")
        stylesheet = get_theme_stylesheet(theme)
        app.setStyleSheet(stylesheet)
        logger.info(f"Applied theme: {theme}")

        # Show NPU warning if not detected
        if not has_npu:
            logger.warning("NPU not detected")
            show_npu_warning()

        # Initialize MCP manager and start autostart servers
        from bacchus.mcp import MCPManager

        mcp_manager = MCPManager()
        mcp_manager.load_configuration()
        logger.info("MCP configuration loaded")

        # Ensure sandbox dir is in filesystem server's allowed_paths (handles existing configs)
        from bacchus.constants import SANDBOX_DIR
        mcp_manager.ensure_path_allowed("filesystem", str(SANDBOX_DIR), persist=False)
        logger.info(f"Sandbox dir added to filesystem allowed_paths: {SANDBOX_DIR}")

        # Start autostart servers in background
        mcp_manager.start_autostart_servers()
        logger.info("MCP autostart servers initiated")

        # Update tools.md file with current tools
        from bacchus.prompts import get_prompt_manager
        prompt_mgr = get_prompt_manager()
        prompt_mgr.update_tools_file(mcp_manager)
        logger.info("Updated tools.md file")

        # Register callback to auto-update tools.md when servers start/stop
        def update_tools_on_change():
            logger.info("MCP servers changed, updating tools.md")
            prompt_mgr.update_tools_file(mcp_manager)

        mcp_manager.on_server_change(update_tools_on_change)
        logger.info("Registered auto-update callback for tools.md")

        # Create and show main window
        from bacchus.ui.main_window import MainWindow

        main_window = MainWindow(
            model_manager=model_manager,
            mcp_manager=mcp_manager
        )
        main_window.show()

        logger.info("Application started successfully")
        
        # Start event loop
        return app.exec()
        
    except Exception as e:
        logger.exception(f"Fatal error during application startup: {e}")
        return 1
