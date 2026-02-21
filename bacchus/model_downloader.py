"""
Model downloader for Bacchus.

Handles downloading models from HuggingFace using huggingface_hub.
"""

import logging
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

from huggingface_hub import snapshot_download
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ProgressTqdm(tqdm):
    """Custom tqdm class that reports progress via callback."""

    _callback: Optional[Callable[[int, str], None]] = None
    _last_update_time: float = 0
    _update_interval: float = 0.5  # Update UI at most every 0.5 seconds

    @classmethod
    def set_callback(cls, callback: Optional[Callable[[int, str], None]]):
        """Set the progress callback function."""
        cls._callback = callback
        cls._last_update_time = 0

    def update(self, n=1):
        """Override update to call our callback."""
        super().update(n)

        # Throttle updates to avoid overwhelming the UI
        current_time = time.time()
        if current_time - self._last_update_time < self._update_interval:
            return

        self._last_update_time = current_time

        if self._callback and self.total:
            percentage = int(100 * self.n / self.total)
            # Calculate speed
            elapsed = current_time - self.start_t if self.start_t else 1
            if elapsed > 0:
                speed = self.n / elapsed
                if speed >= 1e9:
                    speed_str = f"{speed / 1e9:.1f} GB/s"
                elif speed >= 1e6:
                    speed_str = f"{speed / 1e6:.1f} MB/s"
                elif speed >= 1e3:
                    speed_str = f"{speed / 1e3:.1f} KB/s"
                else:
                    speed_str = f"{speed:.0f} B/s"
            else:
                speed_str = ""

            self._callback(percentage, speed_str)


class ModelDownloader:
    """
    Downloads models from HuggingFace Hub.
    
    Uses snapshot_download to get entire model repository.
    """
    
    def __init__(self):
        """Initialize downloader."""
        self._cancelled = False
        self._last_update_time = 0
        self._downloaded_bytes = 0
        self._total_bytes = 0
        self._start_time = 0
    
    def download_model(
        self,
        repo_id: str,
        local_dir: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        Download a model from HuggingFace Hub.
        
        Args:
            repo_id: HuggingFace repository ID (e.g., "OpenVINO/qwen2.5-3b-instruct-ov")
            local_dir: Local directory to download to
            progress_callback: Optional callback(percentage: int, speed: str)
        
        Returns:
            True if download succeeded, False if cancelled or failed
        """
        self._cancelled = False
        self._downloaded_bytes = 0
        self._total_bytes = 0
        self._start_time = time.time()
        self._last_update_time = self._start_time
        
        logger.info(f"Starting download: {repo_id} -> {local_dir}")
        
        try:
            # Create local directory
            local_dir.mkdir(parents=True, exist_ok=True)

            # Set up progress callback
            if progress_callback:
                ProgressTqdm.set_callback(progress_callback)

            # Download with progress tracking
            # Note: resume_download and local_dir_use_symlinks are deprecated
            # Downloads now always resume and never use symlinks
            # Note: Removed tqdm_class due to compatibility issues with newer huggingface_hub
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(local_dir),
            )

            # Clear callback
            ProgressTqdm.set_callback(None)
            
            # Verify download
            if not self._verify_model(local_dir):
                logger.error(f"Model verification failed: {local_dir}")
                ProgressTqdm.set_callback(None)
                return False

            # Report 100% complete
            if progress_callback:
                progress_callback(100, "Complete")

            logger.info(f"Download completed: {repo_id}")
            return True

        except Exception as e:
            logger.error(f"Download failed: {repo_id} - {e}")

            # Clear callback
            ProgressTqdm.set_callback(None)

            # Clean up partial download
            if local_dir.exists():
                try:
                    shutil.rmtree(local_dir)
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up: {cleanup_error}")

            return False
    
    def _verify_model(self, model_dir: Path) -> bool:
        """
        Verify that essential model files exist.

        Supports two layouts:
        - Standard text models:  openvino_model.xml / .bin at root
        - VL / multimodal models: openvino_language_model.xml / .bin at root

        Args:
            model_dir: Model directory to verify

        Returns:
            True if model is complete
        """
        # Standard text model layout
        if (model_dir / "openvino_model.xml").exists():
            if not (model_dir / "openvino_model.bin").exists():
                logger.error(f"Missing openvino_model.bin in {model_dir}")
                return False
            return True

        # VL / multimodal model layout (language backbone named separately)
        if (model_dir / "openvino_language_model.xml").exists():
            if not (model_dir / "openvino_language_model.bin").exists():
                logger.error(f"Missing openvino_language_model.bin in {model_dir}")
                return False
            return True

        logger.error(f"Missing openvino_model.xml in {model_dir}")
        return False
    
    def cancel(self):
        """Cancel ongoing download."""
        self._cancelled = True
        logger.info("Download cancellation requested")
    
    def is_cancelled(self) -> bool:
        """Check if download was cancelled."""
        return self._cancelled
