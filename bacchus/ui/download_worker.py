"""
Download worker thread for model downloads.

Runs model download in background thread to keep UI responsive.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from bacchus.model_downloader import ModelDownloader

logger = logging.getLogger(__name__)


class DownloadWorker(QThread):
    """
    Background thread for downloading models.
    
    Emits progress updates and completion signals.
    """
    
    progress_updated = pyqtSignal(int, str)  # percentage, speed_str
    download_completed = pyqtSignal(bool)  # success
    
    def __init__(self, repo_id: str, local_dir: Path, parent=None):
        """
        Initialize download worker.
        
        Args:
            repo_id: HuggingFace repository ID
            local_dir: Local directory to download to
            parent: Parent QObject
        """
        super().__init__(parent)
        self.repo_id = repo_id
        self.local_dir = local_dir
        self.downloader = ModelDownloader()
    
    def run(self):
        """Run download in background thread."""
        logger.info(f"Download worker started: {self.repo_id}")
        
        def progress_callback(percentage: int, speed: str):
            """Emit progress updates to UI thread."""
            self.progress_updated.emit(percentage, speed)
        
        # Perform download
        success = self.downloader.download_model(
            repo_id=self.repo_id,
            local_dir=self.local_dir,
            progress_callback=progress_callback
        )
        
        # Emit completion
        self.download_completed.emit(success)
        
        logger.info(f"Download worker finished: {self.repo_id} (success={success})")
    
    def cancel(self):
        """Cancel the download."""
        self.downloader.cancel()
