"""
Localization module for Bacchus.

Handles loading and accessing translated strings.
"""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


_current_locale: Dict[str, Any] = {}
_current_language: str = "en"


def load_locale(language: str = "en") -> Dict[str, Any]:
    """
    Load locale strings for the specified language.

    Args:
        language: Language code ("en" or "pt-BR")

    Returns:
        Dictionary of locale strings
    """
    global _current_locale, _current_language

    locale_file = Path(__file__).parent / f"{language}.yaml"

    if not locale_file.exists():
        # Fall back to English
        locale_file = Path(__file__).parent / "en.yaml"
        language = "en"

    with open(locale_file, "r", encoding="utf-8") as f:
        _current_locale = yaml.safe_load(f)

    _current_language = language
    return _current_locale


def get_string(key: str, default: Optional[str] = None) -> str:
    """
    Get a localized string by its key path.

    Args:
        key: Dot-separated key path (e.g., "menu.file")
        default: Default value if key not found

    Returns:
        Localized string or default
    """
    parts = key.split(".")
    value = _current_locale

    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default if default is not None else key

    return str(value) if not isinstance(value, dict) else default or key


def get_section(key: str) -> Dict[str, Any]:
    """
    Get a section of locale strings.

    Args:
        key: Dot-separated key path to section

    Returns:
        Dictionary of strings in section
    """
    parts = key.split(".")
    value = _current_locale

    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return {}

    return value if isinstance(value, dict) else {}


def get_current_language() -> str:
    """Get the currently loaded language code."""
    return _current_language


# Load default locale on import
load_locale("en")
