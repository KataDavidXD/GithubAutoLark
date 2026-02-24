"""Sync sub-agent node for LangGraph."""

from __future__ import annotations

from typing import Any

from src.agent.state import AgentState
from src.agent.tools.sync_tools import SyncTools


def sync_agent_node(state: AgentState, tools: SyncTools) -> dict[str, Any]:
    """Execute sync action based on parsed intent."""
    action = state.get("action", "")
    command = state.get("user_command", "").lower()
    messages = list(state.get("messages", []))
    messages.append("Sync agent invoked")

    result = ""

    try:
        if "retry" in command:
            result = tools.retry_failed()
        elif "status" in command:
            result = tools.sync_status()
        else:
            result = tools.sync_pending()
    except Exception as e:
        result = f"Sync agent error: {e}"

    messages.append(f"Sync agent result: {result[:100]}")

    return {
        "result": result,
        "current_agent": "sync_agent",
        "messages": messages,
    }
