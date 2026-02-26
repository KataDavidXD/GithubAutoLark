"""Field mapping between GitHub Issue fields and Lark Bitable fields.

Open/Closed: mapping configs are data-driven via ``LarkTableConfig.field_mapping``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.models.lark_table_registry import LarkTableConfig, DEFAULT_FIELD_MAPPING
from src.sync.status_mapper import lark_status_to_github_state, github_state_to_lark_status


def github_issue_to_lark_fields(
    issue: dict[str, Any],
    table_cfg: Optional[LarkTableConfig] = None,
    assignee_open_id: Optional[str] = None,
) -> dict[str, Any]:
    """Convert a GitHub Issue dict to Lark record fields."""
    fm = table_cfg.field_mapping if table_cfg else dict(DEFAULT_FIELD_MAPPING)

    title = issue.get("title", "")
    for prefix in ("[AUTO]",):
        if prefix in title:
            title = title.split("]", 2)[-1].strip()

    fields: dict[str, Any] = {
        fm.get("title_field", "Task Name"): title,
        fm.get("status_field", "Status"): github_state_to_lark_status(issue.get("state", "open")),
    }

    body = issue.get("body", "")
    if body:
        desc_field = fm.get("description_field", "Description")
        if desc_field:
            fields[desc_field] = body

    if assignee_open_id:
        fields[fm.get("assignee_field", "Assignee")] = [{"id": assignee_open_id}]

    issue_number = issue.get("number")
    if issue_number:
        fields[fm.get("github_issue_field", "GitHub Issue")] = issue_number

    return fields


def lark_record_to_github_fields(
    record: dict[str, Any],
    table_cfg: Optional[LarkTableConfig] = None,
    task_id: Optional[str] = None,
    assignee_github_username: Optional[str] = None,
) -> dict[str, Any]:
    """Convert a Lark record to GitHub Issue create/update payload."""
    fm = table_cfg.field_mapping if table_cfg else dict(DEFAULT_FIELD_MAPPING)
    record_fields = record.get("fields", {})

    title_raw = record_fields.get(fm.get("title_field", "Task Name"), "Untitled")
    if isinstance(title_raw, list):
        title_raw = title_raw[0].get("text", "") if title_raw else ""
    title = str(title_raw)

    if task_id:
        title = f"[AUTO][{task_id[:8]}] {title}"

    status_raw = record_fields.get(fm.get("status_field", "Status"), "To Do")
    if isinstance(status_raw, dict):
        status_raw = status_raw.get("name", status_raw.get("text", "To Do"))
    status = str(status_raw)

    state, state_reason = lark_status_to_github_state(status)

    body = record_fields.get(fm.get("description_field", "Description"), "")
    if isinstance(body, list):
        body = body[0].get("text", "") if body else ""

    result: dict[str, Any] = {
        "title": title,
        "body": str(body),
        "state": state,
    }
    if state_reason:
        result["state_reason"] = state_reason
    if assignee_github_username:
        result["assignees"] = [assignee_github_username]

    return result


def build_lark_record_fields(
    title: str,
    status: str = "To Do",
    assignee_open_id: Optional[str] = None,
    github_issue_number: Optional[int] = None,
    body: Optional[str] = None,
    table_cfg: Optional[LarkTableConfig] = None,
) -> dict[str, Any]:
    """Build Lark record fields from individual values."""
    fm = table_cfg.field_mapping if table_cfg else dict(DEFAULT_FIELD_MAPPING)

    fields: dict[str, Any] = {
        fm.get("title_field", "Task Name"): title,
        fm.get("status_field", "Status"): status,
    }

    if assignee_open_id:
        fields[fm.get("assignee_field", "Assignee")] = [{"id": assignee_open_id}]

    if github_issue_number is not None:
        fields[fm.get("github_issue_field", "GitHub Issue")] = github_issue_number

    if body:
        desc_field = fm.get("description_field", "Description")
        if desc_field:
            fields[desc_field] = body

    return fields
