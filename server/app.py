"""FastAPI web server for GithubAutoLark."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Optional
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.services.github_service import GitHubService
from src.services.lark_service import LarkService
from src.agent.enhanced_graph import chat
from src.agent.llm_supervisor import get_llm_status


# Global service instances
_db: Optional[Database] = None
_github_svc: Optional[GitHubService] = None
_lark_svc: Optional[LarkService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    global _db, _github_svc, _lark_svc
    
    db_path = Path("data/chat.db")
    db_path.parent.mkdir(exist_ok=True)
    
    _db = Database(path=db_path)
    _db.init()
    
    _github_svc = GitHubService()
    _lark_svc = LarkService()
    _lark_svc.use_direct_api = True
    
    print(f"Server started - DB: {db_path}")
    yield
    
    print("Server shutting down")


app = FastAPI(
    title="GithubAutoLark API",
    description="Sync GitHub issues and Lark tasks with natural language",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Request/Response Models
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    timestamp: str


class MemberCreate(BaseModel):
    name: str
    email: str
    github_username: Optional[str] = None
    lark_open_id: Optional[str] = None
    team: Optional[str] = None
    role: str = "developer"


class TaskCreate(BaseModel):
    title: str
    body: Optional[str] = ""
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    progress: int = 0
    labels: Optional[list[str]] = None
    create_github_issue: bool = False
    create_lark_record: bool = False
    target_table: Optional[str] = None


class IssueCreate(BaseModel):
    title: str
    body: Optional[str] = ""
    assignee: Optional[str] = None
    labels: Optional[list[str]] = None
    sync_to_lark: bool = False


# API Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse("<h1>GithubAutoLark Server</h1><p>Visit /docs for API documentation</p>")


@app.get("/api/status")
async def get_status():
    """Get system status."""
    llm_status = get_llm_status()
    
    github_owner = os.getenv("OWNER", "")
    github_repo = os.getenv("REPO", "")
    github_slug = f"{github_owner}/{github_repo}" if github_owner and github_repo else ""
    lark_app_token = os.getenv("LARK_APP_TOKEN", "")
    lark_table_id = os.getenv("LARK_TASKS_TABLE_ID", "")
    
    links = {
        "github_repo": f"https://github.com/{github_slug}" if github_slug else None,
        "github_repo_name": github_slug,
        "lark_bitable": f"https://your-domain.larksuite.com/base/{lark_app_token}?table={lark_table_id}" if lark_app_token else None,
        "lark_table_name": "Tasks Bitable",
    }
    
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "llm": llm_status,
        "links": links,
        "services": {
            "github": _github_svc is not None,
            "lark": _lark_svc is not None,
            "database": _db is not None,
        }
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Process a natural language message."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        response = chat(
            message=request.message,
            db=_db,
            github_service=_github_svc,
            lark_service=_lark_svc,
        )
        return ChatResponse(
            response=response,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/members")
async def list_members(team: Optional[str] = None):
    """List all members, optionally filtered by team."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    repo = MemberRepository(_db)
    if team:
        members = repo.find_by_team(team)
    else:
        members = repo.list_all()
    
    return {
        "count": len(members),
        "members": [
            {
                "member_id": m.member_id,
                "name": m.name,
                "email": m.email,
                "github_username": m.github_username,
                "lark_open_id": m.lark_open_id,
                "team": m.team,
                "role": m.role.value if hasattr(m.role, 'value') else str(m.role),
            }
            for m in members
        ]
    }


@app.post("/api/members")
async def create_member(member: MemberCreate):
    """Create a new member."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    from src.models.member import Member, MemberRole
    
    role_map = {
        "developer": MemberRole.DEVELOPER,
        "manager": MemberRole.MANAGER,
        "lead": MemberRole.LEAD,
        "qa": MemberRole.QA,
    }
    
    repo = MemberRepository(_db)
    new_member = Member(
        name=member.name,
        email=member.email,
        github_username=member.github_username,
        lark_open_id=member.lark_open_id,
        team=member.team,
        role=role_map.get(member.role.lower(), MemberRole.DEVELOPER),
    )
    repo.create(new_member)
    
    return {"status": "created", "member_id": new_member.member_id}


@app.get("/api/tasks")
async def list_tasks(assignee: Optional[str] = None, status: Optional[str] = None):
    """List all tasks with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    repo = TaskRepository(_db)
    tasks = repo.list_all()
    
    result = []
    for t in tasks:
        if assignee and t.assignee_member_id != assignee:
            continue
        if status and t.status.value != status:
            continue
        
        result.append({
            "task_id": t.task_id,
            "title": t.title,
            "body": t.body[:200] if t.body else "",
            "status": t.status.value if hasattr(t.status, 'value') else str(t.status),
            "source": t.source.value if hasattr(t.source, 'value') else str(t.source),
            "assignee_member_id": t.assignee_member_id,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })
    
    return {"count": len(result), "tasks": result}


@app.post("/api/tasks")
async def create_task(task: TaskCreate):
    """Create a new task, optionally syncing to GitHub/Lark."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    from src.agent.tools.github_tools import GitHubTools
    from src.agent.tools.lark_tools import LarkTools
    
    results = {"task_id": None, "github_issue": None, "lark_record": None}
    
    if task.create_github_issue and _github_svc:
        gh_tools = GitHubTools(_db, _github_svc, _lark_svc)
        result = gh_tools.create_issue(
            title=task.title,
            body=task.body or "",
            assignee=task.assignee,
            labels=task.labels,
            send_to_lark=task.create_lark_record,
            target_table=task.target_table,
        )
        results["github_issue"] = result
    
    if task.create_lark_record and _lark_svc and not task.create_github_issue:
        lark_tools = LarkTools(_db, _lark_svc, _github_svc)
        result = lark_tools.create_record(
            title=task.title,
            body=task.body,
            assignee=task.assignee,
            table_name=task.target_table,
        )
        results["lark_record"] = result
    
    return results


@app.get("/api/issues")
async def list_github_issues(state: str = "open", assignee: Optional[str] = None):
    """List GitHub issues."""
    if not _github_svc:
        raise HTTPException(status_code=503, detail="GitHub service not configured")
    
    try:
        issues = _github_svc.list_issues(state=state, assignee=assignee)
        return {
            "count": len(issues),
            "issues": [
                {
                    "number": i["number"],
                    "title": i["title"],
                    "state": i["state"],
                    "assignees": [a["login"] for a in i.get("assignees", [])],
                    "labels": [l["name"] for l in i.get("labels", [])],
                    "url": i.get("html_url"),
                }
                for i in issues[:50]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/issues")
async def create_github_issue(issue: IssueCreate):
    """Create a GitHub issue."""
    if not _github_svc:
        raise HTTPException(status_code=503, detail="GitHub service not configured")
    
    from src.agent.tools.github_tools import GitHubTools
    
    gh_tools = GitHubTools(_db, _github_svc, _lark_svc)
    result = gh_tools.create_issue(
        title=issue.title,
        body=issue.body or "",
        assignee=issue.assignee,
        labels=issue.labels,
        send_to_lark=issue.sync_to_lark,
    )
    return {"result": result}


@app.get("/api/mappings")
async def list_mappings():
    """List all task-issue-record mappings."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    repo = MappingRepository(_db)
    mappings = repo.list_all()
    
    return {
        "count": len(mappings),
        "mappings": [
            {
                "task_id": m.task_id,
                "github_issue_number": m.github_issue_number,
                "github_repo": m.github_repo,
                "lark_record_id": m.lark_record_id,
                "lark_table_id": m.lark_table_id,
            }
            for m in mappings
        ]
    }


@app.post("/api/sync/run")
async def run_sync():
    """Trigger a manual sync."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    from src.sync.engine import SyncEngine
    
    try:
        engine = SyncEngine(_db, _github_svc, _lark_svc)
        result = engine.process_outbox()
        return {"status": "completed", "processed": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Admin endpoints
@app.post("/api/admin/transfer-owner")
async def transfer_owner_to_admin():
    """Transfer Lark Bitable ownership/permission to Yang Li (Admin).
    
    Yang Li is the user who provides the user token for OAuth.
    """
    if not _lark_svc:
        raise HTTPException(status_code=503, detail="Lark service not configured")
    
    admin_name = os.getenv("LARK_ADMIN_NAME", "Yang Li")
    admin_email = os.getenv("LARK_ADMIN_EMAIL", "")
    admin_open_id = os.getenv("LARK_ADMIN_OPEN_ID", "")
    
    try:
        _lark_svc._init_direct_client()
        
        if not admin_open_id and admin_email:
            user = _lark_svc.direct.get_user_by_email(admin_email)
            if user:
                admin_open_id = user.get("user_id")
        
        if not admin_open_id:
            from src.db.member_repo import MemberRepository
            member_repo = MemberRepository(_db)
            results = member_repo.find_by_name(admin_name)
            if results and results[0].lark_open_id:
                admin_open_id = results[0].lark_open_id
        
        if not admin_open_id:
            return {
                "status": "error",
                "message": f"Cannot find Lark ID for {admin_name}. Please set LARK_ADMIN_OPEN_ID or LARK_ADMIN_EMAIL in .env"
            }
        
        app_token = os.getenv("LARK_APP_TOKEN")
        if not app_token:
            raise HTTPException(status_code=500, detail="LARK_APP_TOKEN not configured")
        
        result = _lark_svc.direct.add_bitable_collaborator(
            app_token,
            admin_open_id,
            perm="full_access",
        )
        
        return {
            "status": "success",
            "message": f"Full access permission granted to {admin_name} ({admin_open_id[:12]}...)",
            "result": result,
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Transfer failed: {str(e)}",
        }


@app.get("/api/admin/collaborators")
async def list_collaborators():
    """List all Lark Bitable collaborators."""
    if not _lark_svc:
        raise HTTPException(status_code=503, detail="Lark service not configured")
    
    try:
        _lark_svc._init_direct_client()
        app_token = os.getenv("LARK_APP_TOKEN")
        collaborators = _lark_svc.direct.list_bitable_collaborators(app_token)
        
        return {
            "count": len(collaborators),
            "collaborators": collaborators,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/sync-members")
async def sync_members_from_platforms():
    """Sync members from both GitHub and Lark to local DB."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    from src.agent.tools.member_tools import MemberTools
    
    tools = MemberTools(_db, _lark_svc, _github_svc)
    result = tools.sync_all_members()
    
    return {"status": "completed", "result": result}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
