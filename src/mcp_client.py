"""
MCP Client - JSON-RPC stdio communication with Lark MCP server.

This module spawns the Lark MCP server process and provides a Python interface
to call Lark API tools via the Model Context Protocol.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.config import get_lark_mcp_config


@dataclass
class MCPClient:
    """
    Client that spawns and communicates with the Lark MCP server.
    
    Usage:
        with MCPClient() as client:
            result = client.call_tool("bitable_v1_app_create", {"data": {"name": "My App"}})
    """
    
    process: Optional[subprocess.Popen] = field(default=None, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    
    def __enter__(self) -> "MCPClient":
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
    
    def start(self) -> None:
        """Start the MCP server process and initialize the connection."""
        if self.process is not None:
            return
        
        cfg = get_lark_mcp_config()
        
        cmd = [
            "npx", "-y", "@larksuiteoapi/lark-mcp", "mcp",
            "-a", cfg.client_id,
            "-s", cfg.client_secret,
            "-d", cfg.domain,
        ]
        if cfg.use_oauth:
            cmd.append("--oauth")
        
        # Force UTF-8 encoding
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        
        # Initialize MCP protocol
        self._initialize()
    
    def stop(self) -> None:
        """Terminate the MCP server process."""
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            finally:
                self.process = None
                self._initialized = False
    
    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id
    
    def _send(self, message: dict) -> None:
        """Send a JSON-RPC message to the server."""
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("MCP client not started")
        
        line = json.dumps(message) + "\n"
        self.process.stdin.write(line)
        self.process.stdin.flush()
    
    def _recv(self, expected_id: Optional[int] = None, timeout: float = 60.0) -> dict:
        """
        Receive a JSON-RPC response from the server.
        
        If expected_id is provided, skip notifications until we get a response with that id.
        """
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("MCP client not started")
        
        start = time.time()
        while True:
            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for response (id={expected_id})")
            
            line = self.process.stdout.readline()
            if not line:
                # Check if process died
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    raise RuntimeError(f"MCP server process exited unexpectedly: {stderr}")
                continue
            
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # If we're waiting for a specific id, skip notifications
            if expected_id is not None:
                if msg.get("id") == expected_id:
                    return msg
                # Skip notifications and other responses
                continue
            
            return msg
    
    def _initialize(self) -> None:
        """Perform MCP protocol initialization handshake."""
        if self._initialized:
            return
        
        # 1. Send initialize request
        init_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "github-auto-lark", "version": "1.0.0"}
            }
        })
        
        # Wait for initialize response
        self._recv(expected_id=init_id, timeout=30.0)
        
        # 2. Send initialized notification
        self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })
        
        self._initialized = True
    
    def call_tool(self, tool_name: str, arguments: dict, timeout: float = 60.0) -> Any:
        """
        Call a Lark MCP tool and return the result.
        
        Args:
            tool_name: The tool name (e.g., "bitable_v1_app_create")
            arguments: The tool arguments (matches the tool's inputSchema)
            timeout: Maximum time to wait for response
        
        Returns:
            The tool result (parsed from JSON)
        
        Raises:
            RuntimeError: If the tool call fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")
        
        # Tool names don't have a prefix in the standalone MCP server
        full_name = tool_name
        
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": full_name,
                "arguments": arguments
            }
        })
        
        response = self._recv(expected_id=req_id, timeout=timeout)
        
        if "error" in response:
            raise RuntimeError(f"Tool call failed: {response['error']}")
        
        result = response.get("result", {})
        
        # The MCP server wraps results in a content array
        content = result.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text = first.get("text", "{}")
                try:
                    parsed = json.loads(text)
                    # Check for Lark API errors in the response
                    # Lark errors have "code" explicitly set to a non-zero integer
                    if isinstance(parsed, dict) and "code" in parsed and parsed["code"] != 0:
                        code = parsed.get("code")
                        msg = parsed.get("msg", "Unknown error")
                        raise RuntimeError(f"Lark API error {code}: {msg}")
                    return parsed
                except json.JSONDecodeError:
                    return text
            elif isinstance(first, dict) and first.get("type") == "resource":
                # Resource type - return the content
                return first
        
        # If result is directly parseable
        if isinstance(result, dict) and "code" in result and result["code"] != 0:
            raise RuntimeError(f"Lark API error {result.get('code')}: {result.get('msg')}")
        
        return result
    
    def list_tools(self, timeout: float = 30.0) -> list[dict]:
        """List all available tools from the MCP server."""
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")
        
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/list"
        })
        
        response = self._recv(expected_id=req_id, timeout=timeout)
        
        if "error" in response:
            raise RuntimeError(f"tools/list failed: {response['error']}")
        
        return response.get("result", {}).get("tools", [])


# ---------------------------------------------------------------------------
# Convenience function for one-off calls
# ---------------------------------------------------------------------------
def call_lark_tool(tool_name: str, arguments: dict, timeout: float = 60.0) -> Any:
    """
    One-off call to a Lark MCP tool.
    
    This spawns the MCP server, makes the call, and terminates the server.
    For multiple calls, use MCPClient as a context manager instead.
    """
    with MCPClient() as client:
        return client.call_tool(tool_name, arguments, timeout=timeout)


if __name__ == "__main__":
    # Quick test: list tools
    print("Testing MCP client...")
    with MCPClient() as client:
        tools = client.list_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools[:5]:
            print(f"  - {t.get('name')}")
        print("  ...")
