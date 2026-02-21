"""
Prompt input area for Bacchus.

Contains text input, send button, document attachment, and device monitor.
"""

import logging
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QSlider,
    QSpinBox,
)
from PyQt6.QtGui import QKeyEvent, QPixmap

from bacchus import locales
from bacchus.config import load_settings, save_settings
from bacchus.constants import SUPPORTED_DOCUMENT_EXTENSIONS

# Image file extensions accepted by the attachment picker
_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}


logger = logging.getLogger(__name__)


class MultiLineInput(QTextEdit):
    """
    Multi-line text input that expands up to 5 lines.

    Enter sends message, Shift+Enter adds new line.
    """

    send_requested = pyqtSignal()  # Emitted when Enter is pressed
    history_up_requested = pyqtSignal()
    history_down_requested = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize multi-line input."""
        super().__init__(parent)

        # Set placeholder
        self.setPlaceholderText(
            locales.get_string("chat.type_message", "Type your message...")
        )

        # Style — no background-color override so theme handles it
        self.setStyleSheet("""
            QTextEdit {
                border: 1px solid #cccccc;
                border-radius: 8px;
                padding: 8px 10px;
                font-size: 13px;
            }
            QTextEdit:focus {
                border: 2px solid #4CAF50;
            }
        """)

        # Start with single line height
        self._min_height = self._calculate_height(1)
        self._max_height = self._calculate_height(5)
        self.setMinimumHeight(self._min_height)
        self.setMaximumHeight(self._max_height)
        self.setFixedHeight(self._min_height)

        # Connect text change to resize
        self.textChanged.connect(self._on_text_changed)

    def _calculate_height(self, lines: int) -> int:
        """
        Calculate widget height for given number of lines.

        Args:
            lines: Number of visible lines

        Returns:
            Height in pixels
        """
        line_height = self.fontMetrics().lineSpacing()
        padding = 24  # top + bottom padding
        return (line_height * lines) + padding

    def _on_text_changed(self):
        """Handle text change to adjust height using actual document size."""
        # document().size().height() correctly accounts for word-wrapped lines,
        # unlike lineCount() which only counts paragraph blocks.
        doc_height = int(self.document().size().height())
        padding = 24
        new_height = doc_height + padding

        # Clamp to 1–5 lines
        new_height = max(self._min_height, min(new_height, self._max_height))

        if new_height != self.height():
            self.setFixedHeight(new_height)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events."""
        # Enter without modifiers sends message
        if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.send_requested.emit()
            event.accept()
        # Up arrow for history (only if cursor is at the beginning or field is empty)
        elif event.key() == Qt.Key.Key_Up:
            cursor = self.textCursor()
            if cursor.atStart() or not self.toPlainText():
                self.history_up_requested.emit()
                event.accept()
            else:
                super().keyPressEvent(event)
        # Down arrow for history (only if cursor is at the end)
        elif event.key() == Qt.Key.Key_Down:
            cursor = self.textCursor()
            if cursor.atEnd() or not self.toPlainText():
                self.history_down_requested.emit()
                event.accept()
            else:
                super().keyPressEvent(event)
        # Shift+Enter adds new line (default behavior)
        else:
            super().keyPressEvent(event)


class DeviceMonitor(QWidget):
    """
    Device monitor showing NPU and RAM usage.

    For MVP, displays placeholder values. Full implementation requires OpenVINO integration.
    """

    def __init__(self, parent=None):
        """Initialize device monitor."""
        super().__init__(parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # NPU label
        self.npu_label = QLabel("NPU: --")
        self.npu_label.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(self.npu_label)

        # RAM label
        self.ram_label = QLabel("RAM: --")
        self.ram_label.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(self.ram_label)

        self.setLayout(layout)

        # Timer for updates (2 seconds idle)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_metrics)
        self.update_timer.start(2000)  # 2 seconds

        # Initial update
        self._update_metrics()

    def _update_metrics(self):
        """Update NPU and RAM metrics."""
        # Get RAM usage using psutil
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            ram_used_gb = mem_info.rss / (1024 ** 3)  # Convert bytes to GB

            vm = psutil.virtual_memory()
            ram_total_gb = vm.total / (1024 ** 3)

            self.ram_label.setText(f"RAM: {ram_used_gb:.1f}/{ram_total_gb:.1f} GB")
        except Exception as e:
            logger.debug(f"Failed to get RAM metrics: {e}")
            self.ram_label.setText("RAM: --")

        # NPU placeholder (requires OpenVINO integration)
        self.npu_label.setText("NPU: --")

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


class PromptArea(QWidget):
    """
    Prompt input area at bottom of chat.

    Contains document indicator, text input, send button, and device monitor.
    """

    send_message_requested = pyqtSignal(str)  # Emits message text
    document_attached = pyqtSignal(str)  # Emits file path
    document_removed = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize prompt area."""
        super().__init__(parent)

        self._attached_document: Optional[str] = None
        self._attached_image_path: Optional[str] = None
        self._is_enabled = False  # True only when a conversation is selected
        self._has_model = False   # True only when a model is loaded
        self._is_generating = False  # True while model is generating
        self._is_vlm_mode = False  # Track if current model supports vision

        # History management
        self._prompt_history: List[str] = []
        self._history_index = -1
        self._current_input_buffer = ""

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 8, 10, 10)
        main_layout.setSpacing(5)

        # Row 1: Document and image indicator row
        info_row = QHBoxLayout()

        # Document indicator (hidden by default)
        self.document_label = QLabel()
        self.document_label.setStyleSheet("""
            QLabel {
                background-color: #E8F5E9;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }
        """)
        self.document_label.hide()
        self.document_label.mousePressEvent = lambda e: self._on_remove_document()
        info_row.addWidget(self.document_label)

        # Image indicator (hidden by default)
        self.image_label = QLabel()
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #E3F2FD;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }
        """)
        self.image_label.hide()
        self.image_label.mousePressEvent = lambda e: self.clear_attached_image()
        info_row.addWidget(self.image_label)

        # Transient notice label (model loading, etc.) — hidden by default
        self.notice_label = QLabel()
        self.notice_label.setStyleSheet("""
            QLabel {
                background-color: #FFF3CD;
                color: #856404;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }
        """)
        self.notice_label.setWordWrap(True)
        self.notice_label.hide()
        info_row.addWidget(self.notice_label)

        info_row.addStretch()

        main_layout.addLayout(info_row)

        # Row 2: Generation params bar ─────────────────────────────────────
        gen_row = QHBoxLayout()
        gen_row.setContentsMargins(0, 2, 0, 2)
        gen_row.setSpacing(6)

        _label_style = "font-size: 11px; color: #888888;"

        temp_label = QLabel(locales.get_string("prompt.temperature", "Temp:"))
        temp_label.setStyleSheet(_label_style)
        gen_row.addWidget(temp_label)

        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 20)   # represents 0.0–2.0 in 0.1 steps
        self.temp_slider.setFixedWidth(90)
        gen_row.addWidget(self.temp_slider)

        self.temp_value_label = QLabel("0.7")
        self.temp_value_label.setFixedWidth(28)
        self.temp_value_label.setStyleSheet(_label_style)
        gen_row.addWidget(self.temp_value_label)

        gen_row.addSpacing(14)

        min_label = QLabel(locales.get_string("prompt.min_tokens", "Min tokens:"))
        min_label.setStyleSheet(_label_style)
        gen_row.addWidget(min_label)

        self.min_tokens_spin = QSpinBox()
        self.min_tokens_spin.setRange(0, 4096)
        self.min_tokens_spin.setSingleStep(64)
        self.min_tokens_spin.setFixedWidth(65)
        gen_row.addWidget(self.min_tokens_spin)

        gen_row.addStretch()

        # Apply a thin top separator via a container widget (hidden by default)
        self.gen_container = QWidget()
        self.gen_container.setStyleSheet(
            "QWidget { border-top: 1px solid rgba(128,128,128,0.20); }"
        )
        self.gen_container.setLayout(gen_row)
        self.gen_container.hide()
        main_layout.addWidget(self.gen_container)

        # Load initial values from settings
        self._load_gen_params()

        # Connect changes → save to settings immediately
        self.temp_slider.valueChanged.connect(self._on_temp_changed)
        self.min_tokens_spin.valueChanged.connect(self._on_min_tokens_changed)

        # Row 3: Input row — buttons align to bottom when input grows
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        # Single attachment button (documents and images)
        self.add_attachment_button = QPushButton("📎")
        self.add_attachment_button.setFixedSize(40, 40)
        self.add_attachment_button.setToolTip(
            locales.get_string("prompt.add_attachment", "Attach Document or Image")
        )
        self.add_attachment_button.clicked.connect(self._on_add_attachment)
        input_row.addWidget(self.add_attachment_button, 0, Qt.AlignmentFlag.AlignBottom)
        # Text input
        self.text_input = MultiLineInput()
        self.text_input.send_requested.connect(self._on_send_message)
        self.text_input.history_up_requested.connect(self._on_history_up)
        self.text_input.history_down_requested.connect(self._on_history_down)
        input_row.addWidget(self.text_input, 1)

        # Send button (aligned to bottom)
        self.send_button = QPushButton(locales.get_string("prompt.send", "Send"))
        self.send_button.setFixedSize(80, 40)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.send_button.clicked.connect(self._on_send_message)
        input_row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)

        # Toggle button for generation params bar (always visible, right of Send)
        self._gen_toggle_button = QPushButton("⚙")
        self._gen_toggle_button.setFixedSize(32, 32)
        self._gen_toggle_button.setCheckable(True)
        self._gen_toggle_button.setChecked(False)
        self._gen_toggle_button.setToolTip("Show/hide generation parameters (Temp, Min tokens)")
        self._gen_toggle_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #cccccc;
                border-radius: 6px;
                font-size: 14px;
                color: #888888;
                background: transparent;
            }
            QPushButton:hover { color: #444444; border-color: #aaaaaa; }
            QPushButton:checked { color: #4CAF50; border-color: #4CAF50; }
        """)
        self._gen_toggle_button.toggled.connect(self._on_toggle_gen_params)
        input_row.addWidget(self._gen_toggle_button, 0, Qt.AlignmentFlag.AlignBottom)

        main_layout.addLayout(input_row)

        self.setLayout(main_layout)

        # Update send button state
        self.text_input.textChanged.connect(self._update_send_button_state)
        self._update_send_button_state()

    def _on_history_up(self):
        """Navigate up in history."""
        if not self._prompt_history:
            return

        if self._history_index == -1:
            # Saving current input before starting navigation
            self._current_input_buffer = self.text_input.toPlainText()
            self._history_index = len(self._prompt_history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return  # Top of history

        self.text_input.setPlainText(self._prompt_history[self._history_index])
        # Move cursor to end
        cursor = self.text_input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_input.setTextCursor(cursor)

    def _on_history_down(self):
        """Navigate down in history."""
        if self._history_index == -1:
            return

        if self._history_index < len(self._prompt_history) - 1:
            self._history_index += 1
            self.text_input.setPlainText(self._prompt_history[self._history_index])
        else:
            # Back to what was typed before navigation
            self._history_index = -1
            self.text_input.setPlainText(self._current_input_buffer)

        # Move cursor to end
        cursor = self.text_input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_input.setTextCursor(cursor)

    def _update_send_button_state(self):
        """Update enabled/placeholder state for all input widgets."""
        # Text input and attachment are usable only when conversation + model + not generating
        input_usable = self._is_enabled and self._has_model and not self._is_generating
        self.text_input.setEnabled(input_usable)
        self.add_attachment_button.setEnabled(input_usable)

        # Context-aware placeholder text
        if not self._is_enabled:
            self.text_input.setPlaceholderText(
                locales.get_string("chat.no_conversation",
                                   "Select or create a conversation to start chatting")
            )
        elif not self._has_model:
            self.text_input.setPlaceholderText(
                locales.get_string("chat.no_model",
                                   "Load a model in Settings → Models to start chatting")
            )
        else:
            self.text_input.setPlaceholderText(
                locales.get_string("chat.type_message", "Type your message...")
            )

        text = self.text_input.toPlainText().strip()
        has_text = len(text) > 0
        self.send_button.setEnabled(has_text and input_usable)

        # Send button tooltip
        if not self._is_enabled:
            self.send_button.setToolTip(
                locales.get_string("prompt.no_conversation", "No conversation selected")
            )
        elif not self._has_model:
            self.send_button.setToolTip(
                locales.get_string("prompt.no_model",
                                   "No model loaded. Go to Settings > Models to download a model.")
            )
        elif self._is_generating:
            self.send_button.setToolTip(
                locales.get_string("prompt.generating", "Generating response...")
            )
        elif not has_text:
            self.send_button.setToolTip(
                locales.get_string("prompt.empty", "Type a message to send")
            )
        else:
            self.send_button.setToolTip(
                locales.get_string("prompt.send", "Send message (Enter)")
            )

    # ── Generation params helpers ─────────────────────────────────────────────

    def _load_gen_params(self) -> None:
        """Load temperature and min_new_tokens from settings into the UI widgets."""
        from bacchus.constants import DEFAULT_TEMPERATURE, DEFAULT_MIN_NEW_TOKENS
        gen = load_settings().get("generation", {})
        temp = gen.get("temperature", DEFAULT_TEMPERATURE)
        min_tok = gen.get("min_new_tokens", DEFAULT_MIN_NEW_TOKENS)

        self.temp_slider.blockSignals(True)
        self.temp_slider.setValue(int(round(temp * 10)))
        self.temp_slider.blockSignals(False)
        self.temp_value_label.setText(f"{temp:.1f}")

        self.min_tokens_spin.blockSignals(True)
        self.min_tokens_spin.setValue(min_tok)
        self.min_tokens_spin.blockSignals(False)

    def _on_temp_changed(self, value: int) -> None:
        """Handle temperature slider change — save to settings immediately."""
        temp = value / 10.0
        self.temp_value_label.setText(f"{temp:.1f}")
        s = load_settings()
        s.setdefault("generation", {})["temperature"] = temp
        save_settings(s)

    def _on_min_tokens_changed(self, value: int) -> None:
        """Handle min_new_tokens spinbox change — save to settings immediately."""
        s = load_settings()
        s.setdefault("generation", {})["min_new_tokens"] = value
        save_settings(s)

    def _on_toggle_gen_params(self, checked: bool) -> None:
        """Show or hide the generation parameters bar."""
        self.gen_container.setVisible(checked)

    # ── Attachment helpers ────────────────────────────────────────────────────

    def _on_add_attachment(self) -> None:
        """Open a unified file picker for documents and images."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            locales.get_string("prompt.select_attachment", "Select Attachment"),
            str(Path.home()),
            "All Supported (*.txt *.md *.png *.jpg *.jpeg *.webp *.bmp)",
        )

        if not file_path:
            return  # User cancelled

        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in _IMAGE_EXTENSIONS:
            # Image path
            if not self._is_vlm_mode:
                QMessageBox.warning(
                    self,
                    locales.get_string("prompt.image_not_supported", "Image not supported"),
                    locales.get_string(
                        "prompt.image_not_supported_msg",
                        "The current model is text-only and cannot process images.\n"
                        "Please attach a text document (.txt or .md) instead.",
                    ),
                )
                return
            self._attach_image(file_path)
        else:
            # Document path
            if ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                QMessageBox.warning(
                    self,
                    locales.get_string("error.generic", "Error"),
                    f"Unsupported file type: {ext}\n\nSupported: .txt, .md",
                )
                return
            self._attach_document(file_path)

    def _attach_document(self, file_path: str) -> None:
        """Attach a text document."""
        self._attached_document = file_path
        path = Path(file_path)
        filename = path.name
        if len(filename) > 20:
            filename = filename[:17] + "..."
        self.document_label.setText(f"📎 {filename} ×")
        self.document_label.setToolTip(f"{path.name}\nClick × to remove")
        self.document_label.show()
        self.document_attached.emit(file_path)
        logger.info(f"Document attached: {file_path}")

    def _on_remove_document(self):
        """Handle document removal."""
        if self._attached_document is None:
            return

        # Show confirmation
        reply = QMessageBox.question(
            self,
            locales.get_string("prompt.remove_document", "Remove Document"),
            locales.get_string("prompt.remove_document_confirm",
                             "Remove document from this conversation?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._attached_document = None
            self.document_label.hide()
            self.document_removed.emit()
            logger.info("Document removed")

    def _on_send_message(self):
        """Handle send message action."""
        text = self.text_input.toPlainText().strip()

        if not text:
            return

        # Add to history
        if not self._prompt_history or self._prompt_history[-1] != text:
            self._prompt_history.append(text)
        self._history_index = -1
        self._current_input_buffer = ""

        # Emit signal
        self.send_message_requested.emit(text)

        # Clear input
        self.text_input.clear()

        logger.info("Message sent")

    def set_enabled(self, enabled: bool):
        """
        Mark whether a conversation is currently selected.

        Args:
            enabled: True when a conversation is active
        """
        self._is_enabled = enabled
        self._update_send_button_state()

    def show_notice(self, text: str, duration_ms: int = 5000) -> None:
        """
        Show a transient notice message above the input field.

        The notice auto-hides after *duration_ms* milliseconds.

        Args:
            text: Message to display.
            duration_ms: How long to show the notice (default 5 s).
        """
        self.notice_label.setText(text)
        self.notice_label.show()
        QTimer.singleShot(duration_ms, self.notice_label.hide)

    def restore_after_blocked_send(self, text: str) -> None:
        """
        Restore *text* to the input field after a blocked send.

        PromptArea clears the input synchronously after emitting
        send_message_requested.  Call this method in the connected slot
        before returning; the restore is deferred by one event-loop tick
        so it runs after the clear.

        Args:
            text: Original message text to restore.
        """
        QTimer.singleShot(0, lambda: self.text_input.setPlainText(text))

    def clear_document(self):
        """Clear attached document without confirmation."""
        self._attached_document = None
        self.document_label.hide()

    def set_model_loaded(self, loaded: bool):
        """
        Set whether a model is loaded.

        Args:
            loaded: True if a model is loaded and ready
        """
        self._has_model = loaded
        self._update_send_button_state()

    def set_generating(self, generating: bool):
        """
        Set whether model is currently generating.

        Args:
            generating: True if model is generating a response
        """
        self._is_generating = generating
        self._update_send_button_state()

    def focus_input(self):
        """Focus the text input field."""
        self.text_input.setFocus()

    # ── VLM Image Attachment ──────────────────────────────────────────────────

    def set_vlm_mode(self, enabled: bool):
        """
        Update VLM mode flag.

        Called by MainWindow when a VLM model is loaded or unloaded.
        Images attached in non-VLM mode are rejected with a warning dialog.

        Args:
            enabled: True if a vision-language model is currently loaded
        """
        self._is_vlm_mode = enabled
        if not enabled:
            self.clear_attached_image()  # Remove any pending image when leaving VLM mode

    def get_attached_image(self) -> Optional[str]:
        """Return the currently attached image path, or None."""
        return self._attached_image_path

    def clear_attached_image(self):
        """Clear the attached image and hide the image indicator."""
        self._attached_image_path = None
        self.image_label.hide()
        logger.debug("Image attachment cleared")

    def _attach_image(self, file_path: str) -> None:
        """Attach an image file and show its thumbnail in the indicator."""
        self._attached_image_path = file_path
        path = Path(file_path)
        filename = path.name
        if len(filename) > 20:
            filename = filename[:17] + "..."

        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            thumb = pixmap.scaledToHeight(20, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(thumb)
            self.image_label.setText("")
            self.image_label.setToolTip(f"{path.name}\nClick to remove")
        else:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText(f"\U0001f5bc {filename} \u00d7")
            self.image_label.setToolTip(f"{path.name}\nClick to remove")

        self.image_label.show()
        logger.info(f"Image attached: {file_path}")
