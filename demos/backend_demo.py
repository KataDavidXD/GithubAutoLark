#!/usr/bin/env python3
"""
Comprehensive Backend Demo - GitHub Issues & Lark Tasks
========================================================
This demo:
1. Syncs users from GitHub/Lark to local DB (local DB is source of truth)
2. Creates two Lark tables: MAS Engine + Agent Optimization WTB
3. Creates tasks with dates, GitHub issues, assignees, and progress tracking
4. Demonstrates natural language queries

Run: python demos/backend_demo.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.member import Member, MemberRole
from src.models.task import Task, TaskStatus, TaskSource
from src.models.lark_table_registry import LarkTableConfig
from src.services.github_service import GitHubService
from src.services.lark_service import LarkService
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.lark_tools import LarkTools


class BackendDemo:
    """Full backend integration demo."""
    
    def __init__(self, db_path: str = "data/demo.db"):
        print("\n" + "=" * 60)
        print("GITHUBAUTO-LARK BACKEND DEMO")
        print("=" * 60)
        
        self.db = Database(path=Path(db_path))
        self.db.init()
        
        self.member_repo = MemberRepository(self.db)
        self.task_repo = TaskRepository(self.db)
        self.mapping_repo = MappingRepository(self.db)
        self.table_repo = LarkTableRepository(self.db)
        
        self.github_svc = GitHubService()
        self.lark_svc = LarkService()
        self.lark_svc.use_direct_api = True
        
        self.github_tools = GitHubTools(self.db, self.github_svc, self.lark_svc)
        self.lark_tools = LarkTools(self.db, self.lark_svc, self.github_svc)
        
        self.created_issues: list[int] = []
        self.created_records: list[str] = []
        
        github_owner = os.getenv("OWNER", "")
        github_repo = os.getenv("REPO", "")
        self.github_slug = f"{github_owner}/{github_repo}" if github_owner and github_repo else "Not configured"
        
        print(f"Database: {db_path}")
        print(f"GitHub Repo: {self.github_slug}")
        print(f"Lark App Token: {os.getenv('LARK_APP_TOKEN', 'Not configured')[:10]}...")
    
    def step1_sync_users(self):
        """Step 1: Sync users from GitHub/Lark to local DB (local DB is source of truth)."""
        print("\n" + "-" * 60)
        print("STEP 1: SYNC USERS TO LOCAL DB (Source of Truth)")
        print("-" * 60)
        
        team_members = [
            {
                "name": "Alice Chen",
                "email": "alice.chen@example.com",
                "github_username": "alicechen",
                "lark_open_id": "ou_alice001",
                "team": "MAS Engine",
                "role": MemberRole.MANAGER,
            },
            {
                "name": "Bob Wang",
                "email": "bob.wang@example.com",
                "github_username": "bobwang",
                "lark_open_id": "ou_bob002",
                "team": "MAS Engine",
                "role": MemberRole.DEVELOPER,
            },
            {
                "name": "Carol Li",
                "email": "carol.li@example.com",
                "github_username": "carolli",
                "lark_open_id": "ou_carol003",
                "team": "MAS Engine",
                "role": MemberRole.DEVELOPER,
            },
            {
                "name": "David Zhang",
                "email": "david.zhang@example.com",
                "github_username": "davidzhang",
                "lark_open_id": "ou_david004",
                "team": "Agent Optimization WTB",
                "role": MemberRole.MANAGER,
            },
            {
                "name": "Eva Liu",
                "email": "eva.liu@example.com",
                "github_username": "evaliu",
                "lark_open_id": "ou_eva005",
                "team": "Agent Optimization WTB",
                "role": MemberRole.DEVELOPER,
            },
            {
                "name": "Frank Zhao",
                "email": "frank.zhao@example.com",
                "github_username": "frankzhao",
                "lark_open_id": "ou_frank006",
                "team": "Agent Optimization WTB",
                "role": MemberRole.QA,
            },
        ]
        
        for m in team_members:
            existing = self.member_repo.get_by_email(m["email"])
            if existing:
                print(f"  [EXISTS] {m['name']} ({m['team']})")
                continue
            
            member = Member(
                name=m["name"],
                email=m["email"],
                github_username=m.get("github_username"),
                lark_open_id=m.get("lark_open_id"),
                team=m.get("team"),
                role=m.get("role", MemberRole.DEVELOPER),
            )
            self.member_repo.create(member)
            print(f"  [CREATED] {m['name']} ({m['team']}) - Role: {m['role'].value}")
        
        all_members = self.member_repo.list_all()
        print(f"\nTotal members in local DB: {len(all_members)}")
        
        mas_team = self.member_repo.list_all(team="MAS Engine")
        wtb_team = self.member_repo.list_all(team="Agent Optimization WTB")
        print(f"  - MAS Engine team: {len(mas_team)}")
        print(f"  - Agent Optimization WTB team: {len(wtb_team)}")
    
    def step2_create_tables(self):
        """Step 2: Register/create two Lark tables."""
        print("\n" + "-" * 60)
        print("STEP 2: CREATE/REGISTER LARK TABLES")
        print("-" * 60)
        
        app_token = os.getenv("LARK_APP_TOKEN")
        default_table_id = os.getenv("LARK_TASKS_TABLE_ID")
        
        if not app_token:
            print("  [SKIP] LARK_APP_TOKEN not configured")
            return
        
        tables = [
            {
                "name": "MAS Engine Tasks",
                "table_id": default_table_id or "tbl_mas_placeholder",
                "is_default": True,
            },
            {
                "name": "Agent Optimization WTB Tasks",
                "table_id": f"{default_table_id}_wtb" if default_table_id else "tbl_wtb_placeholder",
                "is_default": False,
            },
        ]
        
        for t in tables:
            existing = self.table_repo.get_by_name(t["name"])
            if existing:
                print(f"  [EXISTS] {t['name']}")
                continue
            
            result = self.lark_tools.register_table(
                table_name=t["name"],
                app_token=app_token,
                table_id=t["table_id"],
                is_default=t["is_default"],
            )
            print(f"  {result}")
        
        all_tables = self.table_repo.list_all()
        print(f"\nRegistered tables: {len(all_tables)}")
        for t in all_tables:
            default_marker = " [DEFAULT]" if t.is_default else ""
            print(f"  - {t.table_name}{default_marker}")
    
    def step3_create_tasks_with_issues(self):
        """Step 3: Create tasks with GitHub issues, dates, assignees, progress."""
        print("\n" + "-" * 60)
        print("STEP 3: CREATE TASKS WITH GITHUB ISSUES")
        print("-" * 60)
        
        now = datetime.now()
        
        tasks_to_create = [
            {
                "title": "[MAS Engine] Implement API Gateway",
                "body": "Design and implement the API gateway for MAS Engine services",
                "assignee": "alice.chen@example.com",
                "team": "MAS Engine",
                "due_date": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
                "progress": 30,
                "labels": ["feature", "backend", "mas-engine"],
            },
            {
                "title": "[MAS Engine] Database Schema Migration",
                "body": "Migrate database schema to support new features",
                "assignee": "bob.wang@example.com",
                "team": "MAS Engine",
                "due_date": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
                "progress": 70,
                "labels": ["database", "migration", "mas-engine"],
            },
            {
                "title": "[MAS Engine] Unit Test Coverage",
                "body": "Increase unit test coverage to 80%",
                "assignee": "carol.li@example.com",
                "team": "MAS Engine",
                "due_date": (now + timedelta(days=5)).strftime("%Y-%m-%d"),
                "progress": 45,
                "labels": ["testing", "mas-engine"],
            },
            {
                "title": "[WTB] Agent Performance Optimization",
                "body": "Optimize agent response time by 50%",
                "assignee": "david.zhang@example.com",
                "team": "Agent Optimization WTB",
                "due_date": (now + timedelta(days=10)).strftime("%Y-%m-%d"),
                "progress": 20,
                "labels": ["optimization", "performance", "wtb"],
            },
            {
                "title": "[WTB] Implement Caching Layer",
                "body": "Add Redis caching for frequently accessed data",
                "assignee": "eva.liu@example.com",
                "team": "Agent Optimization WTB",
                "due_date": (now + timedelta(days=4)).strftime("%Y-%m-%d"),
                "progress": 55,
                "labels": ["feature", "caching", "wtb"],
            },
            {
                "title": "[WTB] QA Test Plan",
                "body": "Create comprehensive QA test plan for agent optimization",
                "assignee": "frank.zhao@example.com",
                "team": "Agent Optimization WTB",
                "due_date": (now + timedelta(days=2)).strftime("%Y-%m-%d"),
                "progress": 90,
                "labels": ["qa", "testing", "wtb"],
            },
        ]
        
        for task_data in tasks_to_create:
            print(f"\n  Creating: {task_data['title']}")
            
            result = self.github_tools.create_issue(
                title=task_data["title"],
                body=f"{task_data['body']}\n\nDue: {task_data['due_date']}\nProgress: {task_data['progress']}%\nTeam: {task_data['team']}\nAssignee: {task_data['assignee']}",
                labels=task_data["labels"],
                send_to_lark=True,
            )
            print(f"    GitHub: {result}")
            
            if "Issue #" in result:
                import re
                match = re.search(r"Issue #(\d+)", result)
                if match:
                    issue_num = int(match.group(1))
                    self.created_issues.append(issue_num)
                    
                    if self.github_slug != "Not configured":
                        print(f"    URL: https://github.com/{self.github_slug}/issues/{issue_num}")
        
        print(f"\nCreated {len(self.created_issues)} GitHub issues")
    
    def step4_query_tasks(self):
        """Step 4: Query tasks - who does what, progress, team info."""
        print("\n" + "-" * 60)
        print("STEP 4: QUERY TASKS AND TEAM INFO")
        print("-" * 60)
        
        print("\n[Query 1] List all members:")
        members = self.member_repo.list_all()
        for m in members:
            print(f"  - {m.name} ({m.email}) - Team: {m.team}, Role: {m.role.value}")
        
        print("\n[Query 2] MAS Engine team members:")
        mas_team = self.member_repo.list_all(team="MAS Engine")
        for m in mas_team:
            print(f"  - {m.name} ({m.role.value})")
        
        print("\n[Query 3] WTB team members:")
        wtb_team = self.member_repo.list_all(team="Agent Optimization WTB")
        for m in wtb_team:
            print(f"  - {m.name} ({m.role.value})")
        
        print("\n[Query 4] All tasks:")
        tasks = self.task_repo.list_all()
        for t in tasks:
            assignee = "Unassigned"
            if t.assignee_member_id:
                member = self.member_repo.get_by_id(t.assignee_member_id)
                if member:
                    assignee = member.name
            
            print(f"  - {t.title[:50]}...")
            print(f"      Status: {t.status.value}, Progress: {t.progress}%, Assignee: {assignee}")
            if t.due_date:
                print(f"      Due: {t.due_date}")
        
        print("\n[Query 5] Tasks by progress (> 50%):")
        high_progress = self.task_repo.get_by_progress_range(51, 100)
        for t in high_progress:
            print(f"  - {t.title[:40]}... ({t.progress}%)")
        
        print("\n[Query 6] GitHub-Lark mappings:")
        mappings = self.mapping_repo.list_all()
        for m in mappings:
            if m.github_issue_number:
                gh_url = f"https://github.com/{self.github_slug}/issues/{m.github_issue_number}" if self.github_slug != "Not configured" else "N/A"
                lark_url = f"Lark Record: {m.lark_record_id[:12] if m.lark_record_id else 'Pending sync'}..."
                print(f"  Task {m.task_id[:8]}...")
                print(f"    GitHub: {gh_url}")
                print(f"    {lark_url}")
    
    def step5_summary(self):
        """Step 5: Print summary with URLs."""
        print("\n" + "=" * 60)
        print("DEMO SUMMARY")
        print("=" * 60)
        
        lark_app_token = os.getenv("LARK_APP_TOKEN", "")
        lark_table_id = os.getenv("LARK_TASKS_TABLE_ID", "")
        
        print(f"\nMembers synced: {len(self.member_repo.list_all())}")
        print(f"Tables registered: {len(self.table_repo.list_all())}")
        print(f"Tasks created: {len(self.task_repo.list_all())}")
        print(f"GitHub issues created: {len(self.created_issues)}")
        print(f"Mappings: {len(self.mapping_repo.list_all())}")
        
        print("\n--- IMPORTANT URLs ---")
        if self.github_slug != "Not configured":
            print(f"GitHub Repository: https://github.com/{self.github_slug}")
            if self.created_issues:
                print(f"Issues created: {', '.join(f'#{i}' for i in self.created_issues)}")
        
        if lark_app_token:
            print(f"Lark Bitable: https://your-domain.larksuite.com/base/{lark_app_token}")
            if lark_table_id:
                print(f"Tasks Table ID: {lark_table_id}")
        
        print("\n--- Web Interface ---")
        print("Start the server with: python run_server.py")
        print("Then visit: http://localhost:8000")
    
    def cleanup(self):
        """Cleanup created GitHub issues (optional)."""
        print("\n" + "-" * 60)
        print("CLEANUP")
        print("-" * 60)
        
        if not self.created_issues:
            print("No issues to cleanup")
            return
        
        print(f"Created {len(self.created_issues)} issues: {self.created_issues}")
        print("To close these issues, run:")
        for issue_num in self.created_issues:
            print(f"  python -c \"from demos.backend_demo import BackendDemo; d = BackendDemo(); d.github_tools.close_issue({issue_num})\"")
    
    def run(self):
        """Run the full demo."""
        try:
            self.step1_sync_users()
            self.step2_create_tables()
            self.step3_create_tasks_with_issues()
            self.step4_query_tasks()
            self.step5_summary()
            self.cleanup()
            
            print("\n" + "=" * 60)
            print("DEMO COMPLETED SUCCESSFULLY")
            print("=" * 60)
            
        except Exception as e:
            print(f"\n[ERROR] Demo failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        return True


def main():
    demo = BackendDemo()
    demo.run()


if __name__ == "__main__":
    main()
