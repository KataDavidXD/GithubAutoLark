"""
Agent State - Shared state for the LangGraph agent.

The state flows through all nodes and accumulates results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from typing_extensions import TypedDict


class MemberInfo(TypedDict, total=False):
    """Standardized member information."""
    email: str
    github_username: str
    lark_open_id: str
    name: str
    role: str


class TodoItem(TypedDict, total=False):
    """Todo item to be processed."""
    title: str
    body: str
    assignee: str
    priority: str
    status: str
    labels: list[str]
    # After sync, these are populated:
    task_id: str
    github_issue_number: int
    lark_record_id: str


class ProjectConfig(TypedDict, total=False):
    """Project configuration."""
    project_id: str
    name: str
    description: str
    github: dict[str, Any]
    lark: dict[str, Any]
    status_mapping: dict[str, str]
    sync: dict[str, Any]


class AgentState(TypedDict, total=False):
    """
    The state that flows through the LangGraph agent.
    
    Each node reads from and writes to this shared state.
    """
    # --- Input ---
    input_path: str  # Path to input folder
    
    # --- Raw Documents (loaded from markdown) ---
    project_doc: str  # Project structure markdown content
    todos_doc: str  # Fuzzy todos markdown content
    team_doc: str  # Team info markdown content (optional)
    
    # --- Mode ---
    mode: Literal["new", "existing", "sync_only"]
    sync_direction: Literal["github_to_lark", "lark_to_github", "bidirectional"]
    
    # --- Parsed Data (from LLM) ---
    project: ProjectConfig
    members: list[MemberInfo]
    todos: list[TodoItem]
    
    # --- Existing Data (loaded from DB/APIs) ---
    existing_github_issues: list[dict[str, Any]]
    existing_lark_records: list[dict[str, Any]]
    existing_tasks: list[dict[str, Any]]
    
    # --- Processing Results ---
    members_standardized: list[MemberInfo]
    todos_aligned: list[TodoItem]
    
    # --- Sync Results ---
    synced_to_github: list[dict[str, Any]]
    synced_to_lark: list[dict[str, Any]]
    sync_errors: list[str]
    
    # --- Status ---
    current_node: str
    messages: list[str]
    error: Optional[str]
