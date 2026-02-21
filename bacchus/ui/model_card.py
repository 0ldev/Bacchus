"""
Model card widget for model download manager.

Shows model name, size, download status, context selector, and action buttons.
Supports four display states: Downloading, Loaded, Downloaded (not loaded), Not downloaded.
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bacchus import constants, locales
from bacchus.constants import CONTEXT_SIZE_OPTIONS, DEFAULT_CONTEXT_SIZE

logger = logging.getLogger(__name__)


class ModelCard(QWidget):
    """
    Card widget for a single model showing all possible states.

    States:
    - Downloading: progress bar + Cancel
    - Loaded: green badge + Unload + context combo (disabled)
    - Downloaded, not loaded: blue badge + Load + Delete cache (conditional) + Delete model
    - Not downloaded: size info + Download (no context combo)
    """

    download_requested = pyqtSignal(str)    # Emits model_id
    cancel_requested = pyqtSignal(str)      # Emits model_id
    delete_requested = pyqtSignal(str)      # Emits model_id
    load_requested = pyqtSignal(str)        # Emits model_id
    unload_requested = pyqtSignal(str)      # Emits model_id
    context_changed = pyqtSignal(str, int)  # Emits (model_id, context_size)

    def __init__(
        self,
        model_id: str,
        display_name: str,
        size_str: str,
        repo_id: str,
        folder_name: str,
        is_loaded: bool = False,
        context_size: Optional[int] = None,
        parent=None,
    ):
        """
        Initialize model card.

        Args:
            model_id: Unique identifier for this model
            display_name: Human-readable model name
            size_str: Size string (e.g., "~2.5 GB")
            repo_id: HuggingFace repository ID
            folder_name: Local folder name for this model
            is_loaded: True if this model is currently loaded
            context_size: Configured context size (None = auto-detect from cache)
            parent: Parent widget
        """
        super().__init__(parent)

        self.model_id = model_id
        self.display_name = display_name
        self.size_str = size_str
        self.repo_id = repo_id
        self.folder_name = folder_name

        self.model_path = constants.MODELS_DIR / folder_name
        self._is_downloaded = self._check_downloaded()
        self._is_downloading = False
        self._is_loaded = is_loaded and self._is_downloaded

        # Auto-detect context size from compiled cache when not explicitly configured
        if context_size is None:
            cached = self._get_cached_sizes()
            context_size = max(cached) if cached else DEFAULT_CONTEXT_SIZE
        self._context_size = context_size

        # ── Main layout ───────────────────────────────────────────────────────
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # ── Top row: name + status badge + size ───────────────────────────────
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self.name_label = QLabel(display_name)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        top_layout.addWidget(self.name_label)

        top_layout.addStretch()

        self.badge_label = QLabel()
        top_layout.addWidget(self.badge_label)

        self.size_label = QLabel(size_str)
        self.size_label.setStyleSheet("color: #666666; font-size: 11px;")
        top_layout.addWidget(self.size_label)

        main_layout.addLayout(top_layout)

        # ── Context row (visible when downloaded or loaded) ───────────────────
        context_row = QHBoxLayout()
        context_row.setSpacing(6)

        context_label = QLabel(locales.get_string("settings.context_size", "Context:"))
        context_label.setStyleSheet("font-size: 11px; color: #666666;")
        context_row.addWidget(context_label)

        self.context_combo = QComboBox()
        for size in CONTEXT_SIZE_OPTIONS:
            self.context_combo.addItem(f"{size:,} tokens", size)
        self.context_combo.setFixedWidth(160)
        self.context_combo.currentIndexChanged.connect(self._on_context_selected)
        context_row.addWidget(self.context_combo)
        context_row.addStretch()

        self.context_widget = QWidget()
        self.context_widget.setLayout(context_row)
        main_layout.addWidget(self.context_widget)

        # ── Cache warning label ───────────────────────────────────────────────
        self.cache_warning_label = QLabel()
        self.cache_warning_label.setStyleSheet("color: #f57c00; font-size: 11px;")
        self.cache_warning_label.setWordWrap(True)
        self.cache_warning_label.hide()
        main_layout.addWidget(self.cache_warning_label)

        # ── Progress bar (downloading only) ──────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # ── Buttons row ───────────────────────────────────────────────────────
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(6)
        buttons_row.addStretch()

        self.load_button = QPushButton(locales.get_string("settings.load", "Load"))
        self.load_button.setFixedWidth(80)
        self.load_button.clicked.connect(lambda: self.load_requested.emit(self.model_id))
        buttons_row.addWidget(self.load_button)

        self.unload_button = QPushButton(locales.get_string("settings.unload", "Unload"))
        self.unload_button.setFixedWidth(80)
        self.unload_button.clicked.connect(lambda: self.unload_requested.emit(self.model_id))
        buttons_row.addWidget(self.unload_button)

        self.download_button = QPushButton(
            locales.get_string("settings.download", "Download")
        )
        self.download_button.setFixedWidth(90)
        self.download_button.clicked.connect(
            lambda: self.download_requested.emit(self.model_id)
        )
        buttons_row.addWidget(self.download_button)

        # Delete compiled cache for the selected context size
        self.delete_cache_button = QPushButton(
            locales.get_string("settings.delete_cache", "Delete cache")
        )
        self.delete_cache_button.setFixedWidth(95)
        self.delete_cache_button.setStyleSheet("color: #e65100;")
        self.delete_cache_button.clicked.connect(self._on_delete_cache_clicked)
        buttons_row.addWidget(self.delete_cache_button)

        # Delete model files from disk
        self.delete_button = QPushButton(
            locales.get_string("settings.delete_model", "Delete model")
        )
        self.delete_button.setFixedWidth(95)
        self.delete_button.setStyleSheet("color: #d32f2f;")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        buttons_row.addWidget(self.delete_button)

        self.cancel_button = QPushButton(locales.get_string("settings.cancel", "Cancel"))
        self.cancel_button.setFixedWidth(80)
        self.cancel_button.clicked.connect(
            lambda: self.cancel_requested.emit(self.model_id)
        )
        buttons_row.addWidget(self.cancel_button)

        main_layout.addLayout(buttons_row)

        self.setLayout(main_layout)

        # Card styling — background/border come from theme
        self.setStyleSheet("""
            ModelCard {
                border: 1px solid #dddddd;
                border-radius: 6px;
            }
            ModelCard:hover {
                border: 1px solid #bbbbbb;
            }
        """)

        # Sync context combo to the configured size, then update display
        self._sync_context_combo(context_size)
        self._update_display()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _check_downloaded(self) -> bool:
        """Check if model is already downloaded (any .xml file present)."""
        if not self.model_path.exists():
            return False
        return any(self.model_path.glob("*.xml"))

    def _get_cached_sizes(self) -> List[int]:
        """Return list of context sizes that have a compiled NPU cache on disk."""
        cache_dir = constants.APP_DATA_DIR / "cache"
        if not cache_dir.exists():
            return []
        sizes = []
        for size in CONTEXT_SIZE_OPTIONS:
            cache_path = cache_dir / f"{self.folder_name}_{size}"
            if cache_path.exists():
                # Consider it a valid cache only if the directory is non-empty
                try:
                    if any(cache_path.iterdir()):
                        sizes.append(size)
                except OSError:
                    pass
        return sizes

    def _cache_path_for_size(self, size: int) -> Path:
        """Return the cache directory path for a specific context size."""
        return constants.APP_DATA_DIR / "cache" / f"{self.folder_name}_{size}"

    def _refresh_combo_labels(self) -> None:
        """Update combo item labels to show which context sizes have compiled caches (✓)."""
        cached_sizes = set(self._get_cached_sizes())
        self.context_combo.blockSignals(True)
        for i in range(self.context_combo.count()):
            size = self.context_combo.itemData(i)
            if size in cached_sizes:
                self.context_combo.setItemText(i, f"{size:,} tokens  ✓")
            else:
                self.context_combo.setItemText(i, f"{size:,} tokens")
        self.context_combo.blockSignals(False)

    def _sync_context_combo(self, size: int) -> None:
        """Set context combo to *size*, snapping down to largest enabled option if needed."""
        combo_model = self.context_combo.model()

        # Try exact match (only if item is enabled)
        for i in range(self.context_combo.count()):
            if self.context_combo.itemData(i) == size:
                if combo_model.item(i).flags() & Qt.ItemFlag.ItemIsEnabled:
                    self.context_combo.blockSignals(True)
                    self.context_combo.setCurrentIndex(i)
                    self.context_combo.blockSignals(False)
                    return
                break  # found but disabled — fall through

        # Snap down: largest enabled option whose value is ≤ size
        best = -1
        for i in range(self.context_combo.count()):
            if (
                combo_model.item(i).flags() & Qt.ItemFlag.ItemIsEnabled
                and self.context_combo.itemData(i) <= size
            ):
                best = i
        if best >= 0:
            self.context_combo.blockSignals(True)
            self.context_combo.setCurrentIndex(best)
            self.context_combo.blockSignals(False)
            return

        # Fallback: first enabled item
        for i in range(self.context_combo.count()):
            if combo_model.item(i).flags() & Qt.ItemFlag.ItemIsEnabled:
                self.context_combo.blockSignals(True)
                self.context_combo.setCurrentIndex(i)
                self.context_combo.blockSignals(False)
                return

    def _update_display(self) -> None:
        """Update card display based on current state."""
        if self._is_downloading:
            # ── Downloading ──
            self.badge_label.setText("")
            self.size_label.show()
            self.progress_bar.show()
            self.context_widget.hide()
            self.cache_warning_label.hide()
            self.load_button.hide()
            self.unload_button.hide()
            self.download_button.hide()
            self.delete_cache_button.hide()
            self.delete_button.hide()
            self.cancel_button.show()

        elif self._is_loaded:
            # ── Loaded ──
            self.badge_label.setText("● Loaded")
            self.badge_label.setStyleSheet(
                "color: #4caf50; font-weight: bold; font-size: 12px;"
            )
            self.size_label.hide()
            self.progress_bar.hide()
            self.context_widget.show()
            self.context_combo.setEnabled(False)  # Requires reload to change
            self._refresh_combo_labels()
            self.load_button.hide()
            self.unload_button.show()
            self.download_button.hide()
            self.delete_cache_button.hide()  # Don't delete cache while running
            self.delete_button.hide()
            self.cancel_button.hide()
            self._update_cache_warning()

        elif self._is_downloaded:
            # ── Downloaded, not loaded ──
            self.badge_label.setText("○ Ready")
            self.badge_label.setStyleSheet(
                "color: #1976d2; font-weight: bold; font-size: 12px;"
            )
            self.size_label.hide()
            self.progress_bar.hide()
            self.context_widget.show()
            self.context_combo.setEnabled(True)
            self._refresh_combo_labels()
            self.load_button.show()
            self.unload_button.hide()
            self.download_button.hide()
            self.delete_button.show()
            self.cancel_button.hide()
            self._update_cache_warning()

        else:
            # ── Not downloaded ──
            self.badge_label.setText("")
            self.size_label.show()
            self.progress_bar.hide()
            self.context_widget.hide()
            self.cache_warning_label.hide()
            self.load_button.hide()
            self.unload_button.hide()
            self.download_button.show()
            self.delete_cache_button.hide()
            self.delete_button.hide()
            self.cancel_button.hide()

    def _update_cache_warning(self) -> None:
        """Show/hide cache warning label and Delete cache button based on selected context."""
        selected_size = self.context_combo.currentData()
        if not selected_size:
            self.cache_warning_label.hide()
            self.delete_cache_button.hide()
            return

        this_cache = self._cache_path_for_size(selected_size)

        # Delete cache button: show when cache exists for selected size and model not loaded
        self.delete_cache_button.setVisible(this_cache.exists() and not self._is_loaded)

        # Check for any cache at a different size
        cache_dir = constants.APP_DATA_DIR / "cache"
        other_cache_exists = False
        if cache_dir.exists():
            for entry in cache_dir.iterdir():
                if entry.name.startswith(f"{self.folder_name}_") and entry != this_cache:
                    other_cache_exists = True
                    break

        if this_cache.exists():
            # Cache already compiled for this size — nothing to warn about
            self.cache_warning_label.hide()
        elif other_cache_exists:
            self.cache_warning_label.setText(
                f"⚠ This size will create a new cache (~{self.size_str}) "
                "alongside the existing one"
            )
            self.cache_warning_label.show()
        else:
            self.cache_warning_label.setText(
                "⚠ First-time load: model will compile for NPU (~5–10 min)"
            )
            self.cache_warning_label.show()

    def _on_context_selected(self, index: int) -> None:
        """Handle context combo selection change (user-driven only)."""
        size = self.context_combo.currentData()
        if size:
            self._context_size = size
            self._refresh_combo_labels()
            self._update_cache_warning()
            self.context_changed.emit(self.model_id, size)

    def _on_delete_clicked(self) -> None:
        """Handle delete model button — confirms then emits signal."""
        reply = QMessageBox.question(
            self,
            locales.get_string("settings.delete_model", "Delete Model"),
            locales.get_string(
                "settings.delete_confirm",
                f"Delete {self.display_name}? You can re-download it later.",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.model_id)

    def _on_delete_cache_clicked(self) -> None:
        """Delete the compiled NPU cache for the currently selected context size."""
        selected_size = self.context_combo.currentData()
        if not selected_size:
            return

        cache_path = self._cache_path_for_size(selected_size)
        if not cache_path.exists():
            return

        reply = QMessageBox.question(
            self,
            locales.get_string("settings.delete_cache_title", "Delete Compiled Cache?"),
            locales.get_string(
                "settings.delete_cache_confirm",
                f"Delete the compiled cache for {self.display_name} "
                f"at {selected_size:,} tokens?\n\n"
                "The model will need to recompile (~5–10 min) next time it is loaded "
                "at this context size.",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            shutil.rmtree(cache_path)
            logger.info(f"Deleted cache: {cache_path}")
        except Exception as e:
            logger.error(f"Failed to delete cache {cache_path}: {e}")
            QMessageBox.critical(
                self,
                locales.get_string("error.generic", "Error"),
                f"Failed to delete cache: {e}",
            )
            return

        # Refresh combo labels and buttons
        self._refresh_combo_labels()
        self._update_cache_warning()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_loaded(self, loaded: bool) -> None:
        """
        Switch between loaded / not-loaded display.

        Args:
            loaded: True if this model is now the active loaded model
        """
        self._is_loaded = loaded and self._is_downloaded
        self._update_display()

    def set_context_size(self, size: int) -> None:
        """
        Sync combo selection to *size*.

        Args:
            size: Context size in tokens to select
        """
        self._context_size = size
        self._sync_context_combo(size)
        self._refresh_combo_labels()
        self._update_cache_warning()

    def disable_context_above(self, max_context: int) -> None:
        """
        Grey out context sizes that exceed the model's native context window.

        Args:
            max_context: Maximum supported context size for this model
        """
        combo_model = self.context_combo.model()
        for i in range(self.context_combo.count()):
            item = combo_model.item(i)
            size = self.context_combo.itemData(i)
            if size > max_context:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
        # Re-sync to make sure the current selection is still valid
        self._sync_context_combo(self._context_size)

    def set_downloading(self, downloading: bool) -> None:
        """
        Set downloading state.

        Args:
            downloading: True if download is in progress
        """
        self._is_downloading = downloading
        self._update_display()

    def set_progress(self, percentage: int, speed_str: Optional[str] = None) -> None:
        """
        Update download progress.

        Args:
            percentage: Download percentage (0-100)
            speed_str: Download speed string (e.g., "2.3 MB/s")
        """
        self.progress_bar.setValue(percentage)
        if speed_str:
            self.progress_bar.setFormat(f"{percentage}% - {speed_str}")
        else:
            self.progress_bar.setFormat(f"{percentage}%")

    def set_downloaded(self, downloaded: bool) -> None:
        """
        Set downloaded state.

        Args:
            downloaded: True if model is fully downloaded
        """
        self._is_downloaded = downloaded
        if not downloaded:
            self._is_loaded = False
        self._is_downloading = False
        self._update_display()

    def refresh_state(self) -> None:
        """Refresh downloaded state by checking filesystem."""
        self._is_downloaded = self._check_downloaded()
        if not self._is_downloaded:
            self._is_loaded = False
        self._update_display()
