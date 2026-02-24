"""Member domain model — unified identity across GitHub and Lark."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class MemberRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"
    DESIGNER = "designer"
    QA = "qa"
    MEMBER = "member"


class MemberStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass
class LarkTableAssignment:
    """A Lark table that a member is assigned to."""
    app_token: str
    table_id: str
    table_name: str


@dataclass
class Member:
    """Unified team member across GitHub and Lark platforms."""

    name: str
    email: str
    role: MemberRole = MemberRole.MEMBER
    member_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    github_username: Optional[str] = None
    lark_open_id: Optional[str] = None
    position: Optional[str] = None
    team: Optional[str] = None
    status: MemberStatus = MemberStatus.ACTIVE
    lark_tables: list[LarkTableAssignment] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    # -- Serialisation helpers for SQLite JSON columns --

    def lark_tables_json(self) -> str:
        return json.dumps(
            [{"app_token": t.app_token, "table_id": t.table_id, "table_name": t.table_name}
             for t in self.lark_tables]
        )

    @staticmethod
    def parse_lark_tables(raw: Optional[str]) -> list[LarkTableAssignment]:
        if not raw:
            return []
        try:
            items = json.loads(raw)
            return [LarkTableAssignment(**item) for item in items]
        except (json.JSONDecodeError, TypeError):
            return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "name": self.name,
            "email": self.email,
            "github_username": self.github_username,
            "lark_open_id": self.lark_open_id,
            "role": self.role.value,
            "position": self.position,
            "team": self.team,
            "status": self.status.value,
            "lark_tables": self.lark_tables_json(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Member":
        return cls(
            member_id=row["member_id"],
            name=row["name"],
            email=row["email"],
            github_username=row.get("github_username"),
            lark_open_id=row.get("lark_open_id"),
            role=MemberRole(row.get("role", "member")),
            position=row.get("position"),
            team=row.get("team"),
            status=MemberStatus(row.get("status", "active")),
            lark_tables=cls.parse_lark_tables(row.get("lark_tables")),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )
