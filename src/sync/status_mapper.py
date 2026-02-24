"""Pure-function status mapping between Lark and GitHub.

Single Responsibility: only maps statuses.  No side effects.
"""

from __future__ import annotations

from typing import Optional


def lark_status_to_github_state(lark_status: str) -> tuple[str, Optional[str]]:
    """Map Lark status → (github_state, state_reason)."""
    normalised = lark_status.lower().replace(" ", "")
    if normalised == "done":
        return ("closed", "completed")
    if normalised in ("todo", "inprogress"):
        return ("open", None)
    return ("open", None)


def github_state_to_lark_status(
    github_state: str, current_lark_status: Optional[str] = None
) -> str:
    """Map GitHub state → Lark status, preserving 'In Progress' if already set."""
    if github_state == "closed":
        return "Done"
    if github_state == "open":
        if current_lark_status and current_lark_status.lower().replace(" ", "") == "inprogress":
            return "In Progress"
        return "To Do"
    return "To Do"


def normalise_status(raw: str) -> str:
    """Normalise any status string to one of: To Do, In Progress, Done."""
    s = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    if s in ("todo", "new", "open", "pending"):
        return "To Do"
    if s in ("inprogress", "doing", "wip", "working"):
        return "In Progress"
    if s in ("done", "completed", "closed", "finished"):
        return "Done"
    return "To Do"
