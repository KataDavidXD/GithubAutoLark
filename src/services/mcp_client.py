"""MCP Client — JSON-RPC stdio communication with Lark MCP server.

Reused from the original codebase with minimal changes:
  - Moved to src/services/ for SOLID packaging
  - UTF-8 encoding enforced
  - shell=True removed for Linux compatibility
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
    """Lark MCP server JSON-RPC client (stdio transport)."""

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

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        use_shell = sys.platform == "win32"
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=use_shell,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        self._initialize()

    def stop(self) -> None:
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            finally:
                self.process = None
                self._initialized = False

    # -- protocol internals ----------------------------------------------------

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _send(self, message: dict) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("MCP client not started")
        line = json.dumps(message) + "\n"
        self.process.stdin.write(line)
        self.process.stdin.flush()

    def _recv(self, expected_id: Optional[int] = None, timeout: float = 60.0) -> dict:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("MCP client not started")
        start = time.time()
        while True:
            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for response (id={expected_id})")
            line = self.process.stdout.readline()
            if not line:
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    raise RuntimeError(f"MCP server exited: {stderr}")
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if expected_id is not None:
                if msg.get("id") == expected_id:
                    return msg
                continue
            return msg

    def _initialize(self) -> None:
        if self._initialized:
            return
        init_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "github-auto-lark", "version": "2.0.0"},
            },
        })
        self._recv(expected_id=init_id, timeout=30.0)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True

    # -- public API ------------------------------------------------------------

    def call_tool(self, tool_name: str, arguments: dict, timeout: float = 60.0) -> Any:
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        response = self._recv(expected_id=req_id, timeout=timeout)

        if "error" in response:
            raise RuntimeError(f"Tool call failed: {response['error']}")

        result = response.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text = first.get("text", "{}")
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and "code" in parsed and parsed["code"] != 0:
                        raise RuntimeError(
                            f"Lark API error {parsed.get('code')}: {parsed.get('msg')}"
                        )
                    return parsed
                except json.JSONDecodeError:
                    return text
            elif isinstance(first, dict) and first.get("type") == "resource":
                return first

        if isinstance(result, dict) and "code" in result and result["code"] != 0:
            raise RuntimeError(f"Lark API error {result.get('code')}: {result.get('msg')}")
        return result

    def list_tools(self, timeout: float = 30.0) -> list[dict]:
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")
        req_id = self._next_id()
        self._send({"jsonrpc": "2.0", "id": req_id, "method": "tools/list"})
        response = self._recv(expected_id=req_id, timeout=timeout)
        if "error" in response:
            raise RuntimeError(f"tools/list failed: {response['error']}")
        return response.get("result", {}).get("tools", [])
