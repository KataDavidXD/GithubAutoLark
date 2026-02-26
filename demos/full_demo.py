#!/usr/bin/env python3
"""
Full Demo: GithubAutoLark System
================================
1. Sync users from Lark and GitHub to local DB (DB is truth)
2. Create project tables: MAS Engine, Agent Optimization WTB
3. Create tasks with datetime, GitHub issues, assign people, track progress
4. Query tasks: who does what, organization, progress, weekly work
"""
from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.member import Member, MemberRole
from src.models.task import Task, TaskSource, TaskStatus
from src.models.lark_table_registry import LarkTableConfig
from src.services.github_service import GitHubService
from src.services.lark_service import LarkService
from src.services.lark_token_manager import LarkDirectClient, LarkTokenManager
from src.agent.graph import run_command


class FullDemo:
    """Comprehensive demo of GithubAutoLark system."""
    
    def __init__(self):
        self.db = Database(path=Path("data/full_demo.db"))
        self.db.init()
        self.member_repo = MemberRepository(self.db)
        self.task_repo = TaskRepository(self.db)
        self.mapping_repo = MappingRepository(self.db)
        self.table_repo = LarkTableRepository(self.db)
        
        self.github_svc = GitHubService()
        self.lark_svc = LarkService()
        self.lark_svc.use_direct_api = True
        self.lark_client = LarkDirectClient()
        
        self.app_token = os.getenv("LARK_APP_TOKEN")
        self.mas_table_id: Optional[str] = None
        self.wtb_table_id: Optional[str] = None
        
    def run(self):
        """Run the full demo."""
        print("=" * 70)
        print("FULL DEMO: GithubAutoLark System")
        print("=" * 70)
        
        with self.lark_svc:
            self.step1_sync_users()
            self.step2_create_project_tables()
            self.step3_create_tasks_and_issues()
            self.step4_query_tasks()
        
        print()
        print("=" * 70)
        print("DEMO COMPLETE!")
        print("=" * 70)
    
    # =========================================================================
    # Step 1: Sync Users from Lark and GitHub
    # =========================================================================
    
    def step1_sync_users(self):
        """Get users from Lark and GitHub, save to local DB."""
        print()
        print("-" * 70)
        print("STEP 1: Sync Users from Lark and GitHub")
        print("-" * 70)
        
        # Define team members (in real scenario, fetch from Lark/GitHub API)
        team_members = [
            {
                "name": "Alice Chen",
                "email": "alice.chen@example.com",
                "github_username": "alicechen",
                "role": MemberRole.MANAGER,
                "team": "MAS Engine",
                "lark_open_id": os.getenv("EMPLOYEE_OPEN_ID"),  # Use real ID if available
            },
            {
                "name": "Bob Wang",
                "email": "bob.wang@example.com",
                "github_username": "bobwang",
                "role": MemberRole.DEVELOPER,
                "team": "MAS Engine",
            },
            {
                "name": "Carol Li",
                "email": "carol.li@example.com",
                "github_username": "carolli",
                "role": MemberRole.DEVELOPER,
                "team": "Agent Optimization WTB",
            },
            {
                "name": "David Zhang",
                "email": "david.zhang@example.com",
                "github_username": "davidzhang",
                "role": MemberRole.DEVELOPER,
                "team": "Agent Optimization WTB",
            },
            {
                "name": "Eva Liu",
                "email": os.getenv("EMPLOYEE_EMAIL", "eva.liu@example.com"),
                "github_username": "evaliu",
                "role": MemberRole.MANAGER,
                "team": "Management",
                "lark_open_id": os.getenv("EMPLOYEE_OPEN_ID"),
            },
        ]
        
        print(f"   Syncing {len(team_members)} team members to local DB...")
        
        for m in team_members:
            # Check if member exists
            existing = self.member_repo.get_by_email(m["email"])
            if existing:
                print(f"   [EXISTS] {m['name']} ({m['email']})")
                continue
            
            # Try to resolve Lark ID if not provided
            lark_id = m.get("lark_open_id")
            if not lark_id and "@example.com" not in m["email"]:
                try:
                    lark_id = self.lark_svc.get_user_id_by_email(m["email"])
                except:
                    pass
            
            member = Member(
                name=m["name"],
                email=m["email"],
                github_username=m.get("github_username"),
                lark_open_id=lark_id,
                role=m.get("role", MemberRole.DEVELOPER),
                team=m.get("team"),
            )
            self.member_repo.create(member)
            print(f"   [CREATED] {m['name']} ({m['email']}) - Team: {m.get('team')}")
        
        # List all members
        all_members = self.member_repo.list_all()
        print()
        print(f"   Total members in DB: {len(all_members)}")
        for m in all_members:
            lark_status = "Lark ID" if m.lark_open_id else "No Lark"
            print(f"     - {m.name} [{m.role}] Team: {m.team or 'N/A'} ({lark_status})")
    
    # =========================================================================
    # Step 2: Create Project Tables
    # =========================================================================
    
    def step2_create_project_tables(self):
        """Create two Lark tables for the projects."""
        print()
        print("-" * 70)
        print("STEP 2: Create Project Tables in Lark")
        print("-" * 70)
        
        # Table field definition
        table_fields = [
            {"field_name": "Task Name", "type": 1},  # Text
            {"field_name": "Status", "type": 3, "property": {"options": [
                {"name": "To Do"},
                {"name": "In Progress"},
                {"name": "Done"},
                {"name": "Blocked"}
            ]}},
            {"field_name": "Assignee", "type": 11},  # Person
            {"field_name": "Due Date", "type": 5},  # Date
            {"field_name": "Priority", "type": 3, "property": {"options": [
                {"name": "High"},
                {"name": "Medium"},
                {"name": "Low"}
            ]}},
            {"field_name": "GitHub Issue", "type": 15},  # URL
            {"field_name": "Description", "type": 1},  # Text
            {"field_name": "Progress", "type": 2},  # Number (percentage)
        ]
        
        projects = [
            ("MAS Engine", "mas_engine"),
            ("Agent Optimization WTB", "agent_wtb"),
        ]
        
        # First, get all existing tables from Lark
        print("   Fetching existing tables from Lark...")
        existing_lark_tables = {}
        try:
            lark_tables = self.lark_client.list_tables(self.app_token)
            for t in lark_tables:
                existing_lark_tables[t.get("name")] = t.get("table_id")
            print(f"   Found {len(lark_tables)} tables in Lark")
        except Exception as e:
            print(f"   [ERROR] Could not list Lark tables: {e}")
        
        for table_name, table_key in projects:
            print(f"   Setting up table: {table_name}...")
            
            # Check if already registered in local DB
            existing = self.table_repo.get_by_name(table_name)
            if existing:
                print(f"   [EXISTS] Table '{table_name}' already registered locally")
                if table_key == "mas_engine":
                    self.mas_table_id = existing.table_id
                else:
                    self.wtb_table_id = existing.table_id
                continue
            
            # Check if exists in Lark but not registered locally
            table_id = existing_lark_tables.get(table_name)
            
            if table_id:
                # Register existing Lark table locally
                cfg = LarkTableConfig(
                    app_token=self.app_token,
                    table_id=table_id,
                    table_name=table_name,
                    is_default=(table_key == "mas_engine"),
                    field_mapping={
                        "title_field": "Task Name",
                        "status_field": "Status",
                        "assignee_field": "Assignee",
                        "body_field": "Description",
                    }
                )
                self.table_repo.register(cfg)
                print(f"   [REGISTERED] Existing Lark table '{table_name}' (ID: {table_id})")
                
                if table_key == "mas_engine":
                    self.mas_table_id = table_id
                else:
                    self.wtb_table_id = table_id
                continue
            
            # Create new table in Lark
            try:
                resp = self.lark_client._request(
                    "POST",
                    f"/bitable/v1/apps/{self.app_token}/tables",
                    json={
                        "table": {
                            "name": table_name,
                            "default_view_name": "Task Board",
                            "fields": table_fields,
                        }
                    }
                )
                table_id = resp.get("data", {}).get("table_id")
                
                if table_id:
                    # Register in local DB
                    cfg = LarkTableConfig(
                        app_token=self.app_token,
                        table_id=table_id,
                        table_name=table_name,
                        is_default=(table_key == "mas_engine"),
                        field_mapping={
                            "title_field": "Task Name",
                            "status_field": "Status",
                            "assignee_field": "Assignee",
                            "body_field": "Description",
                        }
                    )
                    self.table_repo.register(cfg)
                    print(f"   [CREATED] New table '{table_name}' (ID: {table_id})")
                    
                    if table_key == "mas_engine":
                        self.mas_table_id = table_id
                    else:
                        self.wtb_table_id = table_id
                else:
                    print(f"   [ERROR] Failed to create table: {resp}")
                    
            except Exception as e:
                print(f"   [ERROR] {e}")
        
        # List all registered tables
        tables = self.table_repo.list_all()
        print()
        print(f"   Registered tables: {len(tables)}")
        for t in tables:
            default = " [DEFAULT]" if t.is_default else ""
            print(f"     - {t.table_name} ({t.table_id}){default}")
    
    # =========================================================================
    # Step 3: Create Tasks and GitHub Issues
    # =========================================================================
    
    def step3_create_tasks_and_issues(self):
        """Create tasks with datetime, GitHub issues, assignments."""
        print()
        print("-" * 70)
        print("STEP 3: Create Tasks and GitHub Issues")
        print("-" * 70)
        
        # Get team members
        members = {m.name: m for m in self.member_repo.list_all()}
        
        # Define tasks for each project
        today = datetime.now()
        
        mas_tasks = [
            {
                "title": "Implement multi-agent coordination protocol",
                "assignee": "Alice Chen",
                "status": "In Progress",
                "priority": "High",
                "due_date": today + timedelta(days=7),
                "progress": 40,
                "description": "Design and implement the coordination protocol for multiple agents",
            },
            {
                "title": "Build agent communication layer",
                "assignee": "Bob Wang",
                "status": "To Do",
                "priority": "High",
                "due_date": today + timedelta(days=14),
                "progress": 0,
                "description": "Implement message passing between agents",
            },
            {
                "title": "Create agent state management",
                "assignee": "Alice Chen",
                "status": "Done",
                "priority": "Medium",
                "due_date": today - timedelta(days=3),
                "progress": 100,
                "description": "State persistence and recovery for agents",
            },
        ]
        
        wtb_tasks = [
            {
                "title": "Optimize LLM prompt templates",
                "assignee": "Carol Li",
                "status": "In Progress",
                "priority": "High",
                "due_date": today + timedelta(days=5),
                "progress": 60,
                "description": "Improve prompt efficiency and reduce token usage",
            },
            {
                "title": "Implement caching for agent responses",
                "assignee": "David Zhang",
                "status": "To Do",
                "priority": "Medium",
                "due_date": today + timedelta(days=10),
                "progress": 0,
                "description": "Add Redis caching layer for repeated queries",
            },
            {
                "title": "Benchmark agent performance",
                "assignee": "Carol Li",
                "status": "Done",
                "priority": "Low",
                "due_date": today - timedelta(days=5),
                "progress": 100,
                "description": "Run performance tests and document results",
            },
        ]
        
        # Create tasks
        task_configs = [
            ("MAS Engine", self.mas_table_id, mas_tasks),
            ("Agent Optimization WTB", self.wtb_table_id, wtb_tasks),
        ]
        
        for project_name, table_id, tasks in task_configs:
            if not table_id:
                print(f"   [SKIP] No table ID for {project_name}")
                continue
                
            print(f"\n   Creating tasks for {project_name}...")
            
            for task_data in tasks:
                assignee = members.get(task_data["assignee"])
                assignee_id = assignee.lark_open_id if assignee else None
                
                # Create GitHub issue first
                github_issue = None
                try:
                    label = "mas-engine" if "MAS" in project_name else "agent-wtb"
                    issue_result = self.github_svc.create_issue(
                        title=f"[{project_name}] {task_data['title']}",
                        body=task_data["description"],
                        labels=[label, task_data["priority"].lower()],
                    )
                    github_issue = issue_result.get("number")
                    github_url = issue_result.get("html_url", "")
                    print(f"     [GitHub] Created issue #{github_issue}")
                except Exception as e:
                    print(f"     [GitHub Error] {e}")
                    github_url = ""
                
                # Create Lark record
                try:
                    fields = {
                        "Task Name": task_data["title"],
                        "Status": task_data["status"],
                        "Priority": task_data["priority"],
                        "Description": task_data["description"],
                        "Progress": task_data["progress"],
                    }
                    
                    if assignee_id:
                        fields["Assignee"] = [{"id": assignee_id}]
                    
                    if task_data.get("due_date"):
                        fields["Due Date"] = int(task_data["due_date"].timestamp() * 1000)
                    
                    if github_url:
                        fields["GitHub Issue"] = {"link": github_url, "text": f"Issue #{github_issue}"}
                    
                    record = self.lark_client.create_record(self.app_token, table_id, fields)
                    record_id = record.get("record_id", "unknown")
                    print(f"     [Lark] Created record: {task_data['title'][:30]}...")
                    
                    # Save to local DB
                    status_map = {
                        "To Do": TaskStatus.TODO,
                        "In Progress": TaskStatus.IN_PROGRESS,
                        "Done": TaskStatus.DONE,
                    }
                    task = Task(
                        title=task_data["title"],
                        body=task_data["description"],
                        source=TaskSource.COMMAND,
                        assignee_member_id=assignee.member_id if assignee else None,
                        status=status_map.get(task_data["status"], TaskStatus.TODO),
                        target_table=project_name,
                    )
                    self.task_repo.create(task)
                    
                    # Create mapping
                    self.mapping_repo.upsert_for_task(
                        task.task_id,
                        github_issue_number=github_issue,
                        github_repo=os.getenv("REPO"),
                        lark_record_id=record_id,
                        lark_app_token=self.app_token,
                        lark_table_id=table_id,
                    )
                    
                except Exception as e:
                    print(f"     [Lark Error] {e}")
    
    # =========================================================================
    # Step 4: Query Tasks
    # =========================================================================
    
    def step4_query_tasks(self):
        """Query tasks using natural language commands."""
        print()
        print("-" * 70)
        print("STEP 4: Query Tasks (Natural Language)")
        print("-" * 70)
        
        queries = [
            # Who does what
            ("Show Alice Chen's work", "List tasks assigned to Alice"),
            
            # Organization queries
            ("List members", "List all team members"),
            
            # Task queries
            ("List issues", "Show GitHub issues"),
            
            # Sync status
            ("Sync status", "Show pending sync items"),
        ]
        
        for question, description in queries:
            print(f"\n   Q: {question}")
            print(f"   ({description})")
            
            result = run_command(
                question,
                db=self.db,
                github_service=self.github_svc,
                lark_service=self.lark_svc,
            )
            
            # Format output
            lines = result.split("\n")
            for line in lines[:10]:  # Limit output
                print(f"   > {line}")
            if len(lines) > 10:
                print(f"   > ... ({len(lines) - 10} more lines)")
        
        # Additional: Show local DB summary
        print()
        print("   --- Local Database Summary ---")
        
        all_tasks = self.task_repo.list_all()
        tasks_by_status = {}
        for task in all_tasks:
            status = task.status.value if hasattr(task.status, 'value') else str(task.status)
            tasks_by_status.setdefault(status, []).append(task)
        
        print(f"   Total tasks: {len(all_tasks)}")
        for status, tasks in tasks_by_status.items():
            print(f"     - {status}: {len(tasks)}")
        
        # Show mappings
        print()
        print("   --- GitHub-Lark Mappings ---")
        for task in all_tasks[:5]:
            mappings = self.mapping_repo.get_by_task(task.task_id)
            if mappings:
                mapping = mappings[0] if isinstance(mappings, list) else mappings
                gh = f"#{mapping.github_issue_number}" if mapping.github_issue_number else "N/A"
                lark = mapping.lark_record_id[:12] if mapping.lark_record_id else "N/A"
                print(f"     - {task.title[:40]}... -> GitHub: {gh}, Lark: {lark}")


if __name__ == "__main__":
    demo = FullDemo()
    demo.run()
