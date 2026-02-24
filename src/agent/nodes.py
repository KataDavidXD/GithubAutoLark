"""
Agent Nodes - Individual processing steps for the LangGraph agent.

Each node is a function that takes AgentState and returns updates to the state.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from src.agent.state import AgentState, MemberInfo, TodoItem, ProjectConfig
from src.config import get_repo_root, get_lark_bitable_config
from src.db import get_db
from src.github_service import GitHubService
from src.lark_service import LarkService
from src.sync_engine import lark_status_to_github_state, github_state_to_lark_status


# ---------------------------------------------------------------------------
# Node: Load Input Files (Markdown)
# ---------------------------------------------------------------------------

def load_input_files(state: AgentState) -> dict[str, Any]:
    """
    Load project docs, todos, and team info from markdown files.
    
    Expected files in input/:
    - *project*.md or *structure*.md -> project description
    - *todo*.md or *task*.md -> fuzzy task list
    - *team*.md or *member*.md -> team info (optional)
    - config.yaml -> optional config overrides
    """
    messages = list(state.get("messages", []))
    messages.append("Loading input markdown files...")
    
    input_path = Path(state.get("input_path", get_repo_root() / "input"))
    
    # Find markdown files by pattern
    project_doc = ""
    todos_doc = ""
    team_doc = ""
    
    for md_file in input_path.glob("*.md"):
        name_lower = md_file.stem.lower()
        content = md_file.read_text(encoding="utf-8")
        
        if "project" in name_lower or "structure" in name_lower:
            project_doc = content
            messages.append(f"Loaded project doc: {md_file.name}")
        elif "todo" in name_lower or "task" in name_lower:
            todos_doc = content
            messages.append(f"Loaded todos doc: {md_file.name}")
        elif "team" in name_lower or "member" in name_lower:
            team_doc = content
            messages.append(f"Loaded team doc: {md_file.name}")
    
    # Load optional config.yaml
    config_file = input_path / "config.yaml"
    project_config: ProjectConfig = {}
    
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            project_config = yaml.safe_load(f) or {}
        messages.append("Loaded config.yaml")
    
    return {
        "project_doc": project_doc,
        "todos_doc": todos_doc,
        "team_doc": team_doc,
        "project": project_config,
        "messages": messages,
        "current_node": "load_input_files",
    }


# ---------------------------------------------------------------------------
# Node: Parse with LLM
# ---------------------------------------------------------------------------

def parse_with_llm(state: AgentState) -> dict[str, Any]:
    """
    Use LLM to parse fuzzy markdown documents into structured todos.
    
    Converts natural language project docs and todo notes into:
    - Structured project info
    - Member list with emails
    - Todo list with titles, priorities, assignees
    """
    messages = list(state.get("messages", []))
    messages.append("Parsing documents with LLM...")
    
    project_doc = state.get("project_doc", "")
    todos_doc = state.get("todos_doc", "")
    team_doc = state.get("team_doc", "")
    
    if not todos_doc and not project_doc:
        messages.append("Warning: No input documents found")
        return {
            "members": [],
            "todos": [],
            "messages": messages,
            "current_node": "parse_with_llm",
        }
    
    try:
        from src.llm_processor import LLMProcessor
        
        processor = LLMProcessor()
        parsed = processor.parse_documents(project_doc, todos_doc, team_doc)
        
        # Extract members
        members: list[MemberInfo] = []
        for m in parsed.get("members", []):
            member: MemberInfo = {
                "email": m.get("email", ""),
                "github_username": m.get("github_username", ""),
                "lark_open_id": "",  # Will be resolved later
                "name": m.get("name", ""),
                "role": m.get("role", ""),
            }
            if member["email"]:
                members.append(member)
        
        # Extract todos
        todos: list[TodoItem] = []
        for t in parsed.get("todos", []):
            todo: TodoItem = {
                "title": t.get("title", "Untitled"),
                "body": t.get("body", ""),
                "assignee": t.get("assignee_email", ""),
                "priority": t.get("priority", "medium"),
                "status": t.get("status", "To Do"),
                "labels": t.get("labels", []),
            }
            todos.append(todo)
        
        messages.append(f"LLM extracted {len(members)} member(s) and {len(todos)} todo(s)")
        
        # Update project info if extracted
        project_info = parsed.get("project", {})
        if project_info:
            messages.append(f"Project: {project_info.get('name', 'Unknown')}")
        
        return {
            "members": members,
            "todos": todos,
            "messages": messages,
            "current_node": "parse_with_llm",
        }
        
    except Exception as e:
        messages.append(f"LLM parsing error: {e}")
        messages.append("Falling back to empty extraction")
        return {
            "members": [],
            "todos": [],
            "error": str(e),
            "messages": messages,
            "current_node": "parse_with_llm",
        }


# ---------------------------------------------------------------------------
# Node: Load Existing Data
# ---------------------------------------------------------------------------

def load_existing_data(state: AgentState) -> dict[str, Any]:
    """
    Load existing issues from GitHub, records from Lark, and tasks from SQLite.
    
    This determines whether we're starting fresh or continuing with existing data.
    """
    messages = list(state.get("messages", []))
    messages.append("Loading existing data from GitHub, Lark, and SQLite...")
    
    project = state.get("project", {})
    mode = "new"  # Default
    
    existing_github_issues: list[dict] = []
    existing_lark_records: list[dict] = []
    existing_tasks: list[dict] = []
    
    # Load from GitHub
    try:
        svc = GitHubService()
        existing_github_issues = svc.list_issues(state="all", per_page=100)
        messages.append(f"Found {len(existing_github_issues)} GitHub issue(s)")
        
        if existing_github_issues:
            mode = "existing"
    except Exception as e:
        messages.append(f"GitHub load warning: {e}")
    
    # Load from Lark
    lark_config = get_lark_bitable_config()
    app_token = project.get("lark", {}).get("app_token") or lark_config.app_token
    table_id = project.get("lark", {}).get("table_id") or lark_config.tasks_table_id
    
    if app_token and table_id:
        try:
            with LarkService() as svc:
                existing_lark_records = svc.search_records(
                    app_token=app_token,
                    table_id=table_id,
                )
            messages.append(f"Found {len(existing_lark_records)} Lark record(s)")
            
            if existing_lark_records:
                mode = "existing"
        except Exception as e:
            messages.append(f"Lark load warning: {e}")
    
    # Load from SQLite
    try:
        db = get_db()
        db.init()
        existing_tasks = db.list_tasks()
        messages.append(f"Found {len(existing_tasks)} local task(s)")
        
        if existing_tasks:
            mode = "existing"
    except Exception as e:
        messages.append(f"DB load warning: {e}")
    
    messages.append(f"Mode determined: {mode}")
    
    return {
        "existing_github_issues": existing_github_issues,
        "existing_lark_records": existing_lark_records,
        "existing_tasks": existing_tasks,
        "mode": mode,
        "messages": messages,
        "current_node": "load_existing_data",
    }


# ---------------------------------------------------------------------------
# Node: Standardize Members
# ---------------------------------------------------------------------------

def standardize_members(state: AgentState) -> dict[str, Any]:
    """
    Standardize member identities across GitHub and Lark.
    
    - Resolve Lark open_id from email if not provided
    - Verify GitHub username exists
    - Save standardized mapping to SQLite
    """
    messages = list(state.get("messages", []))
    messages.append("Standardizing member identities...")
    
    members = state.get("members", [])
    standardized: list[MemberInfo] = []
    
    if not members:
        messages.append("No members to standardize")
        return {
            "members_standardized": [],
            "messages": messages,
            "current_node": "standardize_members",
        }
    
    db = get_db()
    db.init()
    
    # Process each member
    with LarkService() as lark_svc:
        for member in members:
            email = member.get("email", "")
            if not email:
                continue
            
            # Check if we already have this member in DB
            existing = db.get_employee(email)
            
            # Get or resolve Lark open_id
            lark_open_id = member.get("lark_open_id", "")
            if not lark_open_id and existing:
                lark_open_id = existing.get("lark_open_id", "")
            
            if not lark_open_id:
                # Resolve from Lark
                try:
                    lark_open_id = lark_svc.get_user_id_by_email(email) or ""
                    messages.append(f"Resolved Lark ID for {email}")
                except Exception as e:
                    messages.append(f"Failed to resolve Lark ID for {email}: {e}")
            
            # Build standardized member
            std_member: MemberInfo = {
                "email": email,
                "github_username": member.get("github_username", ""),
                "lark_open_id": lark_open_id,
                "name": member.get("name", ""),
                "role": member.get("role", ""),
            }
            standardized.append(std_member)
            
            # Save to DB
            db.upsert_employee(email, lark_open_id if lark_open_id else None)
    
    messages.append(f"Standardized {len(standardized)} member(s)")
    
    return {
        "members_standardized": standardized,
        "messages": messages,
        "current_node": "standardize_members",
    }


# ---------------------------------------------------------------------------
# Node: Align Todos
# ---------------------------------------------------------------------------

def align_todos(state: AgentState) -> dict[str, Any]:
    """
    Align todos with existing data.
    
    - Match new todos with existing GitHub issues by title prefix
    - Match new todos with existing Lark records by title
    - Create task records in SQLite for tracking
    """
    messages = list(state.get("messages", []))
    messages.append("Aligning todos with existing data...")
    
    todos = state.get("todos", [])
    existing_issues = state.get("existing_github_issues", [])
    existing_records = state.get("existing_lark_records", [])
    members_std = state.get("members_standardized", [])
    project = state.get("project", {})
    
    if not todos:
        messages.append("No todos to align")
        return {
            "todos_aligned": [],
            "messages": messages,
            "current_node": "align_todos",
        }
    
    # Build email -> member lookup
    member_by_email = {m["email"]: m for m in members_std if m.get("email")}
    
    db = get_db()
    db.init()
    
    lark_fields = project.get("lark", {}).get("fields", {})
    title_field = lark_fields.get("title", "Task Name")
    
    aligned: list[TodoItem] = []
    
    for todo in todos:
        title = todo.get("title", "")
        if not title:
            continue
        
        # Try to find matching GitHub issue
        github_issue_number = None
        for issue in existing_issues:
            issue_title = issue.get("title", "")
            # Match by title (case-insensitive, partial match)
            if title.lower() in issue_title.lower() or issue_title.lower().split("]")[-1].strip().lower() == title.lower():
                github_issue_number = issue["number"]
                messages.append(f"Matched '{title[:30]}...' to GitHub #{github_issue_number}")
                break
        
        # Try to find matching Lark record
        lark_record_id = None
        for record in existing_records:
            fields = record.get("fields", {})
            record_title = fields.get(title_field)
            if isinstance(record_title, list):
                record_title = record_title[0].get("text", "") if record_title else ""
            if record_title and title.lower() in str(record_title).lower():
                lark_record_id = record["record_id"]
                messages.append(f"Matched '{title[:30]}...' to Lark {lark_record_id[:12]}...")
                break
        
        # Resolve assignee
        assignee_email = todo.get("assignee", "")
        assignee_open_id = ""
        if assignee_email and assignee_email in member_by_email:
            assignee_open_id = member_by_email[assignee_email].get("lark_open_id", "")
        
        # Create or update task in DB
        task_id = None
        if github_issue_number:
            mapping = db.get_mapping_by_github_issue(github_issue_number)
            if mapping:
                task_id = mapping["task_id"]
        
        if not task_id and lark_record_id:
            mapping = db.get_mapping_by_lark_record(lark_record_id)
            if mapping:
                task_id = mapping["task_id"]
        
        if not task_id:
            # Create new task
            task_id = db.create_task(
                title=title,
                body=todo.get("body", ""),
                status=todo.get("status", "ToDo"),
                source="input",
                assignee_email=assignee_email,
                assignee_open_id=assignee_open_id,
            )
            messages.append(f"Created task: {task_id[:8]}...")
        
        # Update mapping
        if github_issue_number or lark_record_id:
            db.upsert_mapping(
                task_id,
                github_issue_number=github_issue_number,
                lark_record_id=lark_record_id,
            )
        
        aligned_todo: TodoItem = {
            **todo,
            "task_id": task_id,
            "github_issue_number": github_issue_number or 0,
            "lark_record_id": lark_record_id or "",
        }
        aligned.append(aligned_todo)
    
    messages.append(f"Aligned {len(aligned)} todo(s)")
    
    return {
        "todos_aligned": aligned,
        "messages": messages,
        "current_node": "align_todos",
    }


# ---------------------------------------------------------------------------
# Node: Sync GitHub to Lark
# ---------------------------------------------------------------------------

def sync_github_to_lark(state: AgentState) -> dict[str, Any]:
    """
    Sync todos from GitHub to Lark.
    
    - Create Lark records for todos that only have GitHub issues
    - Update Lark records with GitHub status changes
    """
    messages = list(state.get("messages", []))
    messages.append("Syncing GitHub -> Lark...")
    
    todos_aligned = state.get("todos_aligned", [])
    project = state.get("project", {})
    synced: list[dict] = list(state.get("synced_to_lark", []))
    errors: list[str] = list(state.get("sync_errors", []))
    
    db = get_db()
    lark_config = get_lark_bitable_config()
    app_token = project.get("lark", {}).get("app_token") or lark_config.app_token
    table_id = project.get("lark", {}).get("table_id") or lark_config.tasks_table_id
    fields_config = project.get("lark", {}).get("fields", {})
    
    if not app_token or not table_id:
        messages.append("Skipping Lark sync: no app_token/table_id configured")
        return {
            "synced_to_lark": synced,
            "sync_errors": errors,
            "messages": messages,
            "current_node": "sync_github_to_lark",
        }
    
    with LarkService() as lark_svc:
        for todo in todos_aligned:
            task_id = todo.get("task_id")
            if not task_id:
                continue
            
            # Check if needs Lark record
            mapping = db.get_mapping(task_id)
            if mapping and mapping.get("lark_record_id"):
                # Update existing record
                try:
                    fields = {
                        fields_config.get("title", "Task Name"): todo.get("title"),
                        fields_config.get("status", "Status"): todo.get("status", "To Do"),
                    }
                    lark_svc.update_record(
                        mapping["lark_record_id"],
                        fields,
                        app_token=app_token,
                        table_id=table_id,
                    )
                    synced.append({"task_id": task_id, "action": "updated", "lark_record_id": mapping["lark_record_id"]})
                    messages.append(f"Updated Lark record for task {task_id[:8]}")
                except Exception as e:
                    errors.append(f"Failed to update Lark record: {e}")
            else:
                # Create new record
                try:
                    fields = {
                        fields_config.get("title", "Task Name"): todo.get("title"),
                        fields_config.get("status", "Status"): todo.get("status", "To Do"),
                    }
                    
                    # Add assignee if available
                    task = db.get_task(task_id)
                    if task and task.get("assignee_open_id"):
                        fields[fields_config.get("assignee", "Assignee")] = [{"id": task["assignee_open_id"]}]
                    
                    # Add GitHub issue number if available
                    if todo.get("github_issue_number"):
                        fields[fields_config.get("github_issue", "GitHub Issue")] = todo["github_issue_number"]
                    
                    result = lark_svc.create_record(fields, app_token=app_token, table_id=table_id)
                    record_id = result.get("record", {}).get("record_id")
                    
                    if record_id:
                        db.upsert_mapping(task_id, lark_record_id=record_id)
                        synced.append({"task_id": task_id, "action": "created", "lark_record_id": record_id})
                        messages.append(f"Created Lark record for task {task_id[:8]}")
                except Exception as e:
                    errors.append(f"Failed to create Lark record: {e}")
    
    messages.append(f"Synced {len(synced)} record(s) to Lark")
    
    return {
        "synced_to_lark": synced,
        "sync_errors": errors,
        "messages": messages,
        "current_node": "sync_github_to_lark",
    }


# ---------------------------------------------------------------------------
# Node: Sync Lark to GitHub
# ---------------------------------------------------------------------------

def sync_lark_to_github(state: AgentState) -> dict[str, Any]:
    """
    Sync todos from Lark to GitHub.
    
    - Create GitHub issues for todos that only have Lark records
    - Update GitHub issues with Lark status changes
    """
    messages = list(state.get("messages", []))
    messages.append("Syncing Lark -> GitHub...")
    
    todos_aligned = state.get("todos_aligned", [])
    project = state.get("project", {})
    synced: list[dict] = list(state.get("synced_to_github", []))
    errors: list[str] = list(state.get("sync_errors", []))
    
    db = get_db()
    github_svc = GitHubService()
    
    default_labels = project.get("github", {}).get("default_labels", ["auto"])
    
    for todo in todos_aligned:
        task_id = todo.get("task_id")
        if not task_id:
            continue
        
        # Check if needs GitHub issue
        mapping = db.get_mapping(task_id)
        if mapping and mapping.get("github_issue_number"):
            # Update existing issue
            try:
                state_tuple = lark_status_to_github_state(todo.get("status", "To Do"))
                github_state, state_reason = state_tuple
                
                github_svc.update_issue(
                    mapping["github_issue_number"],
                    title=f"[AUTO][{task_id[:8]}] {todo.get('title')}",
                    body=todo.get("body", ""),
                    state=github_state,
                    state_reason=state_reason,
                )
                synced.append({"task_id": task_id, "action": "updated", "github_issue_number": mapping["github_issue_number"]})
                messages.append(f"Updated GitHub issue #{mapping['github_issue_number']}")
            except Exception as e:
                errors.append(f"Failed to update GitHub issue: {e}")
        else:
            # Create new issue
            try:
                labels = list(set(default_labels + todo.get("labels", [])))
                issue = github_svc.create_issue(
                    title=f"[AUTO][{task_id[:8]}] {todo.get('title')}",
                    body=todo.get("body", "") or f"Task ID: {task_id}\nPriority: {todo.get('priority', 'medium')}",
                    labels=labels,
                )
                
                issue_number = issue["number"]
                db.upsert_mapping(task_id, github_issue_number=issue_number)
                synced.append({"task_id": task_id, "action": "created", "github_issue_number": issue_number})
                messages.append(f"Created GitHub issue #{issue_number}")
            except Exception as e:
                errors.append(f"Failed to create GitHub issue: {e}")
    
    messages.append(f"Synced {len(synced)} issue(s) to GitHub")
    
    return {
        "synced_to_github": synced,
        "sync_errors": errors,
        "messages": messages,
        "current_node": "sync_lark_to_github",
    }


# ---------------------------------------------------------------------------
# Node: Finalize
# ---------------------------------------------------------------------------

def finalize(state: AgentState) -> dict[str, Any]:
    """
    Final node: summarize results and clean up.
    """
    messages = list(state.get("messages", []))
    messages.append("=" * 40)
    messages.append("SYNC COMPLETE")
    messages.append("=" * 40)
    
    # Summary
    synced_github = state.get("synced_to_github", [])
    synced_lark = state.get("synced_to_lark", [])
    errors = state.get("sync_errors", [])
    
    messages.append(f"GitHub issues synced: {len(synced_github)}")
    messages.append(f"Lark records synced: {len(synced_lark)}")
    messages.append(f"Errors: {len(errors)}")
    
    if errors:
        messages.append("Errors encountered:")
        for err in errors:
            messages.append(f"  - {err}")
    
    return {
        "messages": messages,
        "current_node": "finalize",
    }
