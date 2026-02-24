"""Shared agent state — flows through the entire LangGraph supervisor graph."""

from __future__ import annotations

from typing import Any, Literal, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """State shared across all nodes in the supervisor graph."""

    # --- Input from user ---
    user_command: str

    # --- Parsed intent (set by supervisor) ---
    intent: Literal[
        "member_management",
        "github_issues",
        "lark_tables",
        "cross_platform_sync",
        "unknown",
    ]
    action: str
    entities: dict[str, Any]

    # --- Execution context ---
    current_agent: str

    # --- Result ---
    result: Optional[str]
    error: Optional[str]

    # --- Conversation messages (LangGraph Annotated list would go here
    #     but we keep it simple for the non-chat version) ---
    messages: list[str]
