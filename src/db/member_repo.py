"""Repository for the ``members`` table — full CRUD with ACID transactions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.db.database import Database
from src.models.member import Member, MemberRole, MemberStatus


class MemberRepository:
    """Single-Responsibility repository for member persistence."""

    def __init__(self, db: Database):
        self._db = db

    # -- Create ----------------------------------------------------------------

    def create(self, member: Member) -> Member:
        """Insert a new member. Raises on duplicate email."""
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO members
                   (member_id, name, email, github_username, lark_open_id,
                    role, position, team, status, lark_tables)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    member.member_id, member.name, member.email,
                    member.github_username, member.lark_open_id,
                    member.role.value, member.position, member.team,
                    member.status.value, member.lark_tables_json(),
                ),
            )
        return member

    # -- Read ------------------------------------------------------------------

    def get_by_id(self, member_id: str) -> Optional[Member]:
        row = self._db.fetchone("SELECT * FROM members WHERE member_id = ?", (member_id,))
        return Member.from_row(row) if row else None

    def get_by_email(self, email: str) -> Optional[Member]:
        row = self._db.fetchone("SELECT * FROM members WHERE email = ?", (email,))
        return Member.from_row(row) if row else None

    def get_by_github(self, username: str) -> Optional[Member]:
        row = self._db.fetchone(
            "SELECT * FROM members WHERE github_username = ?", (username,)
        )
        return Member.from_row(row) if row else None

    def get_by_lark_id(self, open_id: str) -> Optional[Member]:
        row = self._db.fetchone(
            "SELECT * FROM members WHERE lark_open_id = ?", (open_id,)
        )
        return Member.from_row(row) if row else None

    def find_by_name(self, name: str) -> list[Member]:
        """Case-insensitive partial match on name."""
        rows = self._db.fetchall(
            "SELECT * FROM members WHERE LOWER(name) LIKE ?",
            (f"%{name.lower()}%",),
        )
        return [Member.from_row(r) for r in rows]

    # -- List / Filter ---------------------------------------------------------

    def list_all(
        self,
        status: Optional[MemberStatus] = None,
        role: Optional[MemberRole] = None,
        team: Optional[str] = None,
    ) -> list[Member]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status.value)
        if role:
            clauses.append("role = ?")
            params.append(role.value)
        if team:
            clauses.append("team = ?")
            params.append(team)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.fetchall(f"SELECT * FROM members{where} ORDER BY name", tuple(params))
        return [Member.from_row(r) for r in rows]

    # -- Update ----------------------------------------------------------------

    def update(self, member_id: str, **fields: Any) -> Optional[Member]:
        """
        Update arbitrary fields on a member row.  Only supplied keys are
        changed; ``updated_at`` is set automatically.
        """
        if not fields:
            return self.get_by_id(member_id)

        allowed = {
            "name", "email", "github_username", "lark_open_id",
            "role", "position", "team", "status", "lark_tables",
        }
        filtered = {k: v for k, v in fields.items() if k in allowed}
        if not filtered:
            return self.get_by_id(member_id)

        set_parts = [f"{k} = ?" for k in filtered]
        set_parts.append("updated_at = ?")
        values = list(filtered.values())
        values.append(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        values.append(member_id)

        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE members SET {', '.join(set_parts)} WHERE member_id = ?",
                tuple(values),
            )
        return self.get_by_id(member_id)

    # -- Delete (soft) ---------------------------------------------------------

    def deactivate(self, member_id: str) -> Optional[Member]:
        return self.update(member_id, status=MemberStatus.INACTIVE.value)

    def activate(self, member_id: str) -> Optional[Member]:
        return self.update(member_id, status=MemberStatus.ACTIVE.value)
