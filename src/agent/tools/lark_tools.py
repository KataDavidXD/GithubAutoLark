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
        cfg = self._table_repo.get_default()
        if cfg:
            return cfg
        # No default — fall back to the most recently registered table
        all_tables = self._table_repo.list_all()
        return all_tables[-1] if all_tables else None

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

    def create_task_table(self, table_name: str, tasks: list[dict] = None) -> str:
        """Create a new Lark table for TASKS (not members) with proper task fields.
        
        This creates a task tracking table with:
        - Task Name (text)
        - Description (text)
        - Assignee (Person - linked to Lark user)
        - Status (single select: To Do / In Progress / Done)
        - Priority (single select: High / Medium / Low)
        - Due Date (date)
        - Progress (number 0-100)
        - GitHub Issue (number)
        
        Args:
            table_name: Name for the new task table (e.g., "Sprint_1")
            tasks: Optional list of tasks to create immediately, e.g.:
                [{"title": "SDK packaging", "assignee": "Yang Li"}, ...]
        
        NOTE: This is different from create_team_table which creates a member roster.
        """
        if not self._lark:
            return "Error: Lark service not configured."
        
        import os
        app_token = os.getenv("LARK_APP_TOKEN")
        if not app_token:
            return "Error: LARK_APP_TOKEN not configured."
        
        try:
            from datetime import datetime
            task_fields = [
                {"field_name": "Task Name", "type": 1},
                {"field_name": "Description", "type": 1},
                {"field_name": "Assignee", "type": 11},
                {"field_name": "Status", "type": 3, "property": {
                    "options": [
                        {"name": "To Do"},
                        {"name": "In Progress"},
                        {"name": "Done"},
                    ]
                }},
                {"field_name": "Priority", "type": 3, "property": {
                    "options": [
                        {"name": "High"},
                        {"name": "Medium"},
                        {"name": "Low"},
                    ]
                }},
                {"field_name": "Due Date", "type": 5},
                {"field_name": "Progress", "type": 2},
                {"field_name": "GitHub Issue", "type": 2},
            ]
            
            # Try creating table; on duplicate name, append date suffix
            actual_name = table_name
            result = None
            for attempt in range(3):
                try:
                    result = self._lark.create_table(actual_name, task_fields, app_token=app_token)
                    break
                except Exception as e:
                    if "TableNameDuplicated" in str(e) or "Duplicated" in str(e):
                        suffix = datetime.now().strftime("_%m%d")
                        actual_name = f"{table_name}{suffix}" if attempt == 0 else f"{table_name}{suffix}_{attempt}"
                    else:
                        raise
            
            if result is None:
                return f"Error: Could not create table '{table_name}' after retries."
            
            table_id = result.get("table_id")
            if not table_id:
                return f"Error: Failed to create table. Response: {result}"
            
            # Register with task-specific field mapping
            cfg = LarkTableConfig(
                app_token=app_token,
                table_id=table_id,
                table_name=actual_name,
                is_default=False,
                field_mapping={
                    "title_field": "Task Name",
                    "description_field": "Description",
                    "status_field": "Status",
                    "assignee_field": "Assignee",
                    "priority_field": "Priority",
                    "due_date_field": "Due Date",
                    "progress_field": "Progress",
                    "github_issue_field": "GitHub Issue",
                }
            )
            self._table_repo.register(cfg)
            
            msg = f"Task table '{actual_name}' created (ID: {table_id})."
            
            # Create task records if provided
            if tasks:
                added = 0
                not_found = []
                task_results = []
                
                for t in tasks:
                    title = t.get("title", "Untitled")
                    assignee_name = t.get("assignee", "")
                    desc = t.get("description", t.get("body", ""))
                    
                    # Look up assignee's Lark open_id
                    assignee_id = None
                    assignee_found = False
                    if assignee_name:
                        search = self._member_repo.find_by_name(assignee_name)
                        if search and search[0].lark_open_id:
                            assignee_id = search[0].lark_open_id
                            assignee_found = True
                        else:
                            not_found.append(assignee_name)
                    
                    try:
                        record_fields = {
                            "Task Name": title,
                            "Status": "To Do",
                            "Priority": "Medium",
                        }
                        if desc:
                            record_fields["Description"] = desc
                        
                        # Use Person field format: [{"id": "open_id"}]
                        if assignee_id:
                            record_fields["Assignee"] = [{"id": assignee_id}]
                        
                        # Create record with user_id_type for Person field
                        self._lark.direct.create_record(
                            app_token, table_id, record_fields, 
                            user_id_type="open_id"
                        )
                        added += 1
                        status = f"-> {assignee_name}" if assignee_found else f"-> {assignee_name} (NOT FOUND)"
                        task_results.append(f"  - {title} {status}")
                    except Exception as e:
                        task_results.append(f"  - {title} FAILED: {e}")
                
                msg += f"\nCreated {added}/{len(tasks)} tasks:\n" + "\n".join(task_results)
                
                if not_found:
                    msg += f"\n\nWARNING: Members not found in DB (need to sync first): {', '.join(set(not_found))}"
            
            return msg
            
        except Exception as e:
            return f"Error creating task table: {e}"

    def create_team_table(self, table_name: str, add_all_members: bool = True) -> str:
        """Create a new Lark table for team members and optionally add all members.
        
        Args:
            table_name: Name for the new table (e.g., "MAS_Engine")
            add_all_members: If True, add all members from local DB to the table
        """
        if not self._lark:
            return "Error: Lark service not configured."
        
        import os
        app_token = os.getenv("LARK_APP_TOKEN")
        if not app_token:
            return "Error: LARK_APP_TOKEN not configured."
        
        try:
            fields = [
                {"field_name": "Name", "type": 1},
                {"field_name": "Email", "type": 1},
                {"field_name": "Role", "type": 3, "property": {
                    "options": [
                        {"name": "Manager"},
                        {"name": "Developer"},
                        {"name": "Member"},
                    ]
                }},
                {"field_name": "Team", "type": 1},
                {"field_name": "Status", "type": 3, "property": {
                    "options": [
                        {"name": "Active"},
                        {"name": "Inactive"},
                    ]
                }},
                {"field_name": "GitHub", "type": 1},
                {"field_name": "Lark ID", "type": 1},
            ]
            
            result = self._lark.create_table(table_name, fields, app_token=app_token)
            table_id = result.get("table_id")
            
            if not table_id:
                return f"Error: Failed to create table. Response: {result}"
            
            cfg = LarkTableConfig(
                app_token=app_token,
                table_id=table_id,
                table_name=table_name,
                is_default=False,
                field_mapping={
                    "title_field": "Name",
                    "status_field": "Status",
                    "assignee_field": "Name",
                }
            )
            self._table_repo.register(cfg)
            
            msg = f"Table '{table_name}' created (ID: {table_id})."
            
            if add_all_members:
                members = self._member_repo.list_all()
                added = 0
                errors = []
                
                for m in members:
                    try:
                        fields_data = {
                            "Name": m.name,
                            "Email": m.email or "",
                            "Role": m.role.value.capitalize() if hasattr(m.role, 'value') else "Member",
                            "Team": m.team or table_name,
                            "Status": "Active",
                            "GitHub": m.github_username or "",
                            "Lark ID": m.lark_open_id[:20] + "..." if m.lark_open_id else "",
                        }
                        self._lark.create_record(fields_data, app_token=app_token, table_id=table_id)
                        added += 1
                    except Exception as e:
                        errors.append(f"{m.name}: {e}")
                
                msg += f" Added {added}/{len(members)} members."
                if errors:
                    msg += f" Errors: {errors[:3]}"
            
            return msg
            
        except Exception as e:
            return f"Error creating table: {e}"

    def create_tasks_batch(
        self,
        tasks: list[dict],
        table_name: str,
        create_github_issues: bool = False,
    ) -> str:
        """Create multiple tasks at once with assignees.
        
        Args:
            tasks: List of task dicts with keys: title, assignee, body (optional)
            table_name: Target Lark table name
            create_github_issues: Also create GitHub issues
        
        Example:
            tasks = [
                {"title": "SDK packaging", "assignee": "Yang Li"},
                {"title": "Demo migration", "assignee": "Ethan"},
            ]
        """
        if not self._lark:
            return "Error: Lark service not configured."
        
        table_cfg = self._table_repo.get_by_name(table_name)
        if not table_cfg:
            return f"Table '{table_name}' not found. Create it first with task fields."
        
        # Get field mapping
        fm = table_cfg.field_mapping if table_cfg else {}
        title_field = fm.get("title_field", "Task Name")
        assignee_field = fm.get("assignee_field", "Assignee")
        status_field = fm.get("status_field", "Status")
        
        # Build name->member lookup for fuzzy matching
        all_members = self._member_repo.list_all()
        
        results = []
        for t in tasks:
            title = t.get("title", "Untitled")
            assignee_name = t.get("assignee", "")
            body = t.get("body", "")
            
            # Fuzzy match assignee to member
            assignee_open_id = None
            matched_name = assignee_name
            if assignee_name:
                assignee_lower = assignee_name.lower()
                for m in all_members:
                    # Match by name (partial match)
                    if (assignee_lower in m.name.lower() or 
                        m.name.lower() in assignee_lower or
                        (m.github_username and assignee_lower in m.github_username.lower())):
                        if m.lark_open_id:
                            assignee_open_id = m.lark_open_id
                            matched_name = f"{m.name} ({assignee_name})"
                            break
            
            try:
                fields = {title_field: title}
                
                # Use Person field with open_id if available
                if assignee_open_id:
                    fields[assignee_field] = [{"id": assignee_open_id}]
                
                if status_field:
                    fields[status_field] = "To Do"
                
                if body:
                    desc_field = fm.get("description_field", "Description")
                    if desc_field:
                        fields[desc_field] = body
                
                self._lark.create_record(
                    fields,
                    app_token=table_cfg.app_token,
                    table_id=table_cfg.table_id,
                )
                link_status = "LINKED" if assignee_open_id else "unlinked"
                results.append(f"'{title}' -> {matched_name} [{link_status}]")
            except Exception as e:
                results.append(f"'{title}' FAILED: {e}")
        
        success_count = len([r for r in results if 'FAILED' not in r])
        linked_count = len([r for r in results if 'LINKED' in r])
        return f"Created {success_count}/{len(tasks)} tasks ({linked_count} linked to members):\n" + "\n".join(results)

    def add_member_to_table(self, member_name: str, table_name: str) -> str:
        """Add a member from local DB to a Lark table."""
        if not self._lark:
            return "Error: Lark service not configured."
        
        member = None
        results = self._member_repo.find_by_name(member_name)
        if results:
            member = results[0]
        else:
            member = self._member_repo.get_by_email(member_name)
        
        if not member:
            return f"Member '{member_name}' not found in local DB."
        
        table_cfg = self._table_repo.get_by_name(table_name)
        if not table_cfg:
            return f"Table '{table_name}' not registered. Create it first."
        
        try:
            fields_data = {
                "Name": member.name,
                "Email": member.email or "",
                "Role": member.role.value.capitalize() if hasattr(member.role, 'value') else "Member",
                "Team": member.team or table_name,
                "Status": "Active",
                "GitHub": member.github_username or "",
                "Lark ID": member.lark_open_id[:20] + "..." if member.lark_open_id else "",
            }
            result = self._lark.create_record(
                fields_data,
                app_token=table_cfg.app_token,
                table_id=table_cfg.table_id,
            )
            record_id = result.get("record", {}).get("record_id", "unknown")
            return f"Member '{member.name}' added to '{table_name}' (Record: {record_id[:12]})"
        except Exception as e:
            return f"Error adding member: {e}"
