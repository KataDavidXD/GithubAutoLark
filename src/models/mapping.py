"""Mapping domain model — links a local task to GitHub Issue and/or Lark record."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class SyncStatus(str, Enum):
    SYNCED = "synced"
    PENDING = "pending"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass
class Mapping:
    """Bidirectional link between a local task and its remote representations."""

    task_id: str
    mapping_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    github_issue_number: Optional[int] = None
    github_repo: Optional[str] = None
    lark_record_id: Optional[str] = None
    lark_app_token: Optional[str] = None
    lark_table_id: Optional[str] = None
    field_mapping: dict[str, str] = field(default_factory=dict)
    sync_status: SyncStatus = SyncStatus.SYNCED
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def field_mapping_json(self) -> str:
        return json.dumps(self.field_mapping)

    @staticmethod
    def parse_field_mapping(raw: Optional[str]) -> dict[str, str]:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "task_id": self.task_id,
            "github_issue_number": self.github_issue_number,
            "github_repo": self.github_repo,
            "lark_record_id": self.lark_record_id,
            "lark_app_token": self.lark_app_token,
            "lark_table_id": self.lark_table_id,
            "field_mapping": self.field_mapping_json(),
            "sync_status": self.sync_status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Mapping":
        return cls(
            mapping_id=row["mapping_id"],
            task_id=row["task_id"],
            github_issue_number=row.get("github_issue_number"),
            github_repo=row.get("github_repo"),
            lark_record_id=row.get("lark_record_id"),
            lark_app_token=row.get("lark_app_token"),
            lark_table_id=row.get("lark_table_id"),
            field_mapping=cls.parse_field_mapping(row.get("field_mapping")),
            sync_status=SyncStatus(row.get("sync_status", "synced")),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )
