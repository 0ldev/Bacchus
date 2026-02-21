"""
Enhanced tool result display widget.

Provides rich, interactive display of tool execution results with:
- Visual execution indicators
- Tool-specific formatting (search, files, code execution)
- Clickable links
- Collapsible sections
"""

import json
import logging
from typing import Optional, Dict, Any, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QPushButton, QTextBrowser
)
from PyQt6.QtGui import QFont, QDesktopServices, QCursor
from PyQt6.QtCore import QUrl

from bacchus.constants import TOOL_RESULT_DISPLAY_CHARS

logger = logging.getLogger(__name__)


class ToolResultWidget(QFrame):
    """Enhanced widget for displaying tool execution results."""

    def __init__(self, tool_name: str, arguments: Dict[str, Any],
                 result: str, success: bool, duration_ms: Optional[float] = None,
                 theme: str = "light", parent=None):
        """
        Initialize tool result widget.

        Args:
            tool_name: Name of the tool that was executed
            arguments: Tool arguments
            result: Tool execution result
            success: Whether execution succeeded
            duration_ms: Execution duration in milliseconds
            theme: Current UI theme ("light" or "dark")
            parent: Parent widget
        """
        super().__init__(parent)
        self.tool_name = tool_name
        self.arguments = arguments
        self.result = result
        self.success = success
        self.duration_ms = duration_ms
        self._theme = theme

        self._expanded = False

        is_dark = (theme == "dark")
        bg = "#252525" if is_dark else "#f8f9fa"
        border = "#3d3d3d" if is_dark else "#dee2e6"

        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(f"""
            ToolResultWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(4)

        # Header with tool info (always visible, clickable to expand)
        header = self._create_header()
        layout.addWidget(header)

        # Tool-specific content (hidden by default, shown on expand)
        self._content_widget = self._create_content()
        self._content_widget.setVisible(False)
        layout.addWidget(self._content_widget)

        self.setLayout(layout)

    def _create_header(self) -> QWidget:
        """Create tool execution header (clickable to expand/collapse content)."""
        meta_color = "#888888" if self._theme == "dark" else "#6c757d"
        text_color = "#e0e0e0" if self._theme == "dark" else "#212529"

        header = QWidget()
        header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Toggle arrow
        self._toggle_label = QLabel("▶")
        self._toggle_label.setFont(QFont("Segoe UI", 9))
        self._toggle_label.setStyleSheet(f"color: {meta_color}; background: transparent;")
        header_layout.addWidget(self._toggle_label)

        # Status icon
        status_icon = "✅" if self.success else "❌"
        icon_label = QLabel(status_icon)
        icon_label.setFont(QFont("Segoe UI", 12))
        icon_label.setStyleSheet("background: transparent;")
        header_layout.addWidget(icon_label)

        # Tool name
        tool_label = QLabel(f"<b>{self.tool_name}</b>")
        tool_label.setFont(QFont("Segoe UI", 10))
        tool_label.setStyleSheet(f"color: {text_color}; background: transparent;")
        header_layout.addWidget(tool_label)

        header_layout.addStretch()

        # Duration
        if self.duration_ms is not None:
            duration_label = QLabel(f"⏱️ {self.duration_ms:.0f}ms")
            duration_label.setFont(QFont("Segoe UI", 9))
            duration_label.setStyleSheet(f"color: {meta_color}; background: transparent;")
            header_layout.addWidget(duration_label)

        header.setLayout(header_layout)

        # Make header clickable via mouse press override using event filter
        header.mousePressEvent = lambda event: self._toggle_content()

        return header

    def _toggle_content(self):
        """Toggle the visibility of the content section."""
        self._expanded = not self._expanded
        self._toggle_label.setText("▼" if self._expanded else "▶")
        self._content_widget.setVisible(self._expanded)
        self.updateGeometry()

    def _create_content(self) -> QWidget:
        """Create tool-specific content display."""
        # Route to specific formatter based on tool type
        if self.tool_name == "search_web":
            return self._create_search_content()
        elif self.tool_name == "execute_command":
            return self._create_command_content()
        elif self.tool_name in ["read_file", "write_file", "list_directory", "create_directory", "edit_file"]:
            return self._create_file_content()
        else:
            return self._create_default_content()

    def _create_search_content(self) -> QWidget:
        """Create rich search results display with clickable links."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Search query
        query = self.arguments.get("query", "")
        query_label = QLabel(f'<b>Search:</b> "{query}"')
        query_label.setWordWrap(True)
        layout.addWidget(query_label)

        # Parse and display results
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMaximumHeight(300)
        browser.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """)

        # Format result as HTML with clickable links
        html_content = self._format_search_results_html(self.result)
        browser.setHtml(html_content)

        layout.addWidget(browser)

        widget.setLayout(layout)
        return widget

    def _format_search_results_html(self, result: str) -> str:
        """Format search results as HTML with clickable links."""
        html = '<div style="font-family: Segoe UI; font-size: 10pt;">'

        lines = result.split('\n')
        current_result = []
        result_num = 0

        for line in lines:
            line = line.strip()
            if not line:
                if current_result:
                    html += self._format_single_result(current_result, result_num)
                    current_result = []
                    result_num += 1
                continue

            current_result.append(line)

        # Handle last result
        if current_result:
            html += self._format_single_result(current_result, result_num)

        html += '</div>'
        return html

    def _format_single_result(self, lines: List[str], num: int) -> str:
        """Format a single search result."""
        if not lines:
            return ""

        html = f'<div style="margin-bottom: 12px; padding: 8px; background: #f8f9fa; border-radius: 4px;">'

        title = ""
        url = ""
        snippet = []

        for line in lines:
            if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                title = line.split('. ', 1)[1] if '. ' in line else line
            elif line.startswith(('URL:', 'Source:')):
                url = line.split(':', 1)[1].strip() if ':' in line else ""
            elif line and not line.startswith(('1.', '2.', '3.', '4.', '5.', 'URL:', 'Source:')):
                snippet.append(line)

        # Title with link
        if title and url:
            html += f'<p style="margin: 0 0 4px 0;"><b><a href="{url}" style="color: #0066cc; text-decoration: none;">{title}</a></b></p>'
        elif title:
            html += f'<p style="margin: 0 0 4px 0;"><b>{title}</b></p>'

        # Snippet
        if snippet:
            snippet_text = ' '.join(snippet)
            html += f'<p style="margin: 0 0 4px 0; color: #495057;">{snippet_text}</p>'

        # URL
        if url:
            html += f'<p style="margin: 0; font-size: 9pt;"><a href="{url}" style="color: #28a745; text-decoration: none;">{url}</a></p>'

        html += '</div>'
        return html

    def _create_command_content(self) -> QWidget:
        """Create command execution display."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Command
        command = self.arguments.get("command", "")
        cmd_label = QLabel("<b>Command:</b>")
        layout.addWidget(cmd_label)

        cmd_text = QTextBrowser()
        cmd_text.setMaximumHeight(60)
        cmd_text.setPlainText(command)
        cmd_text.setStyleSheet("""
            QTextBrowser {
                background-color: #2d2d2d;
                color: #f8f8f2;
                border: 1px solid #3e3e3e;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
            }
        """)
        layout.addWidget(cmd_text)

        # Output
        output_label = QLabel("<b>Output:</b>")
        layout.addWidget(output_label)

        output_text = QTextBrowser()
        output_text.setMaximumHeight(400)
        display_result = self.result[:TOOL_RESULT_DISPLAY_CHARS]
        if len(self.result) > TOOL_RESULT_DISPLAY_CHARS:
            display_result += f"\n… [{len(self.result) - TOOL_RESULT_DISPLAY_CHARS:,} more chars not shown]"
        output_text.setPlainText(display_result)
        output_text.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
            }
        """)
        layout.addWidget(output_text)

        widget.setLayout(layout)
        return widget

    def _create_file_content(self) -> QWidget:
        """Create file operation display."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # File path
        path = self.arguments.get("path", "")
        if path:
            path_label = QLabel(f"<b>📁 Path:</b> <code>{path}</code>")
            path_label.setWordWrap(True)
            layout.addWidget(path_label)

        # Result (file tree or content)
        if self.tool_name == "list_directory":
            content = self._create_file_tree(self.result)
        else:
            content = QTextBrowser()
            content.setMaximumHeight(400)
            display_text = self.result[:TOOL_RESULT_DISPLAY_CHARS]
            if len(self.result) > TOOL_RESULT_DISPLAY_CHARS:
                display_text += f"\n… [{len(self.result) - TOOL_RESULT_DISPLAY_CHARS:,} more chars not shown]"
            content.setPlainText(display_text)
            content.setStyleSheet("""
                QTextBrowser {
                    background-color: white;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    padding: 8px;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 9pt;
                }
            """)

        layout.addWidget(content)
        widget.setLayout(layout)
        return widget

    def _create_file_tree(self, result: str) -> QWidget:
        """Create file tree view from directory listing."""
        tree = QTextBrowser()
        tree.setMaximumHeight(400)
        tree.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
            }
        """)

        # Format as tree
        html = '<div style="font-family: Consolas, monospace; font-size: 9pt;">'
        lines = result.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect file type and add icons
            if line.endswith('/') or 'DIR' in line.upper():
                icon = '📁'
                style = 'color: #0066cc; font-weight: bold;'
            elif any(line.endswith(ext) for ext in ['.py', '.js', '.ts', '.cpp', '.c', '.h']):
                icon = '📄'
                style = 'color: #28a745;'
            elif any(line.endswith(ext) for ext in ['.txt', '.md', '.json', '.yaml', '.yml']):
                icon = '📝'
                style = 'color: #6c757d;'
            else:
                icon = '📄'
                style = 'color: #495057;'

            html += f'<div style="{style}">{icon} {line}</div>'

        html += '</div>'
        tree.setHtml(html)

        return tree

    def _create_default_content(self) -> QWidget:
        """Create default content display."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Arguments
        if self.arguments:
            args_label = QLabel("<b>Arguments:</b>")
            layout.addWidget(args_label)

            args_text = QLabel(json.dumps(self.arguments, indent=2))
            args_text.setWordWrap(True)
            args_text.setStyleSheet("""
                QLabel {
                    background-color: #f8f9fa;
                    padding: 8px;
                    border-radius: 4px;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 9pt;
                }
            """)
            layout.addWidget(args_text)

        # Result
        result_label = QLabel("<b>Result:</b>")
        layout.addWidget(result_label)

        result_text = QTextBrowser()
        result_text.setMaximumHeight(400)
        display_result = self.result[:TOOL_RESULT_DISPLAY_CHARS]
        if len(self.result) > TOOL_RESULT_DISPLAY_CHARS:
            display_result += f"\n… [{len(self.result) - TOOL_RESULT_DISPLAY_CHARS:,} more chars not shown]"
        result_text.setPlainText(display_result)
        result_text.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(result_text)

        widget.setLayout(layout)
        return widget


class ToolExecutingWidget(QFrame):
    """Widget shown while a tool is executing."""

    def __init__(self, tool_name: str, arguments: Dict[str, Any], parent=None):
        """
        Initialize executing indicator.

        Args:
            tool_name: Name of the tool being executed
            arguments: Tool arguments
            parent: Parent widget
        """
        super().__init__(parent)
        self.tool_name = tool_name
        self.arguments = arguments

        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            ToolExecutingWidget {
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QHBoxLayout()

        # Spinner
        spinner = QLabel("🔄")
        spinner.setFont(QFont("Segoe UI", 14))
        layout.addWidget(spinner)

        # Message
        msg = QLabel(f"<b>Executing:</b> {tool_name}")
        msg.setFont(QFont("Segoe UI", 10))
        layout.addWidget(msg)

        layout.addStretch()

        self.setLayout(layout)
