"""Backward-compatible shim for modules that import from llm_supervisor.

All real logic lives in supervisor.py (LLMPlanner) now.
"""

from __future__ import annotations

from typing import Any

from src.agent.supervisor import get_planner_status


def get_llm_status() -> dict[str, Any]:
    """Return LLM planner status for the /api/status endpoint."""
    status = get_planner_status()
    return {
        "enabled": status["enabled"],
        "model": status["model"],
        "base_url": status["base_url"],
        "memory_turns": 0,
    }
