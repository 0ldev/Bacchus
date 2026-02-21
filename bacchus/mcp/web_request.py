"""
Built-in web request MCP server for Bacchus.

Provides HTTP request capability (GET, POST) with security restrictions.
Allows LLM-created tools to fetch data from APIs.

Run as: python -m bacchus.mcp.web_request
"""

import json
import os
import sys
from typing import Any, Dict, List
import urllib.request
import urllib.error
import urllib.parse


class WebRequestServer:
    """MCP server for HTTP request operations."""

    def __init__(
        self,
        timeout: int = 10,
        max_response_size: int = 1_000_000,  # 1MB
        allowed_domains: List[str] = None,
        blocked_domains: List[str] = None
    ):
        """
        Initialize web request server.

        Args:
            timeout: Request timeout in seconds
            max_response_size: Maximum response size in bytes
            allowed_domains: If set, only these domains are allowed (whitelist)
            blocked_domains: Domains to block (blacklist)
        """
        self.timeout = timeout
        self.max_response_size = max_response_size
        self.allowed_domains = allowed_domains or []
        self.blocked_domains = blocked_domains or []
        self.user_agent = "Bacchus/0.1.0 (Windows; NPU Chat Application)"

    def _is_domain_allowed(self, url: str) -> bool:
        """
        Check if a domain is allowed.

        Args:
            url: URL to check

        Returns:
            True if domain is allowed
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Check blocked list first
            for blocked in self.blocked_domains:
                if blocked.lower() in domain:
                    return False

            # If whitelist exists, must be in whitelist
            if self.allowed_domains:
                return any(allowed.lower() in domain for allowed in self.allowed_domains)

            # No whitelist, so allowed (unless blocked)
            return True

        except Exception:
            return False

    def http_get(self, url: str, headers: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Perform HTTP GET request.

        Args:
            url: URL to fetch
            headers: Optional custom headers

        Returns:
            Result with response data or error
        """
        if not url or not url.startswith(("http://", "https://")):
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: Invalid URL. Must start with http:// or https://"
                }]
            }

        if not self._is_domain_allowed(url):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Domain not allowed for security reasons"
                }]
            }

        try:
            # Build request headers
            request_headers = {"User-Agent": self.user_agent}
            if headers:
                request_headers.update(headers)

            req = urllib.request.Request(url, headers=request_headers)

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                # Check response size
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > self.max_response_size:
                    return {
                        "content": [{
                            "type": "text",
                            "text": f"Error: Response too large (max {self.max_response_size} bytes)"
                        }]
                    }

                # Read response (with size limit)
                data = response.read(self.max_response_size)

                # Try to decode as text
                try:
                    text = data.decode('utf-8')
                except UnicodeDecodeError:
                    text = f"<binary data, {len(data)} bytes>"

                return {
                    "content": [{
                        "type": "text",
                        "text": text
                    }]
                }

        except urllib.error.HTTPError as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"HTTP Error {e.code}: {e.reason}"
                }]
            }
        except urllib.error.URLError as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Network error: {str(e.reason)}"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: {str(e)}"
                }]
            }

    def http_post(
        self,
        url: str,
        data: str = "",
        headers: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Perform HTTP POST request.

        Args:
            url: URL to post to
            data: Request body (JSON string or form data)
            headers: Optional custom headers

        Returns:
            Result with response data or error
        """
        if not url or not url.startswith(("http://", "https://")):
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: Invalid URL. Must start with http:// or https://"
                }]
            }

        if not self._is_domain_allowed(url):
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Domain not allowed for security reasons"
                }]
            }

        try:
            # Build request headers
            request_headers = {"User-Agent": self.user_agent}
            if headers:
                request_headers.update(headers)

            # Encode data
            data_bytes = data.encode('utf-8') if data else b''

            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers=request_headers,
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                # Check response size
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > self.max_response_size:
                    return {
                        "content": [{
                            "type": "text",
                            "text": f"Error: Response too large (max {self.max_response_size} bytes)"
                        }]
                    }

                # Read response
                response_data = response.read(self.max_response_size)

                try:
                    text = response_data.decode('utf-8')
                except UnicodeDecodeError:
                    text = f"<binary data, {len(response_data)} bytes>"

                return {
                    "content": [{
                        "type": "text",
                        "text": text
                    }]
                }

        except urllib.error.HTTPError as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"HTTP Error {e.code}: {e.reason}"
                }]
            }
        except urllib.error.URLError as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Network error: {str(e.reason)}"
                }]
            }
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: {str(e)}"
                }]
            }

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools."""
        return [
            {
                "name": "http_get",
                "description": "Perform HTTP GET request",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch"
                        },
                        "headers": {
                            "type": "object",
                            "description": "Optional HTTP headers",
                            "default": {}
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "http_post",
                "description": "Perform HTTP POST request",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to post to"
                        },
                        "data": {
                            "type": "string",
                            "description": "Request body (JSON or form data)"
                        },
                        "headers": {
                            "type": "object",
                            "description": "Optional HTTP headers",
                            "default": {}
                        }
                    },
                    "required": ["url"]
                }
            }
        ]


def run_server():
    """Run the web request MCP server."""
    config_json = os.environ.get("BACCHUS_MCP_CONFIG", "{}")

    try:
        config = json.loads(config_json)
        timeout = config.get("timeout", 10)
        max_response_size = config.get("max_response_size", 1_000_000)
        allowed_domains = config.get("allowed_domains", [])
        blocked_domains = config.get("blocked_domains", [])
    except json.JSONDecodeError:
        timeout = 10
        max_response_size = 1_000_000
        allowed_domains = []
        blocked_domains = []

    server = WebRequestServer(
        timeout=timeout,
        max_response_size=max_response_size,
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains
    )
    request_id = 0

    # JSON-RPC 2.0 over stdio
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            request_id = request.get("id", 0)
            method = request.get("method", "")
            params = request.get("params", {})

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "web_request",
                            "version": "0.1.0"
                        }
                    }
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": server.get_tools()}
                }
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                if tool_name == "http_get":
                    result = server.http_get(
                        arguments.get("url", ""),
                        arguments.get("headers", {})
                    )
                elif tool_name == "http_post":
                    result = server.http_post(
                        arguments.get("url", ""),
                        arguments.get("data", ""),
                        arguments.get("headers", {})
                    )
                else:
                    result = {
                        "content": [{
                            "type": "text",
                            "text": f"Error: Unknown tool '{tool_name}'"
                        }]
                    }

                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                }
            elif method == "shutdown":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                break
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_server()
