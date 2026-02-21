"""
Dynamic system prompt management.

Loads prompts from markdown files with hot reload support.
"""

from bacchus.prompts.prompt_manager import PromptManager, get_prompt_manager

__all__ = ["PromptManager", "get_prompt_manager"]
