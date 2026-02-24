"""
Bidirectional Sync Demo Script

This script demonstrates the full sync workflow:
1. Create a task locally
2. Sync to GitHub (create issue)
3. Sync to Lark (create record)
4. Simulate Lark status change -> detect and update GitHub
5. Simulate GitHub status change -> detect and update Lark

Output is saved (redacted) to demos/sync_demo_output.txt
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_lark_bitable_config, get_employee_email, get_demos_dir
from src.db import get_db
from src.sync_engine import SyncEngine, lark_status_to_github_state, github_state_to_lark_status
from src.redact import redact_text


class OutputCapture:
    """Capture print output for saving to file."""
    
    def __init__(self):
        self.buffer = StringIO()
        self._stdout = sys.stdout
    
    def write(self, text: str) -> None:
        self._stdout.write(text)
        self.buffer.write(text)
    
    def flush(self) -> None:
        self._stdout.flush()
    
    def get_output(self) -> str:
        return self.buffer.getvalue()


def main() -> None:
    capture = OutputCapture()
    sys.stdout = capture
    
    try:
        run_demo()
    finally:
        sys.stdout = capture._stdout
        
        # Save redacted output
        output = capture.get_output()
        redacted = redact_text(output)
        
        demos_dir = get_demos_dir()
        demos_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = demos_dir / "sync_demo_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# Sync Demo - {datetime.now().isoformat()}\n")
            f.write("# Output is REDACTED for security\n\n")
            f.write(redacted)
        
        print(f"\n[Output saved to {output_file}]")


def run_demo() -> None:
    config = get_lark_bitable_config()
    employee_email = get_employee_email()
    
    print("=" * 60)
    print("BIDIRECTIONAL SYNC DEMO")
    print("=" * 60)
    print(f"Lark App Token: {config.app_token}")
    print(f"Lark Table ID: {config.tasks_table_id}")
    print(f"Employee Email: {employee_email}")
    print()
    
    # Initialize DB
    db = get_db()
    db.init()
    
    with SyncEngine() as engine:
        # -----------------------------------------------------------------
        # Step 1: Create Task and Sync
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 1: Create Task Locally & Queue Sync")
        print("-" * 40)
        
        task_title = f"[SYNC_DEMO] Test {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task_id = engine.create_task_and_sync(
            title=task_title,
            body="This task tests bidirectional sync between GitHub and Lark.",
            assignee_email=employee_email,
            status="ToDo",
            labels=["sync-demo", "auto"],
        )
        
        print(f"Created task: {task_id}")
        task = db.get_task(task_id)
        print(f"  Title: {task['title']}")
        print(f"  Status: {task['status']}")
        print(f"  Assignee: {task.get('assignee_email')}")
        
        # Check outbox
        pending = db.get_pending_events()
        print(f"\nOutbox has {len(pending)} pending event(s):")
        for e in pending:
            print(f"  - {e['event_type']}")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 2: Process Outbox (Sync to GitHub)
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 2: Process Outbox - Sync to GitHub")
        print("-" * 40)
        
        # Process only GitHub sync first
        processed = engine.process_outbox(limit=1)
        print(f"Processed {processed} event(s)")
        
        mapping = db.get_mapping(task_id)
        if mapping and mapping.get("github_issue_number"):
            print(f"GitHub Issue Created: #{mapping['github_issue_number']}")
        else:
            print("Warning: No GitHub issue created yet")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 3: Process Outbox (Sync to Lark)
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 3: Process Outbox - Sync to Lark")
        print("-" * 40)
        
        processed = engine.process_outbox(limit=1)
        print(f"Processed {processed} event(s)")
        
        mapping = db.get_mapping(task_id)
        if mapping and mapping.get("lark_record_id"):
            print(f"Lark Record Created: {mapping['lark_record_id']}")
        else:
            print("Warning: No Lark record created yet")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 4: Simulate Lark Status Change -> Update GitHub
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 4: Lark Status Change -> Update GitHub")
        print("-" * 40)
        
        # Manually update status in Lark to simulate user change
        if mapping and mapping.get("lark_record_id"):
            print("Updating Lark record status to 'Done'...")
            engine.lark.update_record(mapping["lark_record_id"], {
                config.field_status: "Done"
            })
            print("Lark record updated.")
            time.sleep(2)  # Wait for consistency
            
            # Now check for changes
            print("\nChecking for Lark changes...")
            changes = engine.check_lark_changes()
            print(f"Detected {len(changes)} change(s):")
            for c in changes:
                print(f"  - Task {c['task_id'][:8]}...: {c['old_status']} -> {c['new_status']}")
            
            # Process the status update event
            if changes:
                print("\nProcessing GitHub status update...")
                processed = engine.process_outbox(limit=1)
                print(f"Processed {processed} event(s)")
                
                # Verify GitHub status
                if mapping.get("github_issue_number"):
                    issue = engine.github.get_issue(mapping["github_issue_number"])
                    print(f"GitHub Issue #{mapping['github_issue_number']} state: {issue['state']}")
        else:
            print("Skipping (no Lark record)")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 5: Simulate GitHub Status Change -> Update Lark
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 5: GitHub Status Change -> Update Lark")
        print("-" * 40)
        
        mapping = db.get_mapping(task_id)
        if mapping and mapping.get("github_issue_number"):
            # Reopen the GitHub issue
            print("Reopening GitHub issue...")
            engine.github.reopen_issue(mapping["github_issue_number"])
            print("GitHub issue reopened.")
            time.sleep(2)  # Wait for consistency
            
            # Now check for changes
            print("\nChecking for GitHub changes...")
            changes = engine.check_github_changes()
            print(f"Detected {len(changes)} change(s):")
            for c in changes:
                print(f"  - Task {c['task_id'][:8]}...: {c['old_status']} -> {c['new_status']}")
            
            # Process the status update event
            if changes:
                print("\nProcessing Lark status update...")
                processed = engine.process_outbox(limit=1)
                print(f"Processed {processed} event(s)")
                
                # Verify Lark status
                records = engine.lark.search_records()
                for r in records:
                    if r.get("record_id") == mapping.get("lark_record_id"):
                        status = r.get("fields", {}).get(config.field_status)
                        print(f"Lark Record status: {status}")
                        break
        else:
            print("Skipping (no GitHub issue)")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 6: Final Cleanup
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 6: Cleanup - Close GitHub Issue")
        print("-" * 40)
        
        if mapping and mapping.get("github_issue_number"):
            engine.github.close_issue(mapping["github_issue_number"])
            print(f"Closed GitHub Issue #{mapping['github_issue_number']}")
        
        print()
        print("=" * 60)
        print("BIDIRECTIONAL SYNC DEMO COMPLETE")
        print("=" * 60)
        
        # Summary
        print("\nSummary:")
        print(f"  Task ID: {task_id}")
        if mapping:
            print(f"  GitHub Issue: #{mapping.get('github_issue_number')}")
            print(f"  Lark Record: {mapping.get('lark_record_id')}")
        
        # Show sync log
        print("\nSync Log (last 10 entries):")
        conn = db._get_connection()
        rows = conn.execute(
            "SELECT * FROM sync_log ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        for row in rows:
            print(f"  [{row['status']}] {row['direction']} {row['subject']}: {row['message']}")


if __name__ == "__main__":
    main()
