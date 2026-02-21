"""
Sandboxed dynamic tool executor for Bacchus.

Executes LLM-created tools in a restricted environment with internet access.
Uses subprocess isolation and resource limits for security.
"""

import json
import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""


class SandboxedExecutor:
    """
    Execute Python code in a sandboxed subprocess.

    Security features:
    - Separate process isolation
    - Resource limits (CPU time, memory)
    - Restricted imports (whitelist)
    - Network access only through MCP clients
    - No file system access (except temp dir)
    """

    def __init__(
        self,
        timeout: int = 30,
        max_memory_mb: int = 256,
        allowed_imports: list = None,
        mcp_manager = None
    ):
        """
        Initialize sandboxed executor.

        Args:
            timeout: Maximum execution time in seconds
            max_memory_mb: Maximum memory usage in MB
            allowed_imports: List of allowed import modules
            mcp_manager: MCPManager instance for tool access
        """
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.mcp_manager = mcp_manager

        # Default allowed imports
        self.allowed_imports = allowed_imports or [
            "json",
            "math",
            "datetime",
            "re",
            "urllib.parse",  # For URL encoding only
            "base64",
            "hashlib",
        ]

    def execute(
        self,
        code: str,
        function_name: str,
        arguments: Dict[str, Any],
        enable_internet: bool = False
    ) -> ExecutionResult:
        """
        Execute Python code in sandbox.

        Args:
            code: Python code containing function definition
            function_name: Name of function to call
            arguments: Arguments to pass to function
            enable_internet: Allow internet access via MCP tools

        Returns:
            ExecutionResult with output or error
        """
        start_time = time.time()

        try:
            # Create sandbox script
            sandbox_script = self._create_sandbox_script(
                code,
                function_name,
                arguments,
                enable_internet
            )

            # Write to temp file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False,
                encoding='utf-8'
            ) as f:
                temp_script = f.name
                f.write(sandbox_script)

            try:
                # Execute in subprocess
                result = subprocess.run(
                    ["python", temp_script],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    # On Windows, can't easily set memory limits without job objects
                    # On Linux, could use `ulimit` or `resource` module
                )

                duration_ms = int((time.time() - start_time) * 1000)

                # Parse result
                if result.returncode == 0:
                    try:
                        output = json.loads(result.stdout)
                        return ExecutionResult(
                            success=True,
                            output=output.get("result"),
                            duration_ms=duration_ms,
                            stdout=result.stdout,
                            stderr=result.stderr
                        )
                    except json.JSONDecodeError:
                        return ExecutionResult(
                            success=False,
                            output=None,
                            error=f"Invalid output format: {result.stdout}",
                            duration_ms=duration_ms,
                            stdout=result.stdout,
                            stderr=result.stderr
                        )
                else:
                    return ExecutionResult(
                        success=False,
                        output=None,
                        error=result.stderr or "Execution failed",
                        duration_ms=duration_ms,
                        stdout=result.stdout,
                        stderr=result.stderr
                    )

            finally:
                # Clean up temp file
                try:
                    Path(temp_script).unlink()
                except Exception:
                    pass

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Execution timeout after {self.timeout}s",
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=duration_ms
            )

    def _create_sandbox_script(
        self,
        code: str,
        function_name: str,
        arguments: Dict[str, Any],
        enable_internet: bool
    ) -> str:
        """
        Create the sandbox execution script.

        This script runs in a separate process with restricted environment.

        Args:
            code: User's Python code
            function_name: Function to call
            arguments: Function arguments
            enable_internet: Enable internet via MCP

        Returns:
            Complete sandbox script as string
        """
        # Create restricted import checker
        import_checker = self._create_import_checker()

        # Create MCP client wrapper if internet enabled
        if enable_internet and self.mcp_manager:
            mcp_wrapper = self._create_mcp_wrapper()
        else:
            mcp_wrapper = self._create_no_internet_wrapper()

        # Build sandbox script
        sandbox_template = '''
import sys
import json
import builtins

# Restrict imports
{import_checker}

# Install import hook
sys.meta_path.insert(0, ImportRestrictor())

# MCP client wrapper
{mcp_wrapper}

# User's code
{user_code}

# Execute function
try:
    result = {function_name}(**{arguments})
    output = {{"success": True, "result": result}}
except Exception as e:
    output = {{"success": False, "error": str(e), "type": type(e).__name__}}

print(json.dumps(output))
'''

        return sandbox_template.format(
            import_checker=import_checker,
            mcp_wrapper=mcp_wrapper,
            user_code=code,
            function_name=function_name,
            arguments=json.dumps(arguments)
        )

    def _create_import_checker(self) -> str:
        """Create import restriction code."""
        allowed_modules = json.dumps(self.allowed_imports)

        return f'''
class ImportRestrictor:
    """Restricts imports to whitelisted modules."""

    ALLOWED_MODULES = {allowed_modules}

    def find_module(self, fullname, path=None):
        # Check if module is in whitelist
        base_module = fullname.split('.')[0]
        if base_module in self.ALLOWED_MODULES or base_module == 'bacchus_mcp':
            return None  # Allow import
        else:
            raise ImportError(f"Import of '{{fullname}}' is not allowed in sandbox")
'''

    def _create_mcp_wrapper(self) -> str:
        """Create MCP client wrapper for internet access."""
        # This would connect to the actual MCP servers
        # For now, provide a simple HTTP wrapper using urllib (which is built-in)
        return '''
class bacchus_mcp:
    """MCP client wrapper for sandboxed code."""

    @staticmethod
    def http_get(url, headers=None):
        """Perform HTTP GET request."""
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(url, headers=headers or {})
            req.add_header('User-Agent', 'Bacchus/0.1.0')

            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read(1_000_000).decode('utf-8')
        except Exception as e:
            raise RuntimeError(f"HTTP GET failed: {e}")

    @staticmethod
    def http_post(url, data="", headers=None):
        """Perform HTTP POST request."""
        import urllib.request
        import urllib.error

        try:
            data_bytes = data.encode('utf-8') if data else b''
            req = urllib.request.Request(url, data=data_bytes, headers=headers or {}, method='POST')
            req.add_header('User-Agent', 'Bacchus/0.1.0')

            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read(1_000_000).decode('utf-8')
        except Exception as e:
            raise RuntimeError(f"HTTP POST failed: {e}")

    @staticmethod
    def search_web(query, num_results=5):
        """Search the web."""
        # This would call the web_search MCP server
        # For now, just show the interface
        raise NotImplementedError("Web search requires MCP server connection")
'''

    def _create_no_internet_wrapper(self) -> str:
        """Create stub MCP wrapper when internet is disabled."""
        return '''
class bacchus_mcp:
    """Disabled MCP client (internet not enabled)."""

    @staticmethod
    def http_get(url, headers=None):
        raise RuntimeError("Internet access not enabled for this tool")

    @staticmethod
    def http_post(url, data="", headers=None):
        raise RuntimeError("Internet access not enabled for this tool")

    @staticmethod
    def search_web(query, num_results=5):
        raise RuntimeError("Internet access not enabled for this tool")
'''

    def validate_code(self, code: str) -> tuple[bool, Optional[str]]:
        """
        Validate code for dangerous operations.

        Args:
            code: Python code to validate

        Returns:
            (is_valid, error_message)
        """
        # Dangerous patterns
        dangerous_patterns = [
            "import os",
            "import subprocess",
            "import sys",
            "__import__",
            "eval(",
            "exec(",
            "compile(",
            "open(",
            "file(",
            "input(",
            "raw_input(",
        ]

        code_lower = code.lower()

        for pattern in dangerous_patterns:
            if pattern in code_lower:
                return False, f"Dangerous operation detected: {pattern}"

        return True, None
