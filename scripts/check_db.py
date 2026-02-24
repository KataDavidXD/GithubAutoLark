"""Quick check of database state."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import get_db

db = get_db()
db.init()

print("=== Tasks ===")
tasks = db.list_tasks()
print(f"Total: {len(tasks)}")
for t in tasks:
    print(f"  {t['task_id'][:8]} | {t['title'][:40]:<40} | {t['status']}")

print("\n=== Mappings ===")
import sqlite3
from src.config import get_db_path
db_path = get_db_path()
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM mappings").fetchall()
print(f"Total: {len(rows)}")
for r in rows:
    gh = f"#{r['github_issue_number']}" if r['github_issue_number'] else "N/A"
    lark = r['lark_record_id'][:12] + "..." if r['lark_record_id'] else "N/A"
    print(f"  {r['task_id'][:8]} -> GH: {gh:<5} | Lark: {lark}")
conn.close()

print("\n=== Employees ===")
rows = sqlite3.connect(db_path).execute("SELECT * FROM employees").fetchall()
print(f"Total: {len(rows)}")
for r in rows:
    print(f"  {r[0]} -> {r[1][:20] if r[1] else 'N/A'}...")
