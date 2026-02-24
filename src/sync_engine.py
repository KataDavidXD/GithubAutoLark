"""
Sync Engine - Bidirectional sync between GitHub Issues and Lark Bitable.

Responsibilities:
- Sync local tasks to GitHub Issues
- Sync local tasks to Lark Bitable records
- Detect status changes in Lark -> update GitHub
- Detect status changes in GitHub -> update Lark
- Use outbox pattern for ACID + eventual consistency
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.config import get_lark_bitable_config, LarkBitableConfig
from src.db import Database, get_db
from src.github_service import GitHubService
from src.lark_service import LarkService


# ---------------------------------------------------------------------------
# Status Mapping (pure functions for testability)
# ---------------------------------------------------------------------------

def lark_status_to_github_state(lark_status: str) -> tuple[str, Optional[str]]:
    """
    Map Lark status to GitHub issue state.
    
    Returns: (state, state_reason)
    - state: 'open' or 'closed'
    - state_reason: 'completed', 'not_planned', 'reopened', or None
    """
    status_lower = lark_status.lower().replace(" ", "")
    
    if status_lower == "done":
        return ("closed", "completed")
    elif status_lower in ("todo", "inprogress"):
        return ("open", None)
    else:
        # Default to open for unknown statuses
        return ("open", None)


def github_state_to_lark_status(github_state: str, current_lark_status: Optional[str] = None) -> str:
    """
    Map GitHub issue state to Lark status.
    
    If the issue is open and Lark is already "In Progress", keep it as "In Progress".
    """
    if github_state == "closed":
        return "Done"
    elif github_state == "open":
        # Preserve "In Progress" if already there
        if current_lark_status and current_lark_status.lower().replace(" ", "") == "inprogress":
            return "In Progress"
        return "To Do"
    else:
        return "To Do"


# ---------------------------------------------------------------------------
# Sync Engine
# ---------------------------------------------------------------------------

@dataclass
class SyncEngine:
    """
    Orchestrates bidirectional sync between local DB, GitHub, and Lark.
    
    Usage:
        with SyncEngine() as engine:
            engine.create_task_and_sync("My task", "Description", "yli@example.com")
            engine.sync_all_pending()
    """
    
    db: Database = field(default_factory=get_db)
    lark_config: LarkBitableConfig = field(default_factory=get_lark_bitable_config)
    _github_svc: Optional[GitHubService] = field(default=None, init=False, repr=False)
    _lark_svc: Optional[LarkService] = field(default=None, init=False, repr=False)
    
    def __enter__(self) -> "SyncEngine":
        self.db.init()
        self._github_svc = GitHubService()
        self._lark_svc = LarkService()
        self._lark_svc.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._lark_svc:
            self._lark_svc.__exit__(exc_type, exc_val, exc_tb)
    
    @property
    def github(self) -> GitHubService:
        if self._github_svc is None:
            raise RuntimeError("SyncEngine must be used as context manager")
        return self._github_svc
    
    @property
    def lark(self) -> LarkService:
        if self._lark_svc is None:
            raise RuntimeError("SyncEngine must be used as context manager")
        return self._lark_svc
    
    # -------------------------------------------------------------------------
    # Task Creation with Sync
    # -------------------------------------------------------------------------
    
    def create_task_and_sync(
        self,
        title: str,
        body: str = "",
        assignee_email: Optional[str] = None,
        status: str = "ToDo",
        labels: Optional[list[str]] = None,
    ) -> str:
        """
        Create a task locally, then sync to GitHub and Lark.
        
        Uses outbox pattern: local writes are atomic, external calls are idempotent.
        
        Returns the task_id.
        """
        # Resolve assignee if provided
        assignee_open_id = None
        if assignee_email:
            employee = self.db.get_employee(assignee_email)
            if employee and employee.get("lark_open_id"):
                assignee_open_id = employee["lark_open_id"]
            else:
                # Resolve from Lark
                assignee_open_id = self.lark.get_user_id_by_email(assignee_email)
                if assignee_open_id:
                    self.db.upsert_employee(assignee_email, assignee_open_id)
        
        # Create task in DB
        task_id = self.db.create_task(
            title=title,
            body=body,
            status=status,
            source="manual",
            assignee_email=assignee_email,
            assignee_open_id=assignee_open_id,
        )
        
        # Enqueue outbox events for external sync
        self.db.enqueue_event("sync_github", {
            "task_id": task_id,
            "action": "create",
            "labels": labels or ["auto"],
        })
        
        self.db.enqueue_event("sync_lark", {
            "task_id": task_id,
            "action": "create",
        })
        
        # Log
        self.db.log_sync("outbound", "task", task_id, "pending", "Task created, sync queued")
        
        return task_id
    
    # -------------------------------------------------------------------------
    # Outbox Processing
    # -------------------------------------------------------------------------
    
    def process_outbox(self, limit: int = 10) -> int:
        """
        Process pending outbox events.
        
        Returns the number of events processed.
        """
        events = self.db.get_pending_events(limit=limit)
        processed = 0
        
        for event in events:
            event_id = event["event_id"]
            event_type = event["event_type"]
            payload = json.loads(event["payload_json"])
            
            try:
                if event_type == "sync_github":
                    self._process_github_sync(payload)
                elif event_type == "sync_lark":
                    self._process_lark_sync(payload)
                elif event_type == "update_github_status":
                    self._process_github_status_update(payload)
                elif event_type == "update_lark_status":
                    self._process_lark_status_update(payload)
                else:
                    raise ValueError(f"Unknown event type: {event_type}")
                
                self.db.mark_event_sent(event_id)
                processed += 1
                
            except Exception as e:
                self.db.mark_event_failed(event_id, str(e))
                self.db.log_sync("outbound", event_type, payload.get("task_id"), "failed", str(e))
        
        return processed
    
    def _process_github_sync(self, payload: dict) -> None:
        """Sync a task to GitHub (create or update issue)."""
        task_id = payload["task_id"]
        action = payload.get("action", "create")
        labels = payload.get("labels", ["auto"])
        
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        mapping = self.db.get_mapping(task_id)
        
        # Add idempotency prefix to title
        prefixed_title = f"[AUTO][{task_id[:8]}] {task['title']}"
        
        if mapping and mapping.get("github_issue_number"):
            # Update existing issue
            issue_number = mapping["github_issue_number"]
            state, state_reason = lark_status_to_github_state(task["status"])
            
            self.github.update_issue(
                issue_number,
                title=prefixed_title,
                body=task["body"],
                state=state,
                state_reason=state_reason,
                labels=labels,
            )
        else:
            # Create new issue
            issue = self.github.create_issue(
                title=prefixed_title,
                body=task["body"] or f"Task ID: {task_id}",
                labels=labels,
            )
            
            # Update mapping
            self.db.upsert_mapping(task_id, github_issue_number=issue["number"])
        
        self.db.log_sync("outbound", "github", task_id, "success", f"Synced to GitHub")
    
    def _process_lark_sync(self, payload: dict) -> None:
        """Sync a task to Lark Bitable (create or update record)."""
        task_id = payload["task_id"]
        
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        mapping = self.db.get_mapping(task_id)
        config = self.lark_config
        
        # Build record fields
        fields: dict[str, Any] = {
            config.field_title: task["title"],
            config.field_status: self._normalize_status_for_lark(task["status"]),
        }
        
        # Add assignee if available
        if task.get("assignee_open_id"):
            fields[config.field_assignee] = [{"id": task["assignee_open_id"]}]
        
        # Add GitHub issue link if available
        if mapping and mapping.get("github_issue_number"):
            fields[config.field_github_issue] = mapping["github_issue_number"]
        
        # Add last sync timestamp
        fields[config.field_last_sync] = int(datetime.now().timestamp() * 1000)
        
        if mapping and mapping.get("lark_record_id"):
            # Update existing record
            self.lark.update_record(mapping["lark_record_id"], fields)
        else:
            # Create new record
            result = self.lark.create_record(fields)
            record_id = result.get("record", {}).get("record_id")
            
            if record_id:
                self.db.upsert_mapping(
                    task_id,
                    lark_record_id=record_id,
                    lark_app_token=config.app_token,
                    lark_table_id=config.tasks_table_id,
                )
        
        self.db.log_sync("outbound", "lark", task_id, "success", "Synced to Lark")
    
    def _process_github_status_update(self, payload: dict) -> None:
        """Update GitHub issue status based on Lark change."""
        task_id = payload["task_id"]
        new_status = payload["new_status"]
        
        mapping = self.db.get_mapping(task_id)
        if not mapping or not mapping.get("github_issue_number"):
            raise ValueError(f"No GitHub mapping for task {task_id}")
        
        state, state_reason = lark_status_to_github_state(new_status)
        
        self.github.update_issue(
            mapping["github_issue_number"],
            state=state,
            state_reason=state_reason,
        )
        
        self.db.log_sync("outbound", "github_status", task_id, "success", f"Status -> {state}")
    
    def _process_lark_status_update(self, payload: dict) -> None:
        """Update Lark record status based on GitHub change."""
        task_id = payload["task_id"]
        new_status = payload["new_status"]
        
        mapping = self.db.get_mapping(task_id)
        if not mapping or not mapping.get("lark_record_id"):
            raise ValueError(f"No Lark mapping for task {task_id}")
        
        self.lark.update_record(mapping["lark_record_id"], {
            self.lark_config.field_status: new_status,
            self.lark_config.field_last_sync: int(datetime.now().timestamp() * 1000),
        })
        
        self.db.log_sync("outbound", "lark_status", task_id, "success", f"Status -> {new_status}")
    
    def _normalize_status_for_lark(self, status: str) -> str:
        """Normalize status string for Lark (must match option names exactly)."""
        status_map = {
            "todo": "To Do",
            "inprogress": "In Progress",
            "done": "Done",
        }
        return status_map.get(status.lower().replace(" ", ""), "To Do")
    
    # -------------------------------------------------------------------------
    # Polling / Change Detection
    # -------------------------------------------------------------------------
    
    def check_lark_changes(self) -> list[dict]:
        """
        Check Lark for status changes and queue updates to GitHub.
        
        Returns list of detected changes.
        """
        changes = []
        records = self.lark.search_records()
        
        for record in records:
            record_id = record.get("record_id")
            fields = record.get("fields", {})
            
            # Get current status from Lark
            lark_status_raw = fields.get(self.lark_config.field_status)
            if isinstance(lark_status_raw, dict):
                lark_status = lark_status_raw.get("name", lark_status_raw.get("text", "To Do"))
            else:
                lark_status = str(lark_status_raw) if lark_status_raw else "To Do"
            
            # Find corresponding local task
            mapping = self.db.get_mapping_by_lark_record(record_id)
            if not mapping:
                continue
            
            task = self.db.get_task(mapping["task_id"])
            if not task:
                continue
            
            # Check if status changed
            local_status = task["status"]
            normalized_lark = self._normalize_status_for_lark(lark_status)
            normalized_local = self._normalize_status_for_lark(local_status)
            
            if normalized_lark != normalized_local:
                # Update local status
                self.db.update_task(mapping["task_id"], status=normalized_lark)
                
                # Queue GitHub update
                self.db.enqueue_event("update_github_status", {
                    "task_id": mapping["task_id"],
                    "new_status": normalized_lark,
                })
                
                changes.append({
                    "task_id": mapping["task_id"],
                    "source": "lark",
                    "old_status": normalized_local,
                    "new_status": normalized_lark,
                })
                
                self.db.log_sync("inbound", "lark", mapping["task_id"], "detected",
                                 f"Status change: {normalized_local} -> {normalized_lark}")
        
        return changes
    
    def check_github_changes(self) -> list[dict]:
        """
        Check GitHub for status changes and queue updates to Lark.
        
        Returns list of detected changes.
        """
        changes = []
        
        # Get all issues (both open and closed)
        issues = self.github.list_issues(state="all", labels="auto", per_page=50)
        
        for issue in issues:
            issue_number = issue["number"]
            github_state = issue["state"]
            
            # Find corresponding local task
            mapping = self.db.get_mapping_by_github_issue(issue_number)
            if not mapping:
                continue
            
            task = self.db.get_task(mapping["task_id"])
            if not task:
                continue
            
            # Convert GitHub state to Lark status
            current_lark_status = task["status"]
            expected_lark_status = github_state_to_lark_status(github_state, current_lark_status)
            
            if expected_lark_status != self._normalize_status_for_lark(current_lark_status):
                # Update local status
                self.db.update_task(mapping["task_id"], status=expected_lark_status)
                
                # Queue Lark update
                self.db.enqueue_event("update_lark_status", {
                    "task_id": mapping["task_id"],
                    "new_status": expected_lark_status,
                })
                
                changes.append({
                    "task_id": mapping["task_id"],
                    "source": "github",
                    "old_status": current_lark_status,
                    "new_status": expected_lark_status,
                })
                
                self.db.log_sync("inbound", "github", mapping["task_id"], "detected",
                                 f"Status change: {current_lark_status} -> {expected_lark_status}")
        
        return changes


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def sync_all() -> int:
    """Process all pending sync events."""
    with SyncEngine() as engine:
        return engine.process_outbox(limit=100)


if __name__ == "__main__":
    print("Testing sync engine...")
    with SyncEngine() as engine:
        print("Creating test task...")
        task_id = engine.create_task_and_sync(
            title="[TEST] Sync Engine Test",
            body="Testing the sync engine",
            status="ToDo",
            labels=["test", "auto"],
        )
        print(f"Created task: {task_id}")
        
        print("\nProcessing outbox...")
        processed = engine.process_outbox()
        print(f"Processed {processed} events")
