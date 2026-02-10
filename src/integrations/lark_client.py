"""
Lark (Feishu) API client
"""
import requests
import time
import json
import logging
from typing import Optional, List, Dict, Any
from functools import wraps

from src.config import settings

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = 3, backoff_factor: int = 2):
    """Decorator for retrying failed API calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    
                    sleep_time = backoff_factor ** attempt
                    logger.warning(f"Request failed: {e}. Retry {attempt + 1}/{max_retries} after {sleep_time}s...")
                    time.sleep(sleep_time)
            
            raise Exception(f"Failed after {max_retries} retries")
        return wrapper
    return decorator


class LarkAuth:
    """Lark authentication manager"""
    
    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        self.app_id = app_id or settings.LARK_APP_ID
        self.app_secret = app_secret or settings.LARK_APP_SECRET
        self.base_url = settings.LARK_API_BASE_URL
        
        if not self.app_id or not self.app_secret:
            raise ValueError("Lark app_id and app_secret are required")
        
        self.tenant_access_token: Optional[str] = None
        self.token_expires_at: float = 0
    
    def get_tenant_access_token(self) -> str:
        """Get or refresh tenant access token"""
        # Return cached token if still valid
        if self.tenant_access_token and time.time() < self.token_expires_at:
            return self.tenant_access_token
        
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        logger.info("Fetching new tenant access token")
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to get token: {data.get('msg')}")
        
        # Cache token (expires in 2 hours, we refresh at 1.5 hours)
        self.tenant_access_token = data["tenant_access_token"]
        self.token_expires_at = time.time() + 5400  # 1.5 hours
        
        logger.info("Successfully obtained tenant access token")
        return self.tenant_access_token
    
    def get_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.get_tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8"
        }


class LarkTaskAPI:
    """Lark Task API client"""
    
    def __init__(self, auth: LarkAuth):
        self.auth = auth
        self.base_url = f"{auth.base_url}/task/v2"
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def create_task(
        self,
        summary: str,
        description: Optional[str] = None,
        assignees: Optional[List[str]] = None,
        due_timestamp: Optional[int] = None,
        tasklist_guid: Optional[str] = None,
        section_guid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a task in Lark"""
        url = f"{self.base_url}/tasks"
        
        payload = {"summary": summary}
        
        if description:
            payload["description"] = description
        
        if due_timestamp:
            payload["due"] = {
                "timestamp": str(due_timestamp),
                "is_all_day": False
            }
        
        if assignees:
            payload["members"] = [
                {
                    "id": assignee_id,
                    "type": "user",
                    "role": "assignee"
                }
                for assignee_id in assignees
            ]
        
        if tasklist_guid and section_guid:
            payload["tasklists"] = [{
                "tasklist_guid": tasklist_guid,
                "section_guid": section_guid
            }]
        
        logger.info(f"Creating Lark task: {summary}")
        response = requests.post(url, json=payload, headers=self.auth.get_headers())
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to create task: {data.get('msg')}")
        
        task = data["data"]["task"]
        logger.info(f"Created task: {task['guid']}")
        return task
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def update_task(
        self,
        task_guid: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        completed: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update a task"""
        url = f"{self.base_url}/tasks/{task_guid}"
        
        task_data = {}
        update_fields = []
        
        if summary is not None:
            task_data["summary"] = summary
            update_fields.append("summary")
        
        if description is not None:
            task_data["description"] = description
            update_fields.append("description")
        
        if completed is not None:
            if completed:
                task_data["completed_at"] = str(int(time.time()))
            else:
                task_data["completed_at"] = "0"
            update_fields.append("completed_at")
        
        payload = {
            "task": task_data,
            "update_fields": update_fields
        }
        
        logger.info(f"Updating Lark task: {task_guid}")
        response = requests.patch(url, json=payload, headers=self.auth.get_headers())
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to update task: {data.get('msg')}")
        
        return data["data"]["task"]
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def get_task(self, task_guid: str) -> Dict[str, Any]:
        """Get task details"""
        url = f"{self.base_url}/tasks/{task_guid}"
        
        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to get task: {data.get('msg')}")
        
        return data["data"]["task"]
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def list_tasks(self, completed: Optional[bool] = None, page_size: int = 50) -> List[Dict[str, Any]]:
        """List tasks with pagination"""
        url = f"{self.base_url}/tasks"
        
        params = {"page_size": page_size}
        if completed is not None:
            params["completed"] = "true" if completed else "false"
        
        all_tasks = []
        page_token = None
        
        while True:
            if page_token:
                params["page_token"] = page_token
            
            response = requests.get(url, params=params, headers=self.auth.get_headers())
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise Exception(f"Failed to list tasks: {data.get('msg')}")
            
            tasks = data["data"].get("items", [])
            all_tasks.extend(tasks)
            
            # Check if there are more pages
            page_token = data["data"].get("page_token")
            if not page_token:
                break
        
        return all_tasks


class LarkMessageAPI:
    """Lark Messaging API client"""
    
    def __init__(self, auth: LarkAuth):
        self.auth = auth
        self.base_url = f"{auth.base_url}/im/v1"
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def send_text_message(self, user_id: str, text: str, id_type: str = "open_id") -> Dict[str, Any]:
        """Send text message to user"""
        url = f"{self.base_url}/messages"
        
        params = {"receive_id_type": id_type}
        
        payload = {
            "receive_id": user_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }
        
        logger.info(f"Sending text message to {user_id}")
        response = requests.post(url, params=params, json=payload, headers=self.auth.get_headers())
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to send message: {data.get('msg')}")
        
        return data["data"]
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def send_card_message(self, user_id: str, card_content: Dict[str, Any], id_type: str = "open_id") -> Dict[str, Any]:
        """Send interactive card message"""
        url = f"{self.base_url}/messages"
        
        params = {"receive_id_type": id_type}
        
        payload = {
            "receive_id": user_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content)
        }
        
        logger.info(f"Sending card message to {user_id}")
        response = requests.post(url, params=params, json=payload, headers=self.auth.get_headers())
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to send card: {data.get('msg')}")
        
        return data["data"]


class LarkClient:
    """Unified Lark API client"""
    
    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        self.auth = LarkAuth(app_id, app_secret)
        self.tasks = LarkTaskAPI(self.auth)
        self.messages = LarkMessageAPI(self.auth)
