"""Shared agent state for the plan-based execution engine."""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """State that flows through the plan executor."""

    user_command: str
    plan: list[dict[str, Any]]      # [{"tool": ..., "params": ...}, ...]
    results: list[str]              # output of each executed step
    result: Optional[str]           # final combined output
    error: Optional[str]
    messages: list[str]             # debug trace
