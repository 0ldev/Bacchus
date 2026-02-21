"""
MCP Server Manager for Bacchus.

Manages lifecycle of MCP servers: starting, stopping, monitoring status.
Loads server configuration from mcp_servers.yaml.
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

import yaml

from bacchus.config import get_config_dir, load_secrets
from bacchus.constants import MCP_SERVER_STARTUP_TIMEOUT_SECONDS
from bacchus.mcp.client import MCPClient


logger = logging.getLogger(__name__)


@dataclass
class MCPServer:
    """Configuration and state for an MCP server."""
    name: str
    command: str
    autostart: bool
    builtin: bool
    config: Dict
    status: str = "stopped"  # "stopped", "starting", "running", "error"
    process: Optional[subprocess.Popen] = None
    client: Optional[MCPClient] = None
    error_message: Optional[str] = None


class MCPManager:
    """
    Manages MCP server processes.

    Handles server lifecycle: starting, stopping, monitoring.
    Thread-safe for concurrent access.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize MCP manager.

        Args:
            config_path: Path to mcp_servers.yaml. If None, uses default location.
        """
        self._servers: Dict[str, MCPServer] = {}
        self._lock = Lock()
        self._config_path = config_path or self._get_default_config_path()
        self._server_change_callbacks = []  # Callbacks for when servers start/stop

    def on_server_change(self, callback):
        """
        Register a callback to be called when servers start or stop.

        Args:
            callback: Function to call when server state changes. Will be called with no arguments.
        """
        self._server_change_callbacks.append(callback)

    def _notify_server_change(self):
        """Notify all registered callbacks that server state changed."""
        for callback in self._server_change_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in server change callback: {e}")

    @staticmethod
    def _get_default_config_path() -> Path:
        """Get default path to mcp_servers.yaml."""
        return get_config_dir() / "mcp_servers.yaml"

    def load_configuration(self) -> None:
        """
        Load server configuration from YAML file.

        If file doesn't exist, creates it with default configuration.
        """
        if not self._config_path.exists():
            logger.info("MCP config not found, creating default configuration")
            self._create_default_config()

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "servers" not in data:
                logger.warning("Invalid MCP config, using defaults")
                self._create_default_config()
                return

            with self._lock:
                self._servers.clear()
                for server_data in data["servers"]:
                    server = MCPServer(
                        name=server_data.get("name", ""),
                        command=server_data.get("command", ""),
                        autostart=server_data.get("autostart", False),
                        builtin=server_data.get("builtin", False),
                        config=server_data.get("config", {})
                    )
                    self._servers[server.name] = server

            logger.info(f"Loaded {len(self._servers)} MCP server configurations")

        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            self._create_default_config()

    def _create_default_config(self) -> None:
        """Create default mcp_servers.yaml configuration."""
        default_config = {
            "servers": [
                {
                    "name": "filesystem",
                    "command": "python -m bacchus.mcp.filesystem",
                    "autostart": True,
                    "builtin": True,
                    "config": {
                        "allowed_paths": [
                            "%USERPROFILE%/Documents",
                            "%USERPROFILE%/Desktop",
                            "%APPDATA%/Bacchus/sandbox",
                        ]
                    }
                },
                {
                    "name": "cmd",
                    "command": "python -m bacchus.mcp.commandline",
                    "autostart": True,
                    "builtin": True,
                    "config": {
                        "timeout": 30,
                        "blocked_commands": [
                            "rm", "rmdir", "del", "format", "shutdown", "reboot"
                        ]
                    }
                },
                {
                    "name": "web_search",
                    "command": "python -m bacchus.mcp.web_search",
                    "autostart": True,
                    "builtin": True,
                    "config": {
                        "provider": "duckduckgo",
                        "max_results": 10,
                        "timeout": 10,
                        "fetch_max_length": 8000
                    }
                }
            ]
        }

        # Ensure directory exists
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"Created default MCP config at {self._config_path}")

        # Load the config we just created
        with self._lock:
            self._servers.clear()
            for server_data in default_config["servers"]:
                server = MCPServer(
                    name=server_data["name"],
                    command=server_data["command"],
                    autostart=server_data["autostart"],
                    builtin=server_data["builtin"],
                    config=server_data["config"]
                )
                self._servers[server.name] = server

    def start_server(self, server_name: str) -> bool:
        """
        Start an MCP server.

        Args:
            server_name: Name of the server to start

        Returns:
            True if server started successfully
        """
        with self._lock:
            if server_name not in self._servers:
                logger.error(f"Server '{server_name}' not found")
                return False

            server = self._servers[server_name]

            if server.status == "running":
                logger.warning(f"Server '{server_name}' already running")
                return True

            server.status = "starting"
            server.error_message = None

        try:
            # Start server process with config passed via environment
            env = os.environ.copy()
            env["BACCHUS_MCP_CONFIG"] = json.dumps(server.config)
            
            # Inject secrets
            secrets = load_secrets()
            env["BACCHUS_MCP_SECRETS"] = json.dumps(secrets)
            
            process = subprocess.Popen(
                server.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )

            # Create client
            client = MCPClient(process, server_name)

            # Initialize connection
            start_time = time.time()
            initialized = False

            while time.time() - start_time < MCP_SERVER_STARTUP_TIMEOUT_SECONDS:
                if process.poll() is not None:
                    # Process died
                    stderr = process.stderr.read()
                    raise RuntimeError(f"Server process died: {stderr}")

                try:
                    if client.initialize():
                        initialized = True
                        break
                except Exception as e:
                    # Retry
                    time.sleep(0.5)
                    continue

            if not initialized:
                process.terminate()
                raise TimeoutError(
                    f"Server did not respond within {MCP_SERVER_STARTUP_TIMEOUT_SECONDS}s"
                )

            # List available tools
            client.list_tools()

            with self._lock:
                server.process = process
                server.client = client
                server.status = "running"

            logger.info(f"Server '{server_name}' started successfully")

            # Notify callbacks that server state changed
            self._notify_server_change()

            return True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to start server '{server_name}': {error_msg}")

            with self._lock:
                server.status = "error"
                server.error_message = error_msg
                server.process = None
                server.client = None

            return False

    def stop_server(self, server_name: str) -> bool:
        """
        Stop an MCP server.

        Args:
            server_name: Name of the server to stop

        Returns:
            True if server stopped successfully
        """
        with self._lock:
            if server_name not in self._servers:
                logger.error(f"Server '{server_name}' not found")
                return False

            server = self._servers[server_name]

            if server.status != "running":
                logger.warning(f"Server '{server_name}' not running")
                return True

            # Shutdown gracefully
            if server.client:
                try:
                    server.client.shutdown()
                except Exception:
                    pass

            # Terminate process
            if server.process:
                try:
                    server.process.terminate()
                    server.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.process.kill()
                except Exception as e:
                    logger.error(f"Error terminating server '{server_name}': {e}")

            server.status = "stopped"
            server.process = None
            server.client = None

        logger.info(f"Server '{server_name}' stopped")

        # Notify callbacks that server state changed
        self._notify_server_change()

        return True

    def start_autostart_servers(self) -> None:
        """Start all servers configured with autostart=True."""
        with self._lock:
            autostart_servers = [
                name for name, server in self._servers.items()
                if server.autostart
            ]

        for server_name in autostart_servers:
            logger.info(f"Auto-starting server '{server_name}'")
            success = self.start_server(server_name)
            if not success:
                logger.warning(
                    f"Auto-start failed for '{server_name}', continuing anyway"
                )

    def stop_all_servers(self) -> None:
        """Stop all running servers."""
        with self._lock:
            running_servers = [
                name for name, server in self._servers.items()
                if server.status == "running"
            ]

        for server_name in running_servers:
            self.stop_server(server_name)

    def get_server(self, server_name: str) -> Optional[MCPServer]:
        """
        Get server by name.

        Args:
            server_name: Name of the server

        Returns:
            MCPServer object or None if not found
        """
        with self._lock:
            return self._servers.get(server_name)

    def list_servers(self) -> List[MCPServer]:
        """
        Get list of all configured servers.

        Returns:
            List of MCPServer objects
        """
        with self._lock:
            return list(self._servers.values())

    def get_client(self, server_name: str) -> Optional[MCPClient]:
        """
        Get MCP client for a running server.

        Args:
            server_name: Name of the server

        Returns:
            MCPClient object or None if server not running
        """
        with self._lock:
            server = self._servers.get(server_name)
            if server and server.status == "running":
                return server.client
            return None

    def is_server_running(self, server_name: str) -> bool:
        """
        Check if a server is running.

        Args:
            server_name: Name of the server

        Returns:
            True if server is running
        """
        with self._lock:
            server = self._servers.get(server_name)
            return server.status == "running" if server else False

    def ensure_path_allowed(
        self, server_name: str, path: str, persist: bool = False
    ) -> bool:
        """
        Ensure a path is in the server's allowed_paths.

        If the path is already covered by an existing allowed entry, returns True
        immediately without restarting. Otherwise adds the path, restarts the server
        if it is currently running, and optionally persists the change to YAML.

        Args:
            server_name: Server name (typically 'filesystem')
            path: Absolute path to add (env vars are expanded for comparison)
            persist: If True, also write the change to mcp_servers.yaml

        Returns:
            True if the path is now allowed
        """
        import os
        from pathlib import Path as _P

        def _resolve(p: str) -> str:
            try:
                return str(_P(os.path.expandvars(p)).resolve())
            except Exception:
                return p

        with self._lock:
            server = self._servers.get(server_name)
            if not server:
                return False

            allowed = list(server.config.get("allowed_paths", []))
            norm_new = _resolve(path)

            # Check whether the path is already covered
            for existing in allowed:
                try:
                    _P(norm_new).relative_to(_resolve(existing))
                    return True  # Already within an allowed directory
                except ValueError:
                    continue

            # Not covered — add it
            allowed.append(path)
            new_config = dict(server.config)
            new_config["allowed_paths"] = allowed
            server.config = new_config

        if persist:
            return self.save_server_config(server_name, new_config)

        # In-memory only: restart if running so the subprocess picks up the new env
        if self.is_server_running(server_name):
            self.stop_server(server_name)
            return self.start_server(server_name)

        return True

    def save_server_config(self, server_name: str, config: Dict) -> bool:
        """
        Update server config, persist to YAML, and restart if running.

        Args:
            server_name: Name of the server to update
            config: New config dict

        Returns:
            True if saved successfully
        """
        with self._lock:
            if server_name not in self._servers:
                logger.error(f"Server '{server_name}' not found")
                return False
            self._servers[server_name].config = config

        # Persist to YAML
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for server_data in data.get("servers", []):
                if server_data.get("name") == server_name:
                    server_data["config"] = config
                    break

            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Saved config for server '{server_name}'")
        except Exception as e:
            logger.error(f"Failed to save config for '{server_name}': {e}")
            return False

        # Restart server if it was running so new config takes effect
        was_running = self.is_server_running(server_name)
        if was_running:
            self.stop_server(server_name)
            return self.start_server(server_name)

        return True
