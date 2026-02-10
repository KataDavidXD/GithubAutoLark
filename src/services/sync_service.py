"""
Synchronization service for GitHub and Lark
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import json

from src.core import db
from src.models import Task, GitHubIssue, LarkTask
from src.integrations import GitHubClient, LarkClient
from src.services.task_service import TaskService, EmployeeService
from src.config import settings

logger = logging.getLogger(__name__)


class SyncService:
    """Service for synchronizing tasks between systems"""
    
    def __init__(self):
        self.github_client = None
        self.lark_client = None
        
        # Initialize clients if enabled
        if settings.GITHUB_SYNC_ENABLED and settings.GITHUB_TOKEN:
            try:
                self.github_client = GitHubClient()
            except Exception as e:
                logger.warning(f"Failed to initialize GitHub client: {e}")
        
        if settings.LARK_SYNC_ENABLED and settings.LARK_APP_ID:
            try:
                self.lark_client = LarkClient()
            except Exception as e:
                logger.warning(f"Failed to initialize Lark client: {e}")
    
    def sync_task_to_github(self, task: Task) -> Optional[GitHubIssue]:
        """Sync task to GitHub as an issue"""
        if not self.github_client:
            logger.warning("GitHub client not initialized")
            return None
        
        try:
            # Check if already synced
            existing = self._get_github_issue_by_task(task.id)
            if existing:
                logger.info(f"Task {task.id} already synced to GitHub issue #{existing['issue_number']}")
                return GitHubIssue(**existing)
            
            # Get assignees
            assignees = TaskService.get_task_assignees(task.id)
            github_usernames = [e.github_username for e in assignees if e.github_username]
            
            # Create GitHub issue
            issue_body = self._format_task_description(task)
            labels = self._get_task_labels(task)
            
            issue = self.github_client.create_issue(
                title=task.title,
                body=issue_body,
                assignees=github_usernames,
                labels=labels
            )
            
            # Save mapping to database
            github_issue = GitHubIssue(
                task_id=task.id,
                repo_owner=settings.GITHUB_ORG,
                repo_name=settings.GITHUB_REPO,
                issue_number=issue["number"],
                issue_url=issue["html_url"],
                github_status=issue["state"],
                labels=json.dumps([label["name"] for label in issue.get("labels", [])]),
                last_synced_at=datetime.now()
            )
            
            github_issue.id = self._save_github_issue(github_issue)
            
            # Log sync
            self._log_sync("github", "create", "success", task.id)
            
            return github_issue
            
        except Exception as e:
            logger.error(f"Failed to sync task {task.id} to GitHub: {e}")
            self._log_sync("github", "create", "failed", task.id, error_message=str(e))
            return None
    
    def sync_task_to_lark(self, task: Task) -> Optional[LarkTask]:
        """Sync task to Lark"""
        if not self.lark_client:
            logger.warning("Lark client not initialized")
            return None
        
        try:
            # Check if already synced
            existing = self._get_lark_task_by_task(task.id)
            if existing:
                logger.info(f"Task {task.id} already synced to Lark task {existing['lark_task_guid']}")
                return LarkTask(**existing)
            
            # Get assignees
            assignees = TaskService.get_task_assignees(task.id)
            lark_user_ids = [e.lark_user_id for e in assignees if e.lark_user_id]
            
            # Create Lark task
            due_timestamp = int(task.due_date.timestamp()) if task.due_date else None
            
            lark_task_data = self.lark_client.tasks.create_task(
                summary=task.title,
                description=task.description or "",
                assignees=lark_user_ids,
                due_timestamp=due_timestamp
            )
            
            # Save mapping to database
            lark_task = LarkTask(
                task_id=task.id,
                lark_task_guid=lark_task_data["guid"],
                lark_task_url=lark_task_data.get("url"),
                lark_status="open",
                last_synced_at=datetime.now()
            )
            
            lark_task.id = self._save_lark_task(lark_task)
            
            # Log sync
            self._log_sync("lark", "create", "success", task.id)
            
            return lark_task
            
        except Exception as e:
            logger.error(f"Failed to sync task {task.id} to Lark: {e}")
            self._log_sync("lark", "create", "failed", task.id, error_message=str(e))
            return None
    
    def update_github_from_task(self, task: Task) -> bool:
        """Update GitHub issue from task status"""
        if not self.github_client:
            return False
        
        try:
            github_issue = self._get_github_issue_by_task(task.id)
            if not github_issue:
                logger.warning(f"No GitHub issue found for task {task.id}")
                return False
            
            # Determine GitHub state
            github_state = "closed" if task.status == "completed" else "open"
            
            # Update issue
            self.github_client.update_issue(
                issue_number=github_issue["issue_number"],
                state=github_state
            )
            
            # Update mapping
            query = """
                UPDATE github_issues 
                SET github_status = ?, last_synced_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            db.execute_write(query, (github_state, github_issue["id"]))
            
            # Log sync
            self._log_sync("github", "update", "success", task.id)
            
            logger.info(f"Updated GitHub issue #{github_issue['issue_number']} to {github_state}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update GitHub from task {task.id}: {e}")
            self._log_sync("github", "update", "failed", task.id, error_message=str(e))
            return False
    
    def update_lark_from_task(self, task: Task) -> bool:
        """Update Lark task from task status"""
        if not self.lark_client:
            return False
        
        try:
            lark_task = self._get_lark_task_by_task(task.id)
            if not lark_task:
                logger.warning(f"No Lark task found for task {task.id}")
                return False
            
            # Update Lark task
            completed = task.status == "completed"
            
            self.lark_client.tasks.update_task(
                task_guid=lark_task["lark_task_guid"],
                completed=completed
            )
            
            # Update mapping
            query = """
                UPDATE lark_tasks 
                SET last_synced_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            db.execute_write(query, (lark_task["id"],))
            
            # Log sync
            self._log_sync("lark", "update", "success", task.id)
            
            logger.info(f"Updated Lark task {lark_task['lark_task_guid']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update Lark from task {task.id}: {e}")
            self._log_sync("lark", "update", "failed", task.id, error_message=str(e))
            return False
    
    def handle_github_webhook(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """Handle GitHub webhook event"""
        try:
            if event_type == "issues":
                return self._handle_github_issue_event(payload)
            elif event_type == "issue_comment":
                return self._handle_github_comment_event(payload)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to handle GitHub webhook: {e}")
            return False
    
    def handle_lark_webhook(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """Handle Lark webhook event"""
        try:
            if event_type == "task.task.updated_v2":
                return self._handle_lark_task_updated(payload)
            elif event_type == "task.task.created_v2":
                return self._handle_lark_task_created(payload)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to handle Lark webhook: {e}")
            return False
    
    # Private helper methods
    
    def _get_github_issue_by_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get GitHub issue mapping by task ID"""
        query = "SELECT * FROM github_issues WHERE task_id = ?"
        return db.execute_one(query, (task_id,))
    
    def _get_lark_task_by_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get Lark task mapping by task ID"""
        query = "SELECT * FROM lark_tasks WHERE task_id = ?"
        return db.execute_one(query, (task_id,))
    
    def _save_github_issue(self, github_issue: GitHubIssue) -> int:
        """Save GitHub issue mapping"""
        query = """
            INSERT INTO github_issues (
                task_id, repo_owner, repo_name, issue_number, issue_url,
                github_status, labels, last_synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            github_issue.task_id,
            github_issue.repo_owner,
            github_issue.repo_name,
            github_issue.issue_number,
            github_issue.issue_url,
            github_issue.github_status,
            github_issue.labels,
            github_issue.last_synced_at.isoformat() if github_issue.last_synced_at else None
        )
        
        return db.execute_write(query, params)
    
    def _save_lark_task(self, lark_task: LarkTask) -> int:
        """Save Lark task mapping"""
        query = """
            INSERT INTO lark_tasks (
                task_id, lark_task_guid, lark_task_url, lark_status, last_synced_at
            ) VALUES (?, ?, ?, ?, ?)
        """
        params = (
            lark_task.task_id,
            lark_task.lark_task_guid,
            lark_task.lark_task_url,
            lark_task.lark_status,
            lark_task.last_synced_at.isoformat() if lark_task.last_synced_at else None
        )
        
        return db.execute_write(query, params)
    
    def _log_sync(
        self,
        source: str,
        action: str,
        status: str,
        task_id: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        """Log sync operation"""
        query = """
            INSERT INTO sync_logs (task_id, source, action, status, error_message)
            VALUES (?, ?, ?, ?, ?)
        """
        db.execute_write(query, (task_id, source, action, status, error_message))
    
    def _format_task_description(self, task: Task) -> str:
        """Format task description for GitHub issue"""
        lines = []
        
        if task.description:
            lines.append(task.description)
            lines.append("")
        
        lines.append("---")
        lines.append(f"**Priority:** {task.priority}")
        lines.append(f"**Complexity:** {task.complexity}")
        lines.append(f"**Status:** {task.status}")
        
        if task.due_date:
            lines.append(f"**Due Date:** {task.due_date.strftime('%Y-%m-%d')}")
        
        return "\n".join(lines)
    
    def _get_task_labels(self, task: Task) -> list:
        """Get labels for task"""
        labels = []
        
        # Add priority label
        if task.priority in ["high", "critical"]:
            labels.append(f"priority-{task.priority}")
        
        # Add complexity label
        labels.append(f"complexity-{task.complexity}")
        
        return labels
    
    def _handle_github_issue_event(self, payload: Dict[str, Any]) -> bool:
        """Handle GitHub issue event"""
        action = payload.get("action")
        issue = payload.get("issue", {})
        issue_number = issue.get("number")
        
        if not issue_number:
            return False
        
        # Find task by GitHub issue
        query = """
            SELECT task_id FROM github_issues 
            WHERE repo_owner = ? AND repo_name = ? AND issue_number = ?
        """
        result = db.execute_one(query, (settings.GITHUB_ORG, settings.GITHUB_REPO, issue_number))
        
        if not result:
            logger.warning(f"No task found for GitHub issue #{issue_number}")
            return False
        
        task_id = result["task_id"]
        
        # Update task based on issue state
        if action == "closed":
            TaskService.mark_completed(task_id)
            # Sync to Lark
            task = TaskService.get_task(task_id)
            if task:
                self.update_lark_from_task(task)
        
        return True
    
    def _handle_github_comment_event(self, payload: Dict[str, Any]) -> bool:
        """Handle GitHub comment event"""
        # Could be used for additional features
        return True
    
    def _handle_lark_task_updated(self, payload: Dict[str, Any]) -> bool:
        """Handle Lark task updated event"""
        event = payload.get("event", {})
        task_data = event.get("task", {})
        task_guid = task_data.get("guid")
        
        if not task_guid:
            return False
        
        # Find task by Lark task GUID
        query = "SELECT task_id FROM lark_tasks WHERE lark_task_guid = ?"
        result = db.execute_one(query, (task_guid,))
        
        if not result:
            logger.warning(f"No task found for Lark task {task_guid}")
            return False
        
        task_id = result["task_id"]
        
        # Check if task is completed
        completed_at = task_data.get("completed_at")
        if completed_at and completed_at != "0":
            TaskService.mark_completed(task_id)
            # Sync to GitHub
            task = TaskService.get_task(task_id)
            if task:
                success = self.update_github_from_task(task)
                if not success:
                    # Send notification about sync failure
                    self._send_sync_failure_notification(task)
        
        return True
    
    def _handle_lark_task_created(self, payload: Dict[str, Any]) -> bool:
        """Handle Lark task created event"""
        # Could be used for bidirectional sync
        return True
    
    def _send_sync_failure_notification(self, task: Task):
        """Send notification about sync failure"""
        if not self.lark_client or not settings.NOTIFICATION_ENABLED:
            return
        
        try:
            # Get task assignees
            assignees = TaskService.get_task_assignees(task.id)
            
            for assignee in assignees:
                if not assignee.lark_user_id:
                    continue
                
                message = f"⚠️ Sync Failed\n\nTask '{task.title}' failed to sync with GitHub. Please check manually."
                
                self.lark_client.messages.send_text_message(
                    user_id=assignee.lark_user_id,
                    text=message
                )
                
        except Exception as e:
            logger.error(f"Failed to send sync failure notification: {e}")
