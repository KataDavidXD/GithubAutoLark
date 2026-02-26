"""Legacy graph module — now delegates to the plan-based engine.

Kept for backward compatibility.  All real logic is in enhanced_graph.py.
"""

from __future__ import annotations

from typing import Any

from src.db.database import Database
from src.agent.enhanced_graph import chat


def run_command(
    command: str,
    db: Database,
    github_service: Any = None,
    lark_service: Any = None,
) -> str:
    """One-shot: run a single user command through the plan executor."""
    return chat(command, db, github_service, lark_service)
