"""
Model card widget for model download manager.

Shows model name, size, download status, and action buttons.
"""

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bacchus import constants, locales

logger = logging.getLogger(__name__)


class ModelCard(QWidget):
    """
    Card widget for a single model in the download manager.
    
    Shows model info and download/delete controls.
    """
    
    download_requested = pyqtSignal(str)  # Emits model_id
    cancel_requested = pyqtSignal(str)  # Emits model_id
    delete_requested = pyqtSignal(str)  # Emits model_id
    
    def __init__(self, model_id: str, display_name: str, size_str: str, 
                 repo_id: str, folder_name: str, parent=None):
        """
        Initialize model card.
        
        Args:
            model_id: Unique identifier for this model
            display_name: Human-readable model name
            size_str: Size string (e.g., "2.1 GB")
            repo_id: HuggingFace repository ID
            folder_name: Local folder name for this model
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.model_id = model_id
        self.display_name = display_name
        self.size_str = size_str
        self.repo_id = repo_id
        self.folder_name = folder_name
        
        # Check if model is downloaded
        self.model_path = constants.MODELS_DIR / folder_name
        self._is_downloaded = self._check_downloaded()
        self._is_downloading = False
        
        # Layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Top row: Name and size
        top_layout = QHBoxLayout()
        
        self.name_label = QLabel(display_name)
        self.name_label.setStyleSheet("font-weight: bold;")
        top_layout.addWidget(self.name_label)
        
        top_layout.addStretch()
        
        self.size_label = QLabel(size_str)
        self.size_label.setStyleSheet("color: #666;")
        top_layout.addWidget(self.size_label)
        
        main_layout.addLayout(top_layout)
        
        # Bottom row: Status/Progress and action button
        bottom_layout = QHBoxLayout()
        
        # Status label or progress bar
        self.status_label = QLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.hide()
        
        bottom_layout.addWidget(self.status_label, 1)
        bottom_layout.addWidget(self.progress_bar, 1)
        
        # Action button
        self.action_button = QPushButton()
        self.action_button.setFixedWidth(100)
        self.action_button.clicked.connect(self._on_action_clicked)
        bottom_layout.addWidget(self.action_button)
        
        main_layout.addLayout(bottom_layout)
        
        self.setLayout(main_layout)
        
        # Styling
        self.setStyleSheet("""
            ModelCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            ModelCard:hover {
                border: 1px solid #bbb;
            }
        """)
        
        # Update display
        self._update_display()
    
    def _check_downloaded(self) -> bool:
        """Check if model is already downloaded."""
        if not self.model_path.exists():
            return False
        
        # Verify essential files exist
        xml_file = self.model_path / "openvino_model.xml"
        bin_file = self.model_path / "openvino_model.bin"
        
        return xml_file.exists() and bin_file.exists()
    
    def _update_display(self):
        """Update card display based on state."""
        if self._is_downloading:
            # Downloading state
            self.status_label.hide()
            self.progress_bar.show()
            self.action_button.setText(
                locales.get_string("settings.cancel", "Cancel")
            )
        elif self._is_downloaded:
            # Downloaded state
            self.status_label.setText("✓ " + locales.get_string(
                "settings.downloaded", "Downloaded"
            ))
            self.status_label.setStyleSheet("color: #4caf50; font-weight: bold;")
            self.status_label.show()
            self.progress_bar.hide()
            self.action_button.setText(
                locales.get_string("settings.delete", "Delete")
            )
        else:
            # Not downloaded state
            self.status_label.setText("")
            self.status_label.show()
            self.progress_bar.hide()
            self.action_button.setText(
                locales.get_string("settings.download", "Download")
            )
    
    def _on_action_clicked(self):
        """Handle action button click."""
        if self._is_downloading:
            # Cancel download
            self.cancel_requested.emit(self.model_id)
        elif self._is_downloaded:
            # Delete model
            from PyQt6.QtWidgets import QMessageBox
            
            reply = QMessageBox.question(
                self,
                locales.get_string("settings.delete_model", "Delete Model"),
                locales.get_string("settings.delete_confirm", 
                    f"Delete {self.display_name}? You can re-download it later."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.delete_requested.emit(self.model_id)
        else:
            # Start download
            self.download_requested.emit(self.model_id)
    
    def set_downloading(self, downloading: bool):
        """
        Set downloading state.
        
        Args:
            downloading: True if download is in progress
        """
        self._is_downloading = downloading
        self._update_display()
    
    def set_progress(self, percentage: int, speed_str: Optional[str] = None):
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
    
    def set_downloaded(self, downloaded: bool):
        """
        Set downloaded state.
        
        Args:
            downloaded: True if model is fully downloaded
        """
        self._is_downloaded = downloaded
        self._is_downloading = False
        self._update_display()
    
    def refresh_state(self):
        """Refresh downloaded state by checking filesystem."""
        self._is_downloaded = self._check_downloaded()
        self._update_display()
