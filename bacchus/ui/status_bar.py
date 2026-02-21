"""
Status bar widget for Bacchus.

Displays model status, MCP server status, RAM usage, and NPU usage.
All sections are clickable to open relevant settings tabs.
"""

import logging
from typing import Optional

import psutil
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from bacchus import locales

logger = logging.getLogger(__name__)

# Status bar height
STATUS_BAR_HEIGHT = 24


class StatusBar(QWidget):
    """
    Status bar at bottom of main window.
    
    Shows model status, MCP servers, RAM, and NPU usage.
    Sections are clickable to open settings.
    """
    
    model_clicked = pyqtSignal()  # Open Settings > Models
    mcp_clicked = pyqtSignal()  # Open Settings > MCP
    
    def __init__(self, parent=None):
        """Initialize status bar."""
        super().__init__(parent)

        self._current_model: Optional[str] = None
        self._active_device: Optional[str] = None  # NPU, CPU, etc.
        self._mcp_servers: dict[str, str] = {}  # server_name -> status
        self._loading: bool = False
        self._loading_name: str = ""
        self._loading_dots: int = 0
        self._loading_timer = QTimer()
        self._loading_timer.timeout.connect(self._tick_loading)
        
        # Fixed height
        self.setFixedHeight(STATUS_BAR_HEIGHT)
        
        # Main layout
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)
        
        # Model indicator (clickable)
        self.model_label = QLabel()
        self.model_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_label.mousePressEvent = lambda e: self.model_clicked.emit()
        self.model_label.setStyleSheet("QLabel:hover { background-color: #e0e0e0; }")
        layout.addWidget(self.model_label)
        
        # Divider
        layout.addWidget(self._create_divider())
        
        # MCP status (clickable)
        self.mcp_label = QLabel()
        self.mcp_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mcp_label.mousePressEvent = lambda e: self.mcp_clicked.emit()
        self.mcp_label.setStyleSheet("QLabel:hover { background-color: #e0e0e0; }")
        layout.addWidget(self.mcp_label)
        
        # Divider
        layout.addWidget(self._create_divider())
        
        # RAM usage
        self.ram_label = QLabel()
        layout.addWidget(self.ram_label)
        
        # Divider
        layout.addWidget(self._create_divider())
        
        # NPU usage
        self.npu_label = QLabel()
        layout.addWidget(self.npu_label)
        
        # Stretch to push everything left
        layout.addStretch()
        
        self.setLayout(layout)
        
        # Styling
        self.setStyleSheet("""
            StatusBar {
                background-color: #f5f5f5;
                border-top: 1px solid #ddd;
            }
            QLabel {
                color: #333;
                font-size: 11px;
                padding: 0 8px;
            }
        """)
        
        # Initialize displays
        self._update_model_display()
        self._update_mcp_display()
        self._update_resource_displays()
        
        # Update timer for resource monitoring
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_resource_displays)
        self.update_timer.start(2000)  # 2 seconds
        
        logger.info("Status bar initialized")
    
    def _create_divider(self) -> QLabel:
        """Create a vertical divider."""
        divider = QLabel("|")
        divider.setStyleSheet("color: #ccc; padding: 0;")
        return divider
    
    def _update_model_display(self):
        """Update model indicator display."""
        if self._current_model:
            device_str = f" ({self._active_device})" if self._active_device else ""
            text = f"Model: {self._current_model}{device_str}"
        else:
            text = locales.get_string("status.no_model", "Model: None")

        self.model_label.setText(text)
        self.model_label.setToolTip(
            locales.get_string("status.model_tooltip", "Click to open Settings > Models")
        )
    
    def _update_mcp_display(self):
        """Update MCP server status display."""
        if not self._mcp_servers:
            text = "MCP: " + locales.get_string("status.no_servers", "None")
        else:
            # Format: "MCP: filesystem ✓  cmd ✓"
            server_strs = []
            for name, status in self._mcp_servers.items():
                if status == "running":
                    icon = "✓"
                    color = "green"
                elif status == "failed" or status == "stopped":
                    icon = "✗"
                    color = "red"
                else:  # not_configured
                    icon = "○"
                    color = "gray"
                
                server_strs.append(f"{name} {icon}")
            
            text = "MCP: " + "  ".join(server_strs)
        
        self.mcp_label.setText(text)
        self.mcp_label.setToolTip(
            locales.get_string("status.mcp_tooltip", "Click to open Settings > MCP")
        )
    
    def _update_resource_displays(self):
        """Update RAM and NPU usage displays."""
        # RAM usage
        try:
            process = psutil.Process()
            mem_info = process.memory_info()
            app_ram_gb = mem_info.rss / (1024 ** 3)  # Convert to GB
            
            virtual_mem = psutil.virtual_memory()
            total_ram_gb = virtual_mem.total / (1024 ** 3)
            
            ram_text = f"RAM: {app_ram_gb:.1f}/{total_ram_gb:.1f} GB"
            self.ram_label.setText(ram_text)
        except Exception as e:
            logger.error(f"Failed to update RAM display: {e}")
            self.ram_label.setText("RAM: --")
        
        # NPU usage (placeholder - requires OpenVINO integration)
        self.npu_label.setText("NPU: --")
        self.npu_label.setToolTip(
            locales.get_string("status.npu_pending", "NPU monitoring requires model to be loaded")
        )
    
    def set_model(self, model_name: Optional[str], device: Optional[str] = None):
        """
        Set the current model name and device.

        Args:
            model_name: Name of loaded model, or None if no model
            device: Device used for inference (e.g., "NPU", "CPU")
        """
        self._current_model = model_name
        self._active_device = device
        self._loading = False
        self._loading_timer.stop()
        self._update_model_display()
        logger.info(f"Status bar model updated: {model_name} on {device}")

    def set_loading(self, loading: bool, display_name: str = "") -> None:
        """
        Show/hide an animated loading indicator in the model label.

        Args:
            loading: True to start animation, False to stop
            display_name: Short model name shown in the animation
        """
        if loading:
            self._loading = True
            self._loading_name = display_name
            self._loading_dots = 0
            self._loading_timer.start(600)
            self._tick_loading()
        else:
            self._loading = False
            self._loading_timer.stop()
            self._update_model_display()

    def _tick_loading(self) -> None:
        """Advance the animated ellipsis on the loading label."""
        dots = "." * (self._loading_dots % 4)
        self._loading_dots += 1
        name = self._loading_name or "model"
        self.model_label.setText(f"⏳ Loading {name}{dots}")
    
    def set_mcp_servers(self, servers: dict[str, str]):
        """
        Set MCP server statuses.
        
        Args:
            servers: Dict of server_name -> status
                     status can be: "running", "failed", "stopped", "not_configured"
        """
        self._mcp_servers = servers.copy()
        self._update_mcp_display()
        logger.debug(f"Status bar MCP updated: {servers}")
    
    def set_active(self, active: bool):
        """
        Set active state (changes update frequency).
        
        Args:
            active: True if inference is running
        """
        if active:
            self.update_timer.setInterval(500)  # 500ms during inference
        else:
            self.update_timer.setInterval(2000)  # 2s idle
