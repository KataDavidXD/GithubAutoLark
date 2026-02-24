"""Tool functions for the GitHub Issues agent."""

from __future__ import annotations

from typing import Any, Optional

from src.db.database import Database
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.member_repo import MemberRepository
from src.db.outbox_repo import OutboxRepository
from src.models.task import Task, TaskSource
from src.sync.status_mapper import normalise_status


class GitHubTools:
    """Stateful tool collection for GitHub issue operations."""

    def __init__(self, db: Database, github_service: Any = None, lark_service: Any = None):
        self._db = db
        self._github = github_service
        self._task_repo = TaskRepository(db)
        self._mapping_repo = MappingRepository(db)
        self._member_repo = MemberRepository(db)
        self._outbox = OutboxRepository(db)

    def create_issue(
        self,
        title: str,
        body: str = "",
        assignee: Optional[str] = None,
        labels: Optional[list[str]] = None,
        send_to_lark: bool = False,
        target_table: Optional[str] = None,
    ) -> str:
        """Create a GitHub issue, optionally syncing to Lark."""
        if not self._github:
            return "Error: GitHub service not configured."

        try:
            assignees = []
            member_id = None
            if assignee:
                member = (
                    self._member_repo.get_by_email(assignee)
                    or self._member_repo.get_by_github(assignee)
                )
                if not member:
                    results = self._member_repo.find_by_name(assignee)
                    member = results[0] if results else None
                if member and member.github_username:
                    assignees = [member.github_username]
                    member_id = member.member_id

            issue = self._github.create_issue(
                title=title, body=body,
                labels=labels or ["auto"],
                assignees=assignees or None,
            )
            issue_number = issue["number"]

            task = Task(
                title=title, body=body,
                source=TaskSource.COMMAND,
                assignee_member_id=member_id,
                labels=labels or [],
                target_table=target_table,
            )
            self._task_repo.create(task)
            self._mapping_repo.upsert_for_task(
                task.task_id,
                github_issue_number=issue_number,
                github_repo=self._github.repo_slug,
            )

            result_msg = f"Issue #{issue_number} '{title}' created."
            if assignees:
                result_msg += f" Assigned to {assignees[0]}."

            if send_to_lark:
                self._outbox.enqueue("convert_issue_to_lark", {
                    "issue_number": issue_number,
                    "task_id": task.task_id,
                    "target_table": target_table,
                })
                result_msg += " Queued for Lark sync."

            return result_msg

        except Exception as e:
            return f"Error creating issue: {e}"

    def get_issue(self, issue_number: int) -> str:
        """Get details of a GitHub issue."""
        if not self._github:
            return "Error: GitHub service not configured."
        try:
            issue = self._github.get_issue(issue_number)
            assignees = ", ".join(a["login"] for a in issue.get("assignees", []))
            labels = ", ".join(l["name"] for l in issue.get("labels", []))
            lines = [
                f"Issue #{issue['number']}: {issue['title']}",
                f"State: {issue['state']}",
                f"Assignees: {assignees or 'None'}",
                f"Labels: {labels or 'None'}",
                f"Body: {(issue.get('body') or '')[:200]}",
                f"URL: {issue.get('html_url', '')}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching issue #{issue_number}: {e}"

    def update_issue(
        self,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> str:
        """Update a GitHub issue."""
        if not self._github:
            return "Error: GitHub service not configured."
        try:
            assignees = None
            if assignee:
                member = (
                    self._member_repo.get_by_email(assignee)
                    or self._member_repo.get_by_github(assignee)
                )
                if not member:
                    results = self._member_repo.find_by_name(assignee)
                    member = results[0] if results else None
                if member and member.github_username:
                    assignees = [member.github_username]

            self._github.update_issue(
                issue_number,
                title=title, body=body, state=state,
                labels=labels, assignees=assignees,
            )
            return f"Issue #{issue_number} updated."
        except Exception as e:
            return f"Error updating issue #{issue_number}: {e}"

    def close_issue(self, issue_number: int) -> str:
        """Close a GitHub issue."""
        if not self._github:
            return "Error: GitHub service not configured."
        try:
            self._github.close_issue(issue_number)
            return f"Issue #{issue_number} closed."
        except Exception as e:
            return f"Error closing issue #{issue_number}: {e}"

    def list_issues(
        self,
        state: str = "open",
        assignee: Optional[str] = None,
        labels: Optional[str] = None,
    ) -> str:
        """List GitHub issues with optional filters."""
        if not self._github:
            return "Error: GitHub service not configured."
        try:
            gh_assignee = None
            if assignee:
                member = (
                    self._member_repo.get_by_email(assignee)
                    or self._member_repo.get_by_github(assignee)
                )
                if not member:
                    results = self._member_repo.find_by_name(assignee)
                    member = results[0] if results else None
                if member and member.github_username:
                    gh_assignee = member.github_username

            issues = self._github.list_issues(
                state=state, labels=labels, assignee=gh_assignee,
            )
            if not issues:
                return "No issues found."
            lines = [f"Found {len(issues)} issue(s):"]
            for iss in issues[:20]:
                assignees = ", ".join(a["login"] for a in iss.get("assignees", []))
                lines.append(
                    f"  #{iss['number']}: {iss['title']} [{iss['state']}] "
                    f"Assignee: {assignees or 'None'}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing issues: {e}"

    def send_issue_to_lark(
        self, issue_number: int, target_table: Optional[str] = None
    ) -> str:
        """Convert a GitHub issue to a Lark record."""
        mapping = self._mapping_repo.get_by_github_issue(issue_number)
        task_id = mapping.task_id if mapping else None

        self._outbox.enqueue("convert_issue_to_lark", {
            "issue_number": issue_number,
            "task_id": task_id,
            "target_table": target_table,
        })
        return f"Issue #{issue_number} queued for conversion to Lark table '{target_table or 'default'}'."
