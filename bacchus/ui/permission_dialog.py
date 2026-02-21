"""
Permission request dialog for Bacchus.

Shown when the AI tries to perform an action outside configured permissions.
User can Deny, Sandbox (risky tools only), Allow once, Allow session, or Always allow.
"""

import logging
from typing import Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Return values
ALLOW_ONCE = "allow_once"
ALLOW_ALWAYS = "allow_always"
ALLOW_SESSION = "allow_session"
SANDBOX = "sandbox"
DENY = "deny"


class PermissionDialog(QDialog):
    """
    Modal dialog asking the user to allow or deny a tool action.

    Shows what the AI wants to do and lets the user decide.
    Risky tools (write/execute) show a Sandbox option; safe tools do not.
    """

    def __init__(
        self,
        tool_name: str,
        action_description: str,
        detail: str,
        parent=None,
        risky: bool = True,
    ):
        """
        Initialize permission dialog.

        Args:
            tool_name: Name of the tool (e.g. 'read_file')
            action_description: Human-readable description (e.g. 'read a file')
            detail: Specific detail (path, command, etc.)
            parent: Parent widget
            risky: If True, show Sandbox button (5 choices). If False, 4 choices.
        """
        super().__init__(parent)
        self._result = DENY

        self.setWindowTitle("Permission Required")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("The assistant wants to " + action_description + ":")
        header.setWordWrap(True)
        header.setStyleSheet("font-size: 13px;")
        layout.addWidget(header)

        # Detail box (path, command, URL)
        detail_box = QLabel(detail)
        detail_box.setWordWrap(True)
        detail_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_box.setStyleSheet(
            "background: #f0f0f0; border: 1px solid #ccc; border-radius: 4px;"
            "padding: 8px; font-family: Consolas, monospace; font-size: 12px;"
        )
        layout.addWidget(detail_box)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #ddd;")
        layout.addWidget(sep)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        deny_btn = QPushButton("Deny")
        deny_btn.setStyleSheet(
            "QPushButton { background: #dc3545; color: white; border: none;"
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; }"
            "QPushButton:hover { background: #c82333; }"
        )
        deny_btn.clicked.connect(self._on_deny)

        btn_layout.addWidget(deny_btn)
        btn_layout.addStretch()

        if risky:
            sandbox_btn = QPushButton("Sandbox")
            sandbox_btn.setStyleSheet(
                "QPushButton { background: #fd7e14; color: white; border: none;"
                "border-radius: 4px; padding: 8px 16px; font-size: 12px; }"
                "QPushButton:hover { background: #e8690a; }"
            )
            sandbox_btn.setToolTip("Run in isolated sandbox environment")
            sandbox_btn.clicked.connect(self._on_sandbox)
            btn_layout.addWidget(sandbox_btn)

        allow_btn = QPushButton("Allow once")
        allow_btn.setStyleSheet(
            "QPushButton { background: #fff; color: #333; border: 1px solid #ccc;"
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; }"
            "QPushButton:hover { background: #f8f9fa; }"
        )
        allow_btn.clicked.connect(self._on_allow_once)
        btn_layout.addWidget(allow_btn)

        session_btn = QPushButton("Allow session")
        session_btn.setStyleSheet(
            "QPushButton { background: #17a2b8; color: white; border: none;"
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; }"
            "QPushButton:hover { background: #138496; }"
        )
        session_btn.setToolTip("Allow for the rest of this session")
        session_btn.clicked.connect(self._on_allow_session)
        btn_layout.addWidget(session_btn)

        always_btn = QPushButton("Always allow")
        always_btn.setStyleSheet(
            "QPushButton { background: #28a745; color: white; border: none;"
            "border-radius: 4px; padding: 8px 16px; font-size: 12px; }"
            "QPushButton:hover { background: #218838; }"
        )
        always_btn.clicked.connect(self._on_allow_always)
        btn_layout.addWidget(always_btn)

        layout.addLayout(btn_layout)

    def _on_deny(self):
        self._result = DENY
        self.reject()

    def _on_sandbox(self):
        self._result = SANDBOX
        self.accept()

    def _on_allow_once(self):
        self._result = ALLOW_ONCE
        self.accept()

    def _on_allow_session(self):
        self._result = ALLOW_SESSION
        self.accept()

    def _on_allow_always(self):
        self._result = ALLOW_ALWAYS
        self.accept()

    def get_result(self) -> str:
        """Return ALLOW_ONCE, ALLOW_SESSION, ALLOW_ALWAYS, SANDBOX, or DENY."""
        return self._result


def ask_permission(
    tool_name: str,
    action_description: str,
    detail: str,
    parent=None,
    risky: bool = True,
) -> str:
    """
    Show permission dialog and return result.

    Args:
        tool_name: Tool name
        action_description: What the AI wants to do
        detail: Specific path/command/URL
        parent: Parent widget
        risky: Whether to show Sandbox button

    Returns:
        ALLOW_ONCE, ALLOW_SESSION, ALLOW_ALWAYS, SANDBOX, or DENY
    """
    dialog = PermissionDialog(tool_name, action_description, detail, parent, risky=risky)
    dialog.exec()
    return dialog.get_result()
