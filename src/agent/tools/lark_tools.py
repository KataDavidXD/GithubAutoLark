"""Tool functions for the Lark Tables agent."""

from __future__ import annotations

from typing import Any, Optional

from src.db.database import Database
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.member_repo import MemberRepository
from src.db.outbox_repo import OutboxRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.task import Task, TaskSource
from src.models.lark_table_registry import LarkTableConfig
from src.sync.field_mapper import build_lark_record_fields


class LarkTools:
    """Stateful tool collection for Lark Bitable operations."""

    def __init__(self, db: Database, lark_service: Any = None, github_service: Any = None):
        self._db = db
        self._lark = lark_service
        self._github = github_service
        self._task_repo = TaskRepository(db)
        self._mapping_repo = MappingRepository(db)
        self._member_repo = MemberRepository(db)
        self._outbox = OutboxRepository(db)
        self._table_repo = LarkTableRepository(db)

    def _resolve_table(self, table_name: Optional[str]) -> Optional[LarkTableConfig]:
        if table_name:
            return self._table_repo.get_by_name(table_name)
        return self._table_repo.get_default()

    def create_record(
        self,
        title: str,
        table_name: Optional[str] = None,
        assignee: Optional[str] = None,
        status: str = "To Do",
        body: Optional[str] = None,
        send_to_github: bool = False,
    ) -> str:
        """Create a record in a Lark Bitable table."""
        if not self._lark:
            return "Error: Lark service not configured."

        try:
            table_cfg = self._resolve_table(table_name)

            assignee_open_id = None
            member_id = None
            if assignee:
                member = self._member_repo.get_by_email(assignee)
                if not member:
                    results = self._member_repo.find_by_name(assignee)
                    member = results[0] if results else None
                if member:
                    assignee_open_id = member.lark_open_id
                    member_id = member.member_id

            fields = build_lark_record_fields(
                title=title, status=status, body=body,
                assignee_open_id=assignee_open_id,
                table_cfg=table_cfg,
            )

            result = self._lark.create_record(fields, table_cfg=table_cfg)
            record_id = result.get("record", {}).get("record_id", "unknown")

            task = Task(
                title=title, body=body or "",
                source=TaskSource.COMMAND,
                assignee_member_id=member_id,
                target_table=table_cfg.table_name if table_cfg else None,
            )
            self._task_repo.create(task)
            self._mapping_repo.upsert_for_task(
                task.task_id,
                lark_record_id=record_id,
                lark_app_token=table_cfg.app_token if table_cfg else None,
                lark_table_id=table_cfg.table_id if table_cfg else None,
            )

            msg = f"Record '{title}' created in table '{table_cfg.table_name if table_cfg else 'default'}' (ID: {record_id[:12]})."
            if send_to_github:
                self._outbox.enqueue("convert_record_to_github", {
                    "record_id": record_id,
                    "task_id": task.task_id,
                    "app_token": table_cfg.app_token if table_cfg else None,
                    "table_id": table_cfg.table_id if table_cfg else None,
                })
                msg += " Queued for GitHub sync."
            return msg

        except Exception as e:
            return f"Error creating record: {e}"

    def get_record(self, record_id: str, table_name: Optional[str] = None) -> str:
        """Get details of a Lark record."""
        if not self._lark:
            return "Error: Lark service not configured."
        try:
            table_cfg = self._resolve_table(table_name)
            record = self._lark.get_record(record_id, table_cfg=table_cfg)
            fields = record.get("fields", {})
            lines = [f"Record: {record_id}"]
            for key, val in fields.items():
                lines.append(f"  {key}: {val}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching record: {e}"

    def update_record(
        self,
        record_id: str,
        table_name: Optional[str] = None,
        **field_updates: Any,
    ) -> str:
        """Update a Lark record's fields."""
        if not self._lark:
            return "Error: Lark service not configured."
        try:
            table_cfg = self._resolve_table(table_name)
            self._lark.update_record(record_id, field_updates, table_cfg=table_cfg)
            return f"Record {record_id[:12]} updated."
        except Exception as e:
            return f"Error updating record: {e}"

    def list_records(
        self,
        table_name: Optional[str] = None,
        assignee: Optional[str] = None,
        status: Optional[str] = None,
    ) -> str:
        """List records in a Lark table with optional filters."""
        if not self._lark:
            return "Error: Lark service not configured."
        try:
            table_cfg = self._resolve_table(table_name)
            filters = []
            if status:
                fm = table_cfg.field_mapping if table_cfg else {}
                status_field = fm.get("status_field", "Status")
                filters.append({
                    "field_name": status_field,
                    "operator": "is",
                    "value": [status],
                })
            if assignee:
                member = self._member_repo.get_by_email(assignee)
                if not member:
                    results = self._member_repo.find_by_name(assignee)
                    member = results[0] if results else None
                if member and member.lark_open_id:
                    fm = table_cfg.field_mapping if table_cfg else {}
                    assignee_field = fm.get("assignee_field", "Assignee")
                    filters.append({
                        "field_name": assignee_field,
                        "operator": "is",
                        "value": [member.lark_open_id],
                    })

            records = self._lark.search_records(
                filter_conditions=filters if filters else None,
                table_cfg=table_cfg,
            )
            if not records:
                return "No records found."

            lines = [f"Found {len(records)} record(s) in '{table_cfg.table_name if table_cfg else 'default'}':"]
            fm = table_cfg.field_mapping if table_cfg else {}
            title_field = fm.get("title_field", "Task Name")
            status_field = fm.get("status_field", "Status")
            for rec in records[:20]:
                f = rec.get("fields", {})
                t = f.get(title_field, "?")
                s = f.get(status_field, "?")
                lines.append(f"  {rec.get('record_id', '?')[:12]}: {t} [{s}]")
            return "\n".join(lines)

        except Exception as e:
            return f"Error listing records: {e}"

    def list_tables(self) -> str:
        """List all registered Lark tables."""
        tables = self._table_repo.list_all()
        if not tables:
            return "No tables registered."
        lines = [f"Registered tables ({len(tables)}):"]
        for t in tables:
            default = " [DEFAULT]" if t.is_default else ""
            lines.append(f"  - {t.table_name} ({t.table_id}){default}")
        return "\n".join(lines)

    def send_record_to_github(self, record_id: str, table_name: Optional[str] = None) -> str:
        """Convert a Lark record to a GitHub issue."""
        table_cfg = self._resolve_table(table_name)
        mapping = self._mapping_repo.get_by_lark_record(record_id)
        task_id = mapping.task_id if mapping else None

        self._outbox.enqueue("convert_record_to_github", {
            "record_id": record_id,
            "task_id": task_id,
            "app_token": table_cfg.app_token if table_cfg else None,
            "table_id": table_cfg.table_id if table_cfg else None,
        })
        return f"Record {record_id[:12]} queued for conversion to GitHub issue."

    def register_table(
        self,
        table_name: str,
        app_token: str,
        table_id: str,
        is_default: bool = False,
    ) -> str:
        """Register a new Lark table in the system."""
        try:
            cfg = LarkTableConfig(
                app_token=app_token, table_id=table_id,
                table_name=table_name, is_default=is_default,
            )
            self._table_repo.register(cfg)
            return f"Table '{table_name}' registered (ID: {table_id})."
        except Exception as e:
            return f"Error registering table: {e}"
