"""
Theme CSS rules for Bacchus UI components.

Provides stylesheet strings for custom widgets that need hover/focus styling
beyond what Qt's default palette provides.
"""


LIGHT_THEME_EXTRA = """
ProjectSectionHeader {
    background: transparent;
    border-radius: 4px;
    margin: 2px 2px 0px 2px;
}
ProjectSectionHeader:hover {
    background: rgba(0, 0, 0, 0.06);
}
ConversationListItem {
    border-radius: 6px;
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
    margin: 1px 2px;
}
ConversationListItem:hover {
    background: rgba(0, 0, 0, 0.05);
}
"""

DARK_THEME_EXTRA = """
ProjectSectionHeader {
    background: transparent;
    border-radius: 4px;
    margin: 2px 2px 0px 2px;
}
ProjectSectionHeader:hover {
    background: rgba(255, 255, 255, 0.08);
}
ConversationListItem {
    border-radius: 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    margin: 1px 2px;
}
ConversationListItem:hover {
    background: rgba(255, 255, 255, 0.06);
}
"""


def get_sidebar_extra_css(dark: bool = False) -> str:
    """Return extra CSS rules for sidebar widgets.

    Args:
        dark: True for dark theme rules, False for light theme rules.

    Returns:
        CSS string to append to the application or sidebar stylesheet.
    """
    return DARK_THEME_EXTRA if dark else LIGHT_THEME_EXTRA
