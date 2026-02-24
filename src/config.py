"""
Central configuration loader.
Reads from environment variables (via .env); validates required keys.
NEVER prints secret values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Load .env from repo root (if present)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")


def _get(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.getenv(key, default)
    if required and not val:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return val


# ---------------------------------------------------------------------------
# GitHub config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GitHubConfig:
    token: str
    owner: str
    repo: str

    @property
    def base_url(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}"


def get_github_config() -> GitHubConfig:
    return GitHubConfig(
        token=_get("GITHUB_TOKEN", required=True),  # type: ignore[arg-type]
        owner=_get("OWNER", default="KataDavidXD"),  # type: ignore[arg-type]
        repo=_get("REPO", default="GithubAutoLark"),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Lark MCP config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LarkMCPConfig:
    client_id: str
    client_secret: str
    domain: str
    use_oauth: bool


def get_lark_mcp_config() -> LarkMCPConfig:
    return LarkMCPConfig(
        client_id=_get("LARK_MCP_CLIENT_ID", required=True),  # type: ignore[arg-type]
        client_secret=_get("LARK_MCP_CLIENT_SECRET", required=True),  # type: ignore[arg-type]
        domain=_get("LARK_MCP_DOMAIN", default="https://open.larksuite.com/"),  # type: ignore[arg-type]
        use_oauth=_get("LARK_MCP_USE_OAUTH", default="true").lower() in ("1", "true", "yes"),  # type: ignore[union-attr]
    )


# ---------------------------------------------------------------------------
# Lark Bitable target (created by setup, persisted to .env)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LarkBitableConfig:
    app_token: Optional[str]
    tasks_table_id: Optional[str]
    notify_chat_id: Optional[str]
    # Field names (must match Bitable exactly)
    field_title: str
    field_status: str
    field_assignee: str
    field_github_issue: str
    field_last_sync: str


def get_lark_bitable_config() -> LarkBitableConfig:
    return LarkBitableConfig(
        app_token=_get("LARK_APP_TOKEN"),
        tasks_table_id=_get("LARK_TASKS_TABLE_ID"),
        notify_chat_id=_get("LARK_NOTIFY_CHAT_ID"),
        field_title=_get("LARK_FIELD_TITLE", default="Task Name"),  # type: ignore[arg-type]
        field_status=_get("LARK_FIELD_STATUS", default="Status"),  # type: ignore[arg-type]
        field_assignee=_get("LARK_FIELD_ASSIGNEE", default="Assignee"),  # type: ignore[arg-type]
        field_github_issue=_get("LARK_FIELD_GITHUB_ISSUE", default="GitHub Issue"),  # type: ignore[arg-type]
        field_last_sync=_get("LARK_FIELD_LAST_SYNC", default="Last Sync"),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Employee identity (for assignee demo)
# ---------------------------------------------------------------------------
def get_employee_email() -> Optional[str]:
    return _get("EMPLOYEE_EMAIL")


# ---------------------------------------------------------------------------
# LLM config (optional, for future doc processing)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LLMConfig:
    api_key: Optional[str]
    base_url: Optional[str]
    default_model: Optional[str]


def get_llm_config() -> LLMConfig:
    return LLMConfig(
        api_key=_get("LLM_API_KEY"),
        base_url=_get("LLM_BASE_URL"),
        default_model=_get("DEFAULT_LLM"),
    )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def get_repo_root() -> Path:
    return _REPO_ROOT


def get_db_path() -> Path:
    return _REPO_ROOT / "data" / "sync.db"


def get_demos_dir() -> Path:
    return _REPO_ROOT / "demos"
