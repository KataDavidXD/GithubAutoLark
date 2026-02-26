"""Plan-based execution engine for GithubAutoLark.

Replaces the old branching LangGraph with a simple sequential executor:
  1. LLM Planner decomposes the user message into tool-call steps
  2. ToolRegistry executes each step in order
  3. Results are collected and returned
"""

from __future__ import annotations

from typing import Any

from src.db.database import Database
from src.agent.supervisor import get_planner
from src.agent.tool_registry import ToolRegistry


def chat(
    message: str,
    db: Database,
    github_service: Any = None,
    lark_service: Any = None,
) -> str:
    """Process a natural language message and return a response.

    This is the single entry point used by both ``chat.py`` and ``server/app.py``.
    """
    planner = get_planner()
    registry = ToolRegistry(db, github_service=github_service, lark_service=lark_service)

    # Step 1 — Ask the LLM to produce an execution plan
    plan = planner.create_plan(message)

    if not plan or not plan.get("steps"):
        if not planner.enabled:
            return (
                "LLM is not configured (LLM_API_KEY missing).\n"
                "Set LLM_API_KEY in your .env to enable natural language processing."
            )
        return (
            f"I couldn't understand: '{message}'\n\n"
            "Try commands like:\n"
            "  - 'list members' / 'fetch github members'\n"
            "  - 'what is Alice doing?' / 'show Alice's work'\n"
            "  - 'link KataDavidXD to Yang Li'\n"
            "  - 'create issue: fix login bug'\n"
            "  - 'list open issues' / 'close issue #5'\n"
            "  - 'list tables'\n"
            "  - 'sync status'\n"
            "  - Compound: 'fetch github members, fetch lark members, then list members'"
        )

    steps = plan["steps"]

    # Step 2 — Execute each step sequentially
    results: list[str] = []
    for i, step in enumerate(steps, 1):
        tool_name = step.get("tool", "")
        params = step.get("params", {})

        # Sanitize: ensure params is a dict
        if not isinstance(params, dict):
            params = {}

        result = registry.execute(tool_name, params)
        if len(steps) > 1:
            results.append(f"--- Step {i}: {tool_name} ---\n{result}")
        else:
            results.append(result)

    return "\n\n".join(results)
