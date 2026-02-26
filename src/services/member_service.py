"""Member service — cross-platform member management and identity resolution.

Coordinates local DB, Lark Contact API, and GitHub API to provide a
unified view of team members.  This is the "Facade" for member operations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.member import Member, MemberRole, MemberStatus, LarkTableAssignment
from src.models.lark_table_registry import LarkTableConfig


@dataclass
class MemberWorkSummary:
    """Aggregated view of a member's work across platforms."""
    member: Member
    github_issues: list[dict[str, Any]]
    lark_records: list[dict[str, Any]]
    local_tasks: list[dict[str, Any]]

    @property
    def total_items(self) -> int:
        return len(self.github_issues) + len(self.lark_records)

    def to_text(self) -> str:
        lines = [f"Work summary for {self.member.name} ({self.member.email}):"]
        lines.append(f"  GitHub issues: {len(self.github_issues)}")
        for iss in self.github_issues[:10]:
            state = iss.get("state", "?")
            lines.append(f"    #{iss.get('number')}: {iss.get('title', '')} [{state}]")
        lines.append(f"  Lark tasks: {len(self.lark_records)}")
        for rec in self.lark_records[:10]:
            fields = rec.get("fields", {})
            raw_title = fields.get("Task Name", fields.get("Name", fields.get("title", "?")))
            # Lark text fields can be [{"text": "...", "type": "text"}] or plain strings
            if isinstance(raw_title, list) and raw_title:
                title = raw_title[0].get("text", str(raw_title[0])) if isinstance(raw_title[0], dict) else str(raw_title[0])
            else:
                title = str(raw_title)
            status = fields.get("Status", "?")
            table_name = rec.get("_table_name", "")
            table_prefix = f"[{table_name}] " if table_name else ""
            lines.append(f"    {table_prefix}{title} [{status}]")
        lines.append(f"  Local tasks: {len(self.local_tasks)}")
        return "\n".join(lines)


class MemberService:
    """
    Facade for member CRUD + cross-platform identity resolution.

    Dependencies are injected (Dependency Inversion) so the service
    can be tested with mocks for external APIs.
    """

    def __init__(
        self,
        db: Database,
        lark_service: Optional[Any] = None,
        github_service: Optional[Any] = None,
    ):
        self._db = db
        self._member_repo = MemberRepository(db)
        self._task_repo = TaskRepository(db)
        self._mapping_repo = MappingRepository(db)
        self._table_repo = LarkTableRepository(db)
        self._lark = lark_service
        self._github = github_service

    # -- Create ----------------------------------------------------------------

    def create_member(
        self,
        name: str,
        email: str,
        role: str = "member",
        position: Optional[str] = None,
        team: Optional[str] = None,
        github_username: Optional[str] = None,
        resolve_lark_id: bool = True,
    ) -> Member:
        """Create a member, optionally resolving Lark open_id from email."""
        lark_open_id = None
        if resolve_lark_id and self._lark:
            try:
                lark_open_id = self._lark.get_user_id_by_email(email)
            except Exception:
                pass

        member = Member(
            name=name,
            email=email,
            role=MemberRole(role),
            position=position,
            team=team,
            github_username=github_username,
            lark_open_id=lark_open_id,
        )
        self._member_repo.create(member)
        return member

    # -- Read ------------------------------------------------------------------

    def get_member(self, identifier: str) -> Optional[Member]:
        """Lookup by email, name (first match), or member_id."""
        m = self._member_repo.get_by_email(identifier)
        if m:
            return m
        m = self._member_repo.get_by_id(identifier)
        if m:
            return m
        results = self._member_repo.find_by_name(identifier)
        return results[0] if results else None

    def list_members(
        self,
        role: Optional[str] = None,
        team: Optional[str] = None,
        status: str = "active",
    ) -> list[Member]:
        return self._member_repo.list_all(
            status=MemberStatus(status) if status else None,
            role=MemberRole(role) if role else None,
            team=team,
        )

    # -- Update ----------------------------------------------------------------

    def update_member(self, identifier: str, **fields) -> Optional[Member]:
        """Update member fields by any identifier (email, name, id)."""
        member = self.get_member(identifier)
        if not member:
            return None

        if "lark_tables" in fields and isinstance(fields["lark_tables"], list):
            fields["lark_tables"] = json.dumps(fields["lark_tables"])

        return self._member_repo.update(member.member_id, **fields)

    def deactivate_member(self, identifier: str) -> Optional[Member]:
        member = self.get_member(identifier)
        if not member:
            return None
        return self._member_repo.deactivate(member.member_id)

    # -- Table Assignment ------------------------------------------------------

    def assign_table(self, identifier: str, table_name: str) -> Optional[Member]:
        """Add a Lark table to a member's assignments."""
        member = self.get_member(identifier)
        if not member:
            return None

        table_cfg = self._table_repo.get_by_name(table_name)
        if not table_cfg:
            raise ValueError(f"Table '{table_name}' not found in registry")

        assignment = LarkTableAssignment(
            app_token=table_cfg.app_token,
            table_id=table_cfg.table_id,
            table_name=table_cfg.table_name,
        )

        existing_ids = {t.table_id for t in member.lark_tables}
        if table_cfg.table_id not in existing_ids:
            member.lark_tables.append(assignment)
            return self._member_repo.update(
                member.member_id, lark_tables=member.lark_tables_json()
            )
        return member

    # -- Work view -------------------------------------------------------------

    # Common Lark Person/Assignee field names across different table schemas
    _ASSIGNEE_FIELD_CANDIDATES = ("Assignee", "assignee", "负责人", "Owner", "Person")

    def get_member_work(self, identifier: str) -> Optional[MemberWorkSummary]:
        """Aggregate a member's work across GitHub and Lark.

        For Lark, queries the **live API** to discover ALL tables in the
        Bitable app, then searches each one for records assigned to this
        member.  This guarantees a complete, real-time answer regardless
        of whether the table was created by our system or the Lark UI.
        """
        member = self.get_member(identifier)
        if not member:
            return None

        github_issues: list[dict[str, Any]] = []
        if self._github and member.github_username:
            try:
                github_issues = self._github.list_issues_by_assignee(
                    member.github_username, state="all"
                )
            except Exception as e:
                print(f"[MemberService] GitHub query failed: {e}")

        lark_records: list[dict[str, Any]] = []
        if self._lark and member.lark_open_id:
            lark_records = self._search_all_lark_tables(member.lark_open_id)

        local_tasks = [
            t.to_dict() for t in self._task_repo.get_by_assignee(member.member_id)
        ]

        return MemberWorkSummary(
            member=member,
            github_issues=github_issues,
            lark_records=lark_records,
            local_tasks=local_tasks,
        )

    def _search_all_lark_tables(self, open_id: str) -> list[dict[str, Any]]:
        """Discover ALL tables from the live Lark API and search each one."""
        import os
        app_token = os.getenv("LARK_APP_TOKEN")
        if not app_token:
            return []

        try:
            live_tables = self._lark.list_tables(app_token)
        except Exception as e:
            print(f"[MemberService] Failed to list Lark tables: {e}")
            return []

        # Build a lookup from local registry for known field mappings
        registered = {cfg.table_id: cfg for cfg in self._table_repo.list_all()}

        results: list[dict[str, Any]] = []
        for tbl in live_tables:
            table_id = tbl.get("table_id", "")
            table_name = tbl.get("name", table_id)

            # Determine which field name to use for the Assignee filter
            cfg = registered.get(table_id)
            if cfg:
                candidates = [cfg.field_mapping.get("assignee_field", "Assignee")]
            else:
                candidates = list(self._ASSIGNEE_FIELD_CANDIDATES)

            for field_name in candidates:
                try:
                    records = self._lark.search_records_by_assignee(
                        open_id,
                        app_token=app_token,
                        table_id=table_id,
                        assignee_field=field_name,
                    )
                    for rec in records:
                        rec["_table_name"] = table_name
                    results.extend(records)
                    break  # found the right field name, stop trying
                except Exception as e:
                    err = str(e)
                    # Field doesn't exist or isn't the right type — try next
                    if any(k in err for k in ("FieldNameNotFound", "1254036", "InvalidFilter", "1254018")):
                        continue
                    # Any other error means the table itself is broken; skip.
                    print(f"[MemberService] Lark search '{table_name}' field='{field_name}': {err}")
                    break

        return results

    # -- Resolve Lark ID (batch) -----------------------------------------------

    def resolve_lark_ids(self) -> dict[str, Optional[str]]:
        """Resolve Lark open_ids for all members missing them."""
        if not self._lark:
            return {}

        members = self._member_repo.list_all(status=MemberStatus.ACTIVE)
        to_resolve = [m for m in members if not m.lark_open_id and m.email]

        if not to_resolve:
            return {}

        emails = [m.email for m in to_resolve]
        resolved = self._lark.get_user_ids_by_emails(emails)

        for m in to_resolve:
            open_id = resolved.get(m.email)
            if open_id:
                self._member_repo.update(m.member_id, lark_open_id=open_id)

        return resolved
