"""Lark table registry model — configurable multi-table support."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# Default field mapping that most Lark task tables use
DEFAULT_FIELD_MAPPING: dict[str, str] = {
    "title_field": "Task Name",
    "status_field": "Status",
    "assignee_field": "Assignee",
    "github_issue_field": "GitHub Issue",
    "last_sync_field": "Last Sync",
    "priority_field": "Priority",
    "description_field": "Description",
}


@dataclass
class LarkTableConfig:
    """Configuration for a registered Lark Bitable table."""

    app_token: str
    table_id: str
    table_name: str
    registry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: Optional[str] = None
    field_mapping: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FIELD_MAPPING))
    is_default: bool = False
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
            return dict(DEFAULT_FIELD_MAPPING)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return dict(DEFAULT_FIELD_MAPPING)

    def get_field(self, key: str) -> str:
        """Get a Lark field name by logical key, with fallback to default."""
        return self.field_mapping.get(key, DEFAULT_FIELD_MAPPING.get(key, key))

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "app_token": self.app_token,
            "table_id": self.table_id,
            "table_name": self.table_name,
            "description": self.description,
            "field_mapping": self.field_mapping_json(),
            "is_default": 1 if self.is_default else 0,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "LarkTableConfig":
        return cls(
            registry_id=row["registry_id"],
            app_token=row["app_token"],
            table_id=row["table_id"],
            table_name=row["table_name"],
            description=row.get("description"),
            field_mapping=cls.parse_field_mapping(row.get("field_mapping")),
            is_default=bool(row.get("is_default", 0)),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )
