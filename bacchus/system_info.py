"""
System information discovery for Bacchus.

Runs at startup to gather OS, shell, and environment context.
This is injected into the system prompt so the LLM knows what paths,
commands, and package managers are available on this machine.
"""

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import List, Optional


def _detect_shell() -> str:
    """Detect the active shell."""
    if platform.system() == "Windows":
        # PSModulePath is set by PowerShell
        if os.environ.get("PSModulePath"):
            # Distinguish PowerShell 5 (Windows PowerShell) from 7+
            ps_version = os.environ.get("PSVersionTable", "")
            return "PowerShell"
        return "cmd.exe"
    else:
        shell_path = os.environ.get("SHELL", "")
        return Path(shell_path).name if shell_path else "sh"


def _detect_linux_distro() -> str:
    """Detect Linux distribution from /etc/os-release."""
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except (FileNotFoundError, IOError):
        pass

    try:
        info = platform.freedesktop_os_release()  # Python 3.10+
        return info.get("PRETTY_NAME", "Linux")
    except (AttributeError, OSError):
        pass

    return "Linux"


def _detect_package_managers() -> List[str]:
    """Detect available package managers using shutil.which (no subprocess)."""
    os_name = platform.system()

    if os_name == "Windows":
        candidates = ["winget", "choco", "scoop", "pip", "conda", "uv"]
    elif os_name == "Darwin":
        candidates = ["brew", "port", "pip", "conda", "uv"]
    else:
        candidates = [
            "apt", "apt-get", "dnf", "yum", "pacman",
            "zypper", "apk", "pip", "conda", "uv", "snap", "flatpak"
        ]

    return [mgr for mgr in candidates if shutil.which(mgr)]


def gather_system_info(mcp_manager=None) -> str:
    """
    Build a system context section for the LLM system prompt.

    Args:
        mcp_manager: Optional MCPManager to include expanded allowed paths

    Returns:
        Markdown string describing the runtime environment
    """
    lines = ["# System Context", ""]

    os_name = platform.system()

    if os_name == "Windows":
        build = platform.version()
        lines.append(f"- **OS**: Windows {platform.release()} (build {build})")
        lines.append(f"- **Shell**: {_detect_shell()}")
        lines.append("- **Path format**: Windows - use backslashes or forward slashes, with drive letter")
        lines.append("  - Example: `C:\\Users\\username\\Documents\\file.txt`")
        lines.append("- **mkdir command**: `mkdir folder_name`  (works in both cmd and PowerShell)")
        lines.append("- **Home drive**: `C:`  (most likely)")

    elif os_name == "Darwin":
        lines.append(f"- **OS**: macOS {platform.mac_ver()[0]}")
        lines.append(f"- **Shell**: {_detect_shell()}")
        lines.append("- **Path format**: Unix — forward slashes, no drive letter")
        lines.append("  - Example: `/Users/username/Documents/file.txt`")
        lines.append("- **mkdir command**: `mkdir -p folder_name`")

    else:
        distro = _detect_linux_distro()
        lines.append(f"- **OS**: {distro}")
        lines.append(f"- **Shell**: {_detect_shell()}")
        lines.append("- **Path format**: Unix — forward slashes, no drive letter")
        lines.append("  - Example: `/home/username/Documents/file.txt`")
        lines.append("- **mkdir command**: `mkdir -p folder_name`")

    # Actual home directory (fully expanded, no env vars)
    home = str(Path.home())
    lines.append(f"- **User home directory**: `{home}`")

    # Allowed filesystem paths (expanded from MCP server config)
    if mcp_manager:
        server = mcp_manager.get_server("filesystem")
        if server:
            raw_paths = server.config.get("allowed_paths", [])
            if raw_paths:
                expanded = [os.path.expandvars(p) for p in raw_paths]
                lines.append("- **Allowed file access paths** (use ONLY these for file operations):")
                for p in expanded:
                    lines.append(f"  - `{p}`")

    # Available package managers
    pkg_managers = _detect_package_managers()
    if pkg_managers:
        lines.append(f"- **Available package managers**: {', '.join(pkg_managers)}")

    lines.append("")
    return "\n".join(lines)
