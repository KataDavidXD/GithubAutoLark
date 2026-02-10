"""
Task data models
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import uuid


@dataclass
class Task:
    """Task model"""
    id: Optional[int] = None
    task_uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: Optional[str] = None
    status: str = "open"  # 'open', 'in_progress', 'completed', 'cancelled'
    priority: str = "medium"  # 'low', 'medium', 'high', 'critical'
    complexity: str = "medium"  # 'low', 'medium', 'high'
    parent_task_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "task_uuid": self.task_uuid,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "complexity": self.complexity,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by": self.created_by
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """Create from dictionary"""
        # Convert datetime strings to datetime objects
        for date_field in ['created_at', 'updated_at', 'due_date', 'completed_at']:
            if data.get(date_field) and isinstance(data[date_field], str):
                data[date_field] = datetime.fromisoformat(data[date_field])
        
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Employee:
    """Employee model"""
    id: Optional[int] = None
    name: str = ""
    email: Optional[str] = None
    github_username: Optional[str] = None
    lark_user_id: Optional[str] = None
    lark_union_id: Optional[str] = None
    position: str = ""  # 'frontend', 'backend', 'fullstack', 'devops', etc.
    expertise: Optional[str] = None  # JSON string
    max_concurrent_tasks: int = 5
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "github_username": self.github_username,
            "lark_user_id": self.lark_user_id,
            "lark_union_id": self.lark_union_id,
            "position": self.position,
            "expertise": self.expertise,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Employee':
        """Create from dictionary"""
        for date_field in ['created_at', 'updated_at']:
            if data.get(date_field) and isinstance(data[date_field], str):
                data[date_field] = datetime.fromisoformat(data[date_field])
        
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TaskAssignment:
    """Task assignment model"""
    id: Optional[int] = None
    task_id: int = 0
    employee_id: int = 0
    assigned_at: Optional[datetime] = None
    status: str = "assigned"  # 'assigned', 'accepted', 'rejected', 'completed'
    assigned_by: Optional[str] = None
    notes: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "employee_id": self.employee_id,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "status": self.status,
            "assigned_by": self.assigned_by,
            "notes": self.notes
        }


@dataclass
class GitHubIssue:
    """GitHub issue mapping model"""
    id: Optional[int] = None
    task_id: int = 0
    repo_owner: str = ""
    repo_name: str = ""
    issue_number: int = 0
    issue_url: Optional[str] = None
    github_status: Optional[str] = None
    github_state_reason: Optional[str] = None
    labels: Optional[str] = None  # JSON string
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_enabled: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "github_status": self.github_status,
            "github_state_reason": self.github_state_reason,
            "labels": self.labels,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "sync_enabled": self.sync_enabled
        }


@dataclass
class LarkTask:
    """Lark task mapping model"""
    id: Optional[int] = None
    task_id: int = 0
    lark_task_guid: str = ""
    lark_task_url: Optional[str] = None
    lark_status: Optional[str] = None
    lark_tasklist_guid: Optional[str] = None
    lark_section_guid: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_enabled: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "lark_task_guid": self.lark_task_guid,
            "lark_task_url": self.lark_task_url,
            "lark_status": self.lark_status,
            "lark_tasklist_guid": self.lark_tasklist_guid,
            "lark_section_guid": self.lark_section_guid,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "sync_enabled": self.sync_enabled
        }
