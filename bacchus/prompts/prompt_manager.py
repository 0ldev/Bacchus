"""
Dynamic system prompt manager with hot reload support.

Loads system prompt from markdown files and watches for changes.
"""

import logging
from pathlib import Path
from typing import Optional, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent


logger = logging.getLogger(__name__)


class PromptFileHandler(FileSystemEventHandler):
    """Handles file system events for prompt files."""

    def __init__(self, prompt_manager):
        self.prompt_manager = prompt_manager

    def on_modified(self, event):
        """Called when a prompt file is modified."""
        if isinstance(event, FileModifiedEvent) and event.src_path.endswith('.md'):
            logger.info(f"Prompt file modified: {event.src_path}")
            self.prompt_manager.reload()


class PromptManager:
    """
    Manages dynamic system prompts loaded from markdown files.

    Supports hot reload - changes to markdown files are automatically detected.
    """

    # Order of prompt components
    PROMPT_FILES = [
        "identity.md",
        "soul.md",
        "constraints.md",
        "tools.md"
    ]

    def __init__(self, language: str = "en"):
        """
        Initialize prompt manager.

        Args:
            language: Language code (en or pt-BR)
        """
        self.language = language
        self.prompts_dir = Path(__file__).parent / language
        self._cached_prompt: Optional[str] = None
        self._cached_tools_content: Optional[str] = None
        self._observer: Optional[Observer] = None

        # Ensure prompts directory exists
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory not found: {self.prompts_dir}")
            self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def start_watching(self):
        """Start watching prompt files for changes."""
        if self._observer is not None:
            logger.warning("File watcher already started")
            return

        self._observer = Observer()
        handler = PromptFileHandler(self)
        self._observer.schedule(handler, str(self.prompts_dir), recursive=False)
        self._observer.start()
        logger.info(f"Started watching prompt files in {self.prompts_dir}")

    def stop_watching(self):
        """Stop watching prompt files."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Stopped watching prompt files")

    def reload(self):
        """Force reload of all prompt files."""
        logger.info("Reloading system prompt from files")
        self._cached_prompt = None
        self._cached_tools_content = None

    def set_language(self, language: str):
        """
        Change the language and reload prompts.

        Args:
            language: Language code (en or pt-BR)
        """
        if language != self.language:
            logger.info(f"Changing prompt language from {self.language} to {language}")
            self.language = language
            self.prompts_dir = Path(__file__).parent / language
            self.reload()

    def _load_prompt_file(self, filename: str) -> str:
        """
        Load content from a prompt file.

        Args:
            filename: Name of the markdown file

        Returns:
            File content or empty string if not found
        """
        file_path = self.prompts_dir / filename

        if not file_path.exists():
            logger.warning(f"Prompt file not found: {file_path}")
            return ""

        try:
            content = file_path.read_text(encoding="utf-8")
            return content.strip()
        except Exception as e:
            logger.error(f"Failed to read prompt file {file_path}: {e}")
            return ""

    def _generate_tools_section(self, mcp_manager) -> str:
        """
        Generate the tools.md section from running MCP servers.

        Args:
            mcp_manager: MCP manager instance

        Returns:
            Markdown content for tools section
        """
        if mcp_manager is None:
            return ""

        # Import here to avoid circular dependency
        from bacchus.inference.autonomous_tools import build_tool_system_prompt

        tools_content = build_tool_system_prompt(mcp_manager, self.language)

        if not tools_content:
            return ""

        return tools_content

    def get_system_prompt(self, mcp_manager=None, force_reload: bool = False) -> str:
        """
        Get the complete system prompt.

        Combines all prompt components and auto-generates tools section.

        Args:
            mcp_manager: MCP manager instance (for tool generation)
            force_reload: Force reload even if cached

        Returns:
            Complete system prompt
        """
        # Check if we can use cached version
        if not force_reload and self._cached_prompt is not None:
            # Still regenerate tools section as it may have changed
            tools_content = self._generate_tools_section(mcp_manager)

            # If tools haven't changed, return cached prompt
            if tools_content == self._cached_tools_content:
                return self._cached_prompt

        # Load all prompt files
        prompt_parts = []

        for filename in self.PROMPT_FILES:
            # Skip tools.md - we'll generate it
            if filename == "tools.md":
                continue

            content = self._load_prompt_file(filename)
            if content:
                prompt_parts.append(content)

        # Inject system context (OS, shell, paths, package managers)
        from bacchus.system_info import gather_system_info
        system_context = gather_system_info(mcp_manager)
        if system_context:
            prompt_parts.append(system_context)

        # Inject scripts directory from settings
        from bacchus.config import load_settings, expand_path
        scripts_dir = load_settings().get("permissions", {}).get(
            "scripts_dir", "%APPDATA%/Bacchus/scripts"
        )
        scripts_dir_expanded = expand_path(scripts_dir)
        prompt_parts.append(
            f"Default scripts directory: Save generated scripts to `{scripts_dir_expanded}` "
            f"unless the user specifies another location."
        )

        # Generate and append tools section
        tools_content = self._generate_tools_section(mcp_manager)
        if tools_content:
            prompt_parts.append(tools_content)
            self._cached_tools_content = tools_content

        # Combine all parts
        full_prompt = "\n\n".join(prompt_parts)

        # Cache the result
        self._cached_prompt = full_prompt

        logger.debug(f"Generated system prompt ({len(full_prompt)} characters)")

        return full_prompt

    def update_tools_file(self, mcp_manager):
        """
        Update the tools.md file with current tool information.

        This writes the auto-generated tools section to the file so users can see it.

        Args:
            mcp_manager: MCP manager instance
        """
        tools_file = self.prompts_dir / "tools.md"

        # Generate tools content
        tools_content = self._generate_tools_section(mcp_manager)

        if not tools_content:
            logger.debug("No tools available to write")
            return

        # Read existing header
        header_lines = []
        if tools_file.exists():
            content = tools_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            # Find the auto-generated marker
            for i, line in enumerate(lines):
                if "AUTO-GENERATED" in line or "AUTO-GERADO" in line:
                    header_lines = lines[:i+1]
                    break

            # If no marker found, keep everything before first tool
            if not header_lines:
                for i, line in enumerate(lines):
                    if line.strip().startswith("##") and i > 0:
                        header_lines = lines[:i]
                        break

        # If still no header, create default
        if not header_lines:
            if self.language == "pt-BR":
                header_lines = [
                    "# Ferramentas Disponíveis",
                    "",
                    "Esta seção é gerada automaticamente a partir dos servidores MCP em execução.",
                    "",
                    "<!-- AUTO-GERADO: Não edite manualmente abaixo desta linha -->"
                ]
            else:
                header_lines = [
                    "# Available Tools",
                    "",
                    "This section is automatically generated from running MCP servers.",
                    "",
                    "<!-- AUTO-GENERATED: Do not manually edit below this line -->"
                ]

        # Combine header and tools
        full_content = "\n".join(header_lines) + "\n\n" + tools_content

        try:
            tools_file.write_text(full_content, encoding="utf-8")
            logger.info(f"Updated tools file: {tools_file}")
        except Exception as e:
            logger.error(f"Failed to update tools file: {e}")


# Global instance
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager(language: str = "en") -> PromptManager:
    """
    Get or create the global prompt manager instance.

    Args:
        language: Language code (en or pt-BR)

    Returns:
        PromptManager instance
    """
    global _prompt_manager

    if _prompt_manager is None:
        _prompt_manager = PromptManager(language)
        _prompt_manager.start_watching()
    elif _prompt_manager.language != language:
        _prompt_manager.set_language(language)

    return _prompt_manager
