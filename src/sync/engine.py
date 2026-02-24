"""Outbox-driven sync engine — processes pending events for eventual consistency.

Single Responsibility: dispatches outbox events to the correct handler.
Depends on service abstractions (Dependency Inversion).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from src.db.database import Database
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.outbox_repo import OutboxRepository
from src.db.sync_log_repo import SyncLogRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.mapping import Mapping
from src.sync.status_mapper import lark_status_to_github_state, normalise_status
from src.sync.field_mapper import build_lark_record_fields, github_issue_to_lark_fields


class SyncEngine:
    """Processes outbox events, dispatching to GitHub/Lark services."""

    def __init__(
        self,
        db: Database,
        github_service: Optional[Any] = None,
        lark_service: Optional[Any] = None,
    ):
        self._db = db
        self._task_repo = TaskRepository(db)
        self._mapping_repo = MappingRepository(db)
        self._outbox_repo = OutboxRepository(db)
        self._sync_log = SyncLogRepository(db)
        self._table_repo = LarkTableRepository(db)
        self._github = github_service
        self._lark = lark_service

    def process_batch(self, limit: int = 10) -> int:
        """Process pending outbox events. Returns count of successfully processed."""
        events = self._outbox_repo.get_pending(limit)
        processed = 0

        for event in events:
            event_id = event["event_id"]
            event_type = event["event_type"]
            payload = json.loads(event["payload_json"])

            try:
                self._outbox_repo.mark_processing(event_id)
                self._dispatch(event_type, payload)
                self._outbox_repo.mark_sent(event_id)
                processed += 1
            except Exception as e:
                attempts = event.get("attempts", 0) + 1
                max_attempts = event.get("max_attempts", 5)
                if attempts >= max_attempts:
                    self._outbox_repo.mark_dead(event_id, str(e))
                else:
                    self._outbox_repo.mark_failed(event_id, str(e))
                self._sync_log.log(
                    "outbound", event_type,
                    payload.get("task_id"), "failed", str(e),
                )

        return processed

    def _dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        handlers = {
            "sync_github_create": self._handle_github_create,
            "sync_github_update": self._handle_github_update,
            "sync_github_close": self._handle_github_close,
            "sync_lark_create": self._handle_lark_create,
            "sync_lark_update": self._handle_lark_update,
            "convert_issue_to_lark": self._handle_convert_issue_to_lark,
            "convert_record_to_github": self._handle_convert_record_to_github,
        }
        handler = handlers.get(event_type)
        if handler is None:
            raise ValueError(f"Unknown event type: {event_type}")
        handler(payload)

    # -- GitHub handlers -------------------------------------------------------

    def _handle_github_create(self, payload: dict[str, Any]) -> None:
        if not self._github:
            raise RuntimeError("GitHubService not available")

        task_id = payload["task_id"]
        task = self._task_repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        labels = payload.get("labels", ["auto"])
        title = f"[AUTO][{task_id[:8]}] {task.title}"

        issue = self._github.create_issue(
            title=title, body=task.body or f"Task ID: {task_id}", labels=labels,
        )
        self._mapping_repo.upsert_for_task(
            task_id,
            github_issue_number=issue["number"],
            github_repo=self._github.repo_slug,
        )
        self._sync_log.log("outbound", "github", task_id, "success", f"Created #{issue['number']}")

    def _handle_github_update(self, payload: dict[str, Any]) -> None:
        if not self._github:
            raise RuntimeError("GitHubService not available")

        task_id = payload["task_id"]
        task = self._task_repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        mappings = self._mapping_repo.get_by_task(task_id)
        mapping = next((m for m in mappings if m.github_issue_number), None)
        if not mapping:
            raise ValueError(f"No GitHub mapping for task {task_id}")

        state, state_reason = lark_status_to_github_state(task.status.value)
        self._github.update_issue(
            mapping.github_issue_number,
            title=f"[AUTO][{task_id[:8]}] {task.title}",
            body=task.body,
            state=state,
            state_reason=state_reason,
        )
        self._sync_log.log("outbound", "github", task_id, "success", f"Updated #{mapping.github_issue_number}")

    def _handle_github_close(self, payload: dict[str, Any]) -> None:
        if not self._github:
            raise RuntimeError("GitHubService not available")

        task_id = payload["task_id"]
        mappings = self._mapping_repo.get_by_task(task_id)
        mapping = next((m for m in mappings if m.github_issue_number), None)
        if not mapping:
            raise ValueError(f"No GitHub mapping for task {task_id}")

        self._github.close_issue(mapping.github_issue_number)
        self._sync_log.log("outbound", "github", task_id, "success", f"Closed #{mapping.github_issue_number}")

    # -- Lark handlers ---------------------------------------------------------

    def _handle_lark_create(self, payload: dict[str, Any]) -> None:
        if not self._lark:
            raise RuntimeError("LarkService not available")

        task_id = payload["task_id"]
        task = self._task_repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        table_cfg = self._resolve_table_config(payload, task)
        fields = build_lark_record_fields(
            title=task.title,
            status=normalise_status(task.status.value),
            body=task.body,
            table_cfg=table_cfg,
        )

        result = self._lark.create_record(fields, table_cfg=table_cfg)
        record_id = result.get("record", {}).get("record_id")

        if record_id:
            self._mapping_repo.upsert_for_task(
                task_id,
                lark_record_id=record_id,
                lark_app_token=table_cfg.app_token if table_cfg else None,
                lark_table_id=table_cfg.table_id if table_cfg else None,
            )
        self._sync_log.log("outbound", "lark", task_id, "success", f"Created record {record_id}")

    def _handle_lark_update(self, payload: dict[str, Any]) -> None:
        if not self._lark:
            raise RuntimeError("LarkService not available")

        task_id = payload["task_id"]
        task = self._task_repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        mappings = self._mapping_repo.get_by_task(task_id)
        mapping = next((m for m in mappings if m.lark_record_id), None)
        if not mapping:
            raise ValueError(f"No Lark mapping for task {task_id}")

        table_cfg = self._table_repo.get_by_table_id(
            mapping.lark_app_token or "", mapping.lark_table_id or ""
        )

        fields = build_lark_record_fields(
            title=task.title,
            status=normalise_status(task.status.value),
            body=task.body,
            table_cfg=table_cfg,
        )
        self._lark.update_record(mapping.lark_record_id, fields, table_cfg=table_cfg)
        self._sync_log.log("outbound", "lark", task_id, "success", f"Updated {mapping.lark_record_id}")

    # -- Conversion handlers ---------------------------------------------------

    def _handle_convert_issue_to_lark(self, payload: dict[str, Any]) -> None:
        if not self._github or not self._lark:
            raise RuntimeError("Both services required for conversion")

        issue_number = payload["issue_number"]
        target_table = payload.get("target_table")

        issue = self._github.get_issue(issue_number)
        table_cfg = None
        if target_table:
            table_cfg = self._table_repo.get_by_name(target_table)
        if not table_cfg:
            table_cfg = self._table_repo.get_default()

        fields = github_issue_to_lark_fields(issue, table_cfg=table_cfg)
        result = self._lark.create_record(fields, table_cfg=table_cfg)
        record_id = result.get("record", {}).get("record_id")

        task_id = payload.get("task_id")
        if task_id and record_id:
            self._mapping_repo.upsert_for_task(
                task_id,
                lark_record_id=record_id,
                lark_app_token=table_cfg.app_token if table_cfg else None,
                lark_table_id=table_cfg.table_id if table_cfg else None,
            )
        self._sync_log.log("outbound", "convert", str(issue_number), "success",
                           f"Issue #{issue_number} → Lark {record_id}")

    def _handle_convert_record_to_github(self, payload: dict[str, Any]) -> None:
        if not self._github or not self._lark:
            raise RuntimeError("Both services required for conversion")

        record_id = payload["record_id"]
        app_token = payload.get("app_token")
        table_id = payload.get("table_id")

        table_cfg = None
        if app_token and table_id:
            table_cfg = self._table_repo.get_by_table_id(app_token, table_id)

        record = self._lark.get_record(record_id, table_cfg=table_cfg)
        from src.sync.field_mapper import lark_record_to_github_fields
        gh_fields = lark_record_to_github_fields(record, table_cfg=table_cfg)

        issue = self._github.create_issue(
            title=gh_fields["title"], body=gh_fields.get("body", ""),
        )
        task_id = payload.get("task_id")
        if task_id:
            self._mapping_repo.upsert_for_task(
                task_id,
                github_issue_number=issue["number"],
                github_repo=self._github.repo_slug,
            )
        self._sync_log.log("outbound", "convert", record_id, "success",
                           f"Lark {record_id} → Issue #{issue['number']}")

    # -- helpers ---------------------------------------------------------------

    def _resolve_table_config(
        self, payload: dict[str, Any], task: Any
    ) -> Optional[LarkTableConfig]:
        table_name = payload.get("target_table")
        if table_name:
            cfg = self._table_repo.get_by_name(table_name)
            if cfg:
                return cfg
        if task.target_table:
            cfg = self._table_repo.get_by_name(task.target_table)
            if cfg:
                return cfg
        return self._table_repo.get_default()
