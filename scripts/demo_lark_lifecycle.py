"""
Lark Lifecycle Demo Script

This script demonstrates the full Lark Bitable lifecycle:
1. List existing tables in the Base App
2. List fields in the Tasks table
3. Create a new task record
4. Resolve assignee email -> open_id
5. Assign member to the task
6. Update task status
7. Search and verify the record

Output is saved (redacted) to demos/lark_lifecycle_output.txt
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_lark_bitable_config, get_employee_email, get_repo_root, get_demos_dir
from src.lark_service import LarkService
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
        
        output_file = demos_dir / "lark_lifecycle_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# Lark Lifecycle Demo - {datetime.now().isoformat()}\n")
            f.write("# Output is REDACTED for security\n\n")
            f.write(redacted)
        
        print(f"\n[Output saved to {output_file}]")


def run_demo() -> None:
    config = get_lark_bitable_config()
    employee_email = get_employee_email()
    
    print("=" * 60)
    print("LARK LIFECYCLE DEMO")
    print("=" * 60)
    print(f"App Token: {config.app_token}")
    print(f"Table ID: {config.tasks_table_id}")
    print(f"Employee Email: {employee_email}")
    print()
    
    with LarkService() as svc:
        # -----------------------------------------------------------------
        # Step 1: List Tables
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 1: List Tables")
        print("-" * 40)
        tables = svc.list_tables()
        print(f"Found {len(tables)} table(s):")
        for t in tables:
            print(f"  - {t.get('name')} (id: {t.get('table_id')})")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 2: List Fields
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 2: List Fields in Tasks Table")
        print("-" * 40)
        fields = svc.list_fields()
        print(f"Found {len(fields)} field(s):")
        for f in fields:
            print(f"  - {f.get('field_name')} (type={f.get('type')}, id={f.get('field_id')})")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 3: Create Task Record
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 3: Create Task Record")
        print("-" * 40)
        
        task_title = f"[DEMO] Lifecycle Test {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task_data = {
            config.field_title: task_title,
            config.field_status: "To Do",
        }
        
        print(f"Creating task: {task_title}")
        result = svc.create_record(task_data)
        record = result.get("record", {})
        record_id = record.get("record_id")
        print(f"Created record_id: {record_id}")
        print(f"Fields: {record.get('fields')}")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 4: Resolve Assignee
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 4: Resolve Assignee Email -> open_id")
        print("-" * 40)
        
        if employee_email:
            print(f"Looking up: {employee_email}")
            open_id = svc.get_user_id_by_email(employee_email)
            print(f"Resolved open_id: {open_id}")
        else:
            print("No EMPLOYEE_EMAIL configured, skipping assignee resolution")
            open_id = None
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 5: Assign Member
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 5: Assign Member to Task")
        print("-" * 40)
        
        if open_id and record_id:
            # Assignee field expects array of {id: open_id}
            assignee_value = [{"id": open_id}]
            update_result = svc.update_record(record_id, {
                config.field_assignee: assignee_value
            })
            print(f"Updated record with assignee")
            print(f"Result: {update_result.get('record', {}).get('fields')}")
        else:
            print("Skipping (no open_id or record_id)")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 6: Update Status
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 6: Update Task Status")
        print("-" * 40)
        
        if record_id:
            # Update to "In Progress"
            update_result = svc.update_record(record_id, {
                config.field_status: "In Progress"
            })
            print("Updated status to: In Progress")
            print(f"Result: {update_result.get('record', {}).get('fields')}")
            
            time.sleep(1)
            
            # Update to "Done"
            update_result = svc.update_record(record_id, {
                config.field_status: "Done"
            })
            print("Updated status to: Done")
            print(f"Result: {update_result.get('record', {}).get('fields')}")
        else:
            print("Skipping (no record_id)")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 7: Search & Verify
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 7: Search & Verify Record")
        print("-" * 40)
        
        records = svc.search_records()
        print(f"Total records in table: {len(records)}")
        
        # Find our record
        found = None
        for r in records:
            if r.get("record_id") == record_id:
                found = r
                break
        
        if found:
            print(f"\nFound our record:")
            print(f"  record_id: {found.get('record_id')}")
            print(f"  fields: {found.get('fields')}")
        else:
            print(f"Warning: Could not find record {record_id}")
        
        print()
        print("=" * 60)
        print("LARK LIFECYCLE DEMO COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
