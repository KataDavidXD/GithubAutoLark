"""Task domain model — local work item linked to GitHub/Lark."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskSource(str, Enum):
    MANUAL = "manual"
    COMMAND = "command"
    GITHUB_SYNC = "github_sync"
    LARK_SYNC = "lark_sync"


@dataclass
class Task:
    """A local work item that may be linked to a GitHub Issue and/or Lark record."""

    title: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    body: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    source: TaskSource = TaskSource.MANUAL
    assignee_member_id: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    target_table: Optional[str] = None
    due_date: Optional[str] = None
    progress: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def labels_json(self) -> str:
        return json.dumps(self.labels)

    @staticmethod
    def parse_labels(raw: Optional[str]) -> list[str]:
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "body": self.body,
            "status": self.status.value,
            "priority": self.priority.value,
            "source": self.source.value,
            "assignee_member_id": self.assignee_member_id,
            "labels": self.labels_json(),
            "target_table": self.target_table,
            "due_date": self.due_date,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Task":
        return cls(
            task_id=row["task_id"],
            title=row["title"],
            body=row.get("body", ""),
            status=TaskStatus(row.get("status", "To Do")),
            priority=TaskPriority(row.get("priority", "medium")),
            source=TaskSource(row.get("source", "manual")),
            assignee_member_id=row.get("assignee_member_id"),
            labels=cls.parse_labels(row.get("labels")),
            target_table=row.get("target_table"),
            due_date=row.get("due_date"),
            progress=row.get("progress", 0),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )
