"""
Configuration management for Bacchus.

Handles loading, saving, and managing application settings.
Settings are stored as YAML in %APPDATA%/Bacchus/config/settings.yaml
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml


def expand_path(path: str) -> str:
    """
    Expand environment variables in a path string.

    Supports Windows-style %VAR% and Unix-style $VAR syntax.

    Args:
        path: Path string potentially containing environment variables

    Returns:
        Path with environment variables expanded
    """
    # Expand Windows-style %VAR% variables
    def replace_windows_var(match):
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    result = re.sub(r'%([^%]+)%', replace_windows_var, path)

    # Also expand Unix-style $VAR variables
    result = os.path.expandvars(result)

    return result


def get_default_settings() -> Dict[str, Any]:
    """
    Get default application settings.

    Returns:
        Dictionary containing all default settings
    """
    return {
        "version": 1,
        "language": "en",
        "last_model": None,
        "startup_model": None,       # Model to load at startup (None = don't auto-load)
        "model_context_sizes": {},   # Per-model context window size: {folder_name: tokens}
        "window": {
            "width": 1280,
            "height": 800,
            "maximized": False,
            "x": 100,
            "y": 100
        },
        "npu": {
            "turbo_mode": True
        },
        "performance": {
            "autoload_model": False  # Disabled by default; set a startup_model to enable
        },
        "context": {
            "management": "fifo"
        },
        "permissions": {
            "scripts_dir": "%APPDATA%/Bacchus/scripts",
            "tool_policy": {
                "search_web":       "always_allow",
                "fetch_webpage":    "always_allow",
                "read_file":        "ask",
                "list_directory":   "ask",
                "write_file":       "ask",
                "edit_file":        "ask",
                "create_directory": "ask",
                "execute_command":  "ask",
            }
        }
    }


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """
    Deep merge two dictionaries.

    Values from override take precedence. Nested dicts are merged recursively.

    Args:
        base: Base dictionary
        override: Dictionary with values to override

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Load settings from YAML file.

    If the file doesn't exist or is corrupted, returns default settings.
    Partial settings are merged with defaults.

    Args:
        path: Path to settings file. If None, uses default location.

    Returns:
        Dictionary containing all settings
    """
    if path is None:
        path = get_settings_path()

    path = Path(path)
    defaults = get_default_settings()

    if not path.exists():
        return defaults

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                return defaults

            loaded = yaml.safe_load(content)
            if loaded is None:
                return defaults

            # Merge loaded settings with defaults
            return _deep_merge(defaults, loaded)

    except (yaml.YAMLError, IOError):
        # Return defaults on any error
        return defaults


def save_settings(settings: Dict[str, Any], path: Optional[Union[str, Path]] = None) -> None:
    """
    Save settings to YAML file.

    Creates parent directories if they don't exist.

    Args:
        settings: Dictionary of settings to save
        path: Path to settings file. If None, uses default location.
    """
    if path is None:
        path = get_settings_path()

    path = Path(path)

    # Create parent directories if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(settings, f, default_flow_style=False, allow_unicode=True)


def get_app_data_dir() -> Path:
    """
    Get the application data directory.

    Returns:
        Path to %APPDATA%/Bacchus
    """
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        # Fallback for non-Windows systems
        appdata = os.path.expanduser("~/.config")

    return Path(appdata) / "Bacchus"


def get_config_dir() -> Path:
    """
    Get the configuration directory.

    Returns:
        Path to config directory
    """
    return get_app_data_dir() / "config"


def get_settings_path() -> Path:
    """
    Get the path to settings.yaml.

    Returns:
        Path to settings file
    """
    return get_config_dir() / "settings.yaml"


def get_secrets_path() -> Path:
    """
    Get the path to secrets.yaml.

    Returns:
        Path to secrets file
    """
    return get_config_dir() / "secrets.yaml"


def load_secrets() -> Dict[str, Any]:
    """
    Load secrets from YAML file.
    
    Returns:
        Dictionary containing secrets
    """
    path = get_secrets_path()
    if not path.exists():
        return {}
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                return {}
            return yaml.safe_load(content) or {}
    except (yaml.YAMLError, IOError):
        return {}


def save_secrets(secrets: Dict[str, Any]) -> None:
    """
    Save secrets to YAML file.
    
    Args:
        secrets: Dictionary of secrets to save
    """
    path = get_secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(secrets, f, default_flow_style=False, allow_unicode=True)


def get_models_dir() -> Path:
    """
    Get the models directory.

    Returns:
        Path to models directory
    """
    return get_app_data_dir() / "models"


def get_logs_dir() -> Path:
    """
    Get the logs directory.

    Returns:
        Path to logs directory
    """
    return get_app_data_dir() / "logs"


def get_conversations_dir() -> Path:
    """
    Get the conversations directory.

    Returns:
        Path to conversations directory
    """
    return get_app_data_dir() / "conversations"


def get_temp_dir() -> Path:
    """
    Get the temporary files directory.

    Returns:
        Path to temp directory
    """
    return get_app_data_dir() / "temp"


def get_cache_dir() -> Path:
    """
    Get the cache directory for compiled models.

    OpenVINO can cache compiled models here to speed up subsequent loads.

    Returns:
        Path to cache directory
    """
    return get_app_data_dir() / "cache"


def ensure_directories() -> None:
    """
    Ensure all required application directories exist.

    Creates the following directories if they don't exist:
    - %APPDATA%/Bacchus/
    - %APPDATA%/Bacchus/config/
    - %APPDATA%/Bacchus/models/
    - %APPDATA%/Bacchus/logs/
    - %APPDATA%/Bacchus/conversations/
    - %APPDATA%/Bacchus/temp/
    """
    app_data = get_app_data_dir()
    directories = [
        app_data,
        get_config_dir(),
        get_models_dir(),
        get_logs_dir(),
        get_conversations_dir(),
        get_temp_dir(),
        get_cache_dir(),
        app_data / "scripts",
        app_data / "sandbox",
        app_data / "images",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
