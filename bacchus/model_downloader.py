"""
Model downloader for Bacchus.

Handles downloading models from HuggingFace using huggingface_hub.
"""

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from huggingface_hub import HfApi, snapshot_download

logger = logging.getLogger(__name__)




def _get_repo_total_bytes(repo_id: str) -> int:
    """Return the sum of all file sizes in a HuggingFace repo, or 0 on failure."""
    try:
        api = HfApi()
        info = api.model_info(repo_id, files_metadata=True)
        total = sum(
            (s.size or 0)
            for s in (info.siblings or [])
        )
        logger.info(f"Repo {repo_id} total size: {total / 1e9:.2f} GB ({len(info.siblings or [])} files)")
        return total
    except Exception as e:
        logger.warning(f"Could not fetch repo size for {repo_id}: {e}")
        return 0


def _dir_size(path: Path) -> int:
    """Return the total size in bytes of all files currently in *path*."""
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except Exception:
        pass
    return total


class ModelDownloader:
    """
    Downloads models from HuggingFace Hub.
    
    Uses snapshot_download to get entire model repository.
    """
    
    def __init__(self):
        """Initialize downloader."""
        self._cancelled = False
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
        self._start_time = time.time()

        logger.info(f"Starting download: {repo_id} -> {local_dir}")

        try:
            local_dir.mkdir(parents=True, exist_ok=True)

            # Query total repo size before starting so the poller can derive percentage.
            total_bytes = _get_repo_total_bytes(repo_id) if progress_callback else 0

            # Start a background poller that watches directory growth and fires the callback.
            stop_polling = threading.Event()
            if progress_callback and total_bytes > 0:
                def _poller():
                    prev_bytes = 0
                    prev_time = time.time()
                    while not stop_polling.wait(timeout=1.0):
                        now = time.time()
                        current = _dir_size(local_dir)
                        pct = min(99, int(100 * current / total_bytes))

                        dt = now - prev_time
                        speed = (current - prev_bytes) / dt if dt > 0 else 0
                        if speed >= 1e9:
                            speed_str = f"{speed / 1e9:.1f} GB/s"
                        elif speed >= 1e6:
                            speed_str = f"{speed / 1e6:.1f} MB/s"
                        elif speed >= 1e3:
                            speed_str = f"{speed / 1e3:.1f} KB/s"
                        else:
                            speed_str = f"{speed:.0f} B/s"

                        progress_callback(pct, speed_str)
                        prev_bytes = current
                        prev_time = now

                poller_thread = threading.Thread(target=_poller, daemon=True)
                poller_thread.start()
            else:
                poller_thread = None

            try:
                snapshot_download(
                    repo_id=repo_id,
                    local_dir=str(local_dir),
                )
            finally:
                stop_polling.set()
                if poller_thread is not None:
                    poller_thread.join(timeout=2.0)

            # Verify download
            if not self._verify_model(local_dir):
                logger.error(f"Model verification failed: {local_dir}")
                return False

            # Report 100% complete
            if progress_callback:
                progress_callback(100, "Complete")

            logger.info(f"Download completed: {repo_id}")
            return True

        except Exception as e:
            logger.error(f"Download failed: {repo_id} - {e}")

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
