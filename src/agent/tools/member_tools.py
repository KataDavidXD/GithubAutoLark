"""Tool functions for the Member Management agent.

Each function is a plain callable that wraps MemberService.
These are designed to be bound to a LangGraph ``create_react_agent``
via ``langchain_core.tools.tool`` or used directly.
"""

from __future__ import annotations

from typing import Any, Optional

from src.db.database import Database
from src.services.member_service import MemberService


class MemberTools:
    """Stateful tool collection — holds references to DB and services."""

    def __init__(self, db: Database, lark_service: Any = None, github_service: Any = None):
        self._svc = MemberService(db, lark_service=lark_service, github_service=github_service)

    def create_member(
        self,
        name: str,
        email: str,
        role: str = "member",
        position: Optional[str] = None,
        team: Optional[str] = None,
        github_username: Optional[str] = None,
    ) -> str:
        """Create a new team member with cross-platform identity resolution."""
        try:
            member = self._svc.create_member(
                name=name, email=email, role=role,
                position=position, team=team,
                github_username=github_username,
            )
            lark_status = f", Lark ID: {member.lark_open_id}" if member.lark_open_id else ""
            return (
                f"Member '{member.name}' created (ID: {member.member_id[:8]}). "
                f"Email: {member.email}, Role: {member.role.value}{lark_status}"
            )
        except Exception as e:
            return f"Error creating member: {e}"

    def get_member(self, identifier: str) -> str:
        """Look up a member by email, name, or ID."""
        member = self._svc.get_member(identifier)
        if not member:
            return f"Member '{identifier}' not found."
        lines = [
            f"Name: {member.name}",
            f"Email: {member.email}",
            f"Role: {member.role.value}",
            f"Position: {member.position or 'N/A'}",
            f"Team: {member.team or 'N/A'}",
            f"GitHub: {member.github_username or 'N/A'}",
            f"Lark ID: {member.lark_open_id or 'N/A'}",
            f"Status: {member.status.value}",
            f"Tables: {', '.join(t.table_name for t in member.lark_tables) or 'None'}",
        ]
        return "\n".join(lines)

    def update_member(self, identifier: str, **fields: Any) -> str:
        """Update member fields (role, position, team, github_username, etc.)."""
        result = self._svc.update_member(identifier, **fields)
        if not result:
            return f"Member '{identifier}' not found."
        return f"Member '{result.name}' updated successfully."

    def list_members(
        self,
        role: Optional[str] = None,
        team: Optional[str] = None,
        status: str = "active",
    ) -> str:
        """List team members with optional filters."""
        members = self._svc.list_members(role=role, team=team, status=status)
        if not members:
            return "No members found matching filters."
        lines = [f"Found {len(members)} member(s):"]
        for m in members:
            lines.append(
                f"  - {m.name} ({m.email}) [{m.role.value}] "
                f"Team: {m.team or 'N/A'} Status: {m.status.value}"
            )
        return "\n".join(lines)

    def deactivate_member(self, identifier: str) -> str:
        """Soft-delete a member (mark as inactive)."""
        result = self._svc.deactivate_member(identifier)
        if not result:
            return f"Member '{identifier}' not found."
        return f"Member '{result.name}' deactivated."

    def assign_table(self, identifier: str, table_name: str) -> str:
        """Assign a Lark table to a member."""
        try:
            result = self._svc.assign_table(identifier, table_name)
            if not result:
                return f"Member '{identifier}' not found."
            tables = ", ".join(t.table_name for t in result.lark_tables)
            return f"Member '{result.name}' assigned to tables: {tables}"
        except ValueError as e:
            return str(e)

    def view_member_work(self, identifier: str) -> str:
        """View all GitHub issues and Lark records for a member."""
        work = self._svc.get_member_work(identifier)
        if not work:
            return f"Member '{identifier}' not found."
        return work.to_text()
