"""
Background worker thread for loading OpenVINO models.

Runs model_manager.load_chat_model() off the main thread so the UI
stays responsive during the (potentially multi-minute) first-time NPU
compilation step.
"""

import logging
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ModelLoadWorker(QThread):
    """
    Background thread for loading a chat model.

    Emits load_completed(success) when done.  The slot connected to this
    signal runs on the main thread, so it is safe to update the UI there.
    """

    load_completed = pyqtSignal(bool)  # True = success

    def __init__(self, model_manager: Any, model_folder_name: str, parent=None):
        """
        Args:
            model_manager: ModelManager instance.
            model_folder_name: Folder name of the model to load.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.model_manager = model_manager
        self.model_folder_name = model_folder_name

    def run(self):
        """Call load_chat_model on the background thread."""
        logger.info(f"ModelLoadWorker: loading {self.model_folder_name}")
        try:
            success = self.model_manager.load_chat_model(self.model_folder_name)
        except Exception as e:
            logger.error(f"ModelLoadWorker: unexpected error: {e}", exc_info=True)
            success = False
        logger.info(f"ModelLoadWorker: finished {self.model_folder_name} (success={success})")
        self.load_completed.emit(success)
