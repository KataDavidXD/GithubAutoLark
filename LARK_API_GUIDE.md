# Lark (Feishu) API Integration Guide

## Overview

This guide covers the setup and usage of Lark (Feishu) API for the Project Position System. Lark is a collaboration platform widely used in enterprises, especially in Asia.

## Prerequisites

- Lark Developer Account
- Admin access to your Lark workspace
- Basic understanding of OAuth 2.0

## Application Setup

### 1. Create a Lark App

1. Go to [Lark Open Platform](https://open.feishu.cn/app) (International) or [Feishu Open Platform](https://open.feishu.cn/app) (China)
2. Click "Create custom app"
3. Fill in app information:
   - **App Name**: Project Position Bot
   - **App Description**: Automated task management and synchronization
   - **App Icon**: Upload an icon
4. Click "Create"

### 2. Configure App Credentials

After creation, you'll get:
- **App ID**: `cli_xxxxxxxxxx`
- **App Secret**: Click "View" to see the secret

```bash
# Add to .env file
LARK_APP_ID=cli_xxxxxxxxxx
LARK_APP_SECRET=your_app_secret_here
```

### 3. Configure Permissions (Scopes)

Go to App Details → Permissions & Scopes

**Required Scopes**:

**Task Management**:
- `task:task` - Create, read, update, delete tasks
- `task:task:readonly` - Read task information

**Messaging**:
- `im:message` - Send messages
- `im:message:send_as_bot` - Send messages as bot
- `im:chat` - Access chat information

**User Information**:
- `contact:user.id:readonly` - Read user OpenID
- `contact:user.base:readonly` - Read basic user info

**Event Subscriptions**:
- `task:task:event` - Receive task events

### 4. Version Management

1. Go to "Version Management & Release"
2. Create a new version
3. Set availability scope:
   - **All members** (recommended for internal use)
   - Or specific departments/users
4. Submit for review (automatic approval for internal apps)
5. Publish the version

## Authentication

### Tenant Access Token (Server-to-Server)

For backend operations, use tenant access token.

**Endpoint**: `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`

**Request**:
```json
{
  "app_id": "cli_xxxxxxxxxx",
  "app_secret": "your_app_secret"
}
```

**Python Implementation**:
```python
import requests
import time

class LarkAuth:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_access_token = None
        self.token_expires_at = 0
    
    def get_tenant_access_token(self):
        """Get or refresh tenant access token"""
        # Return cached token if still valid
        if self.tenant_access_token and time.time() < self.token_expires_at:
            return self.tenant_access_token
        
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to get token: {data.get('msg')}")
        
        # Cache token (expires in 2 hours, we refresh at 1.5 hours)
        self.tenant_access_token = data["tenant_access_token"]
        self.token_expires_at = time.time() + 5400  # 1.5 hours
        
        return self.tenant_access_token
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.get_tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8"
        }
```

## Task API Operations

### 1. Create a Task

**Endpoint**: `POST https://open.feishu.cn/open-apis/task/v2/tasks`

**Request Body**:
```json
{
  "summary": "Implement user authentication",
  "description": "## Description\n\nImplement JWT-based authentication...\n\n## Acceptance Criteria\n\n- [ ] Login endpoint\n- [ ] Token generation",
  "due": {
    "timestamp": "1707552000",
    "is_all_day": false
  },
  "members": [
    {
      "id": "ou_xxxxxxxxxx",
      "type": "user",
      "role": "assignee"
    }
  ],
  "completed_at": null,
  "tasklists": [
    {
      "tasklist_guid": "tasklist_guid_xxxxx",
      "section_guid": "section_guid_xxxxx"
    }
  ]
}
```

**Python Implementation**:
```python
class LarkTaskAPI:
    def __init__(self, auth: LarkAuth):
        self.auth = auth
        self.base_url = "https://open.feishu.cn/open-apis/task/v2"
    
    def create_task(self, summary, description=None, assignees=None, due_timestamp=None):
        """Create a task in Lark"""
        url = f"{self.base_url}/tasks"
        
        payload = {
            "summary": summary,
        }
        
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
        
        response = requests.post(
            url,
            json=payload,
            headers=self.auth.get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to create task: {data.get('msg')}")
        
        return data["data"]["task"]

# Example usage
auth = LarkAuth(app_id="cli_xxx", app_secret="secret")
task_api = LarkTaskAPI(auth)

task = task_api.create_task(
    summary="Implement login API",
    description="Create JWT-based authentication endpoint",
    assignees=["ou_user123"],
    due_timestamp=1707552000
)
print(f"Created task: {task['guid']}")
```

### 2. Update a Task

**Endpoint**: `PATCH https://open.feishu.cn/open-apis/task/v2/tasks/{task_guid}`

**Request Body**:
```json
{
  "task": {
    "summary": "Updated task title",
    "completed_at": "1707552000"
  },
  "update_fields": ["summary", "completed_at"]
}
```

**Python Implementation**:
```python
def update_task(self, task_guid, summary=None, completed=None, description=None):
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
    
    response = requests.patch(
        url,
        json=payload,
        headers=self.auth.get_headers()
    )
    response.raise_for_status()
    data = response.json()
    
    if data.get("code") != 0:
        raise Exception(f"Failed to update task: {data.get('msg')}")
    
    return data["data"]["task"]
```

### 3. Get Task Details

**Endpoint**: `GET https://open.feishu.cn/open-apis/task/v2/tasks/{task_guid}`

**Python Implementation**:
```python
def get_task(self, task_guid):
    """Get task details"""
    url = f"{self.base_url}/tasks/{task_guid}"
    
    response = requests.get(url, headers=self.auth.get_headers())
    response.raise_for_status()
    data = response.json()
    
    if data.get("code") != 0:
        raise Exception(f"Failed to get task: {data.get('msg')}")
    
    return data["data"]["task"]
```

### 4. List Tasks

**Endpoint**: `GET https://open.feishu.cn/open-apis/task/v2/tasks`

**Query Parameters**:
- `page_size`: Number of items per page (max 100)
- `page_token`: Pagination token
- `completed`: Filter by completion status

**Python Implementation**:
```python
def list_tasks(self, completed=None, page_size=50):
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
        
        response = requests.get(
            url,
            params=params,
            headers=self.auth.get_headers()
        )
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
```

## Messaging API

### 1. Send Message to User

**Endpoint**: `POST https://open.feishu.cn/open-apis/im/v1/messages`

**Query Parameters**: `receive_id_type=open_id` (or `user_id`, `email`)

**Request Body**:
```json
{
  "receive_id": "ou_xxxxxxxxxx",
  "msg_type": "text",
  "content": "{\"text\":\"Your task status update failed. Please check.\"}"
}
```

**Python Implementation**:
```python
class LarkMessageAPI:
    def __init__(self, auth: LarkAuth):
        self.auth = auth
        self.base_url = "https://open.feishu.cn/open-apis/im/v1"
    
    def send_text_message(self, user_id, text, id_type="open_id"):
        """Send text message to user"""
        url = f"{self.base_url}/messages"
        
        params = {"receive_id_type": id_type}
        
        payload = {
            "receive_id": user_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }
        
        response = requests.post(
            url,
            params=params,
            json=payload,
            headers=self.auth.get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to send message: {data.get('msg')}")
        
        return data["data"]
    
    def send_card_message(self, user_id, card_content, id_type="open_id"):
        """Send interactive card message"""
        url = f"{self.base_url}/messages"
        
        params = {"receive_id_type": id_type}
        
        payload = {
            "receive_id": user_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content)
        }
        
        response = requests.post(
            url,
            params=params,
            json=payload,
            headers=self.auth.get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to send card: {data.get('msg')}")
        
        return data["data"]

# Example: Send sync failure notification
msg_api = LarkMessageAPI(auth)

msg_api.send_text_message(
    user_id="ou_user123",
    text="⚠️ Sync Failed\n\nTask 'Implement login' failed to sync with GitHub. Please check manually."
)
```

### 2. Rich Message Card Example

```python
def create_sync_failure_card(task_title, error_message, github_url=None):
    """Create a rich card for sync failure notification"""
    card = {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "⚠️ GitHub Sync Failed"
            },
            "template": "red"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**Task**: {task_title}\n**Error**: {error_message}"
                }
            },
            {
                "tag": "hr"
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "Please check the task manually and ensure it's synced with GitHub."
                    }
                ]
            }
        ]
    }
    
    if github_url:
        card["elements"].insert(1, {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "View on GitHub"
                    },
                    "url": github_url,
                    "type": "primary"
                }
            ]
        })
    
    return card

# Send card
msg_api.send_card_message(
    user_id="ou_user123",
    card_content=create_sync_failure_card(
        task_title="Implement login API",
        error_message="GitHub API rate limit exceeded",
        github_url="https://github.com/org/repo/issues/42"
    )
)
```

## Event Subscription (Webhooks)

### 1. Configure Event Subscription

1. Go to App Details → Event Subscriptions
2. Configure Request URL: `https://your-domain.com/webhooks/lark`
3. Enable event encryption (recommended)
4. Subscribe to events:
   - `task.task.updated_v2` - Task updated
   - `task.task.created_v2` - Task created
   - `task.task.deleted_v2` - Task deleted

### 2. Handle Webhook Events

**Event Payload Structure**:
```json
{
  "schema": "2.0",
  "header": {
    "event_id": "xxx",
    "event_type": "task.task.updated_v2",
    "create_time": "1707552000000",
    "token": "verification_token",
    "app_id": "cli_xxx"
  },
  "event": {
    "task": {
      "guid": "task_guid_xxx",
      "summary": "Task title",
      "completed_at": "1707552000"
    }
  }
}
```

**Python Implementation (Flask)**:
```python
from flask import Flask, request, jsonify
import hashlib
import json

app = Flask(__name__)

class LarkWebhookHandler:
    def __init__(self, verification_token, encrypt_key=None):
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
    
    def verify_request(self, request_data):
        """Verify webhook request"""
        token = request_data.get("header", {}).get("token")
        return token == self.verification_token
    
    def handle_event(self, event_data):
        """Handle webhook event"""
        event_type = event_data["header"]["event_type"]
        event = event_data["event"]
        
        if event_type == "task.task.updated_v2":
            return self.handle_task_updated(event)
        elif event_type == "task.task.created_v2":
            return self.handle_task_created(event)
        elif event_type == "task.task.deleted_v2":
            return self.handle_task_deleted(event)
        
        return {"status": "ok"}
    
    def handle_task_updated(self, event):
        """Handle task update event"""
        task = event["task"]
        task_guid = task["guid"]
        
        # Check if task is completed
        if task.get("completed_at") and task["completed_at"] != "0":
            print(f"Task {task_guid} completed, syncing to GitHub...")
            # Sync to GitHub
            self.sync_task_to_github(task_guid)
        
        return {"status": "ok"}
    
    def sync_task_to_github(self, task_guid):
        """Sync task status to GitHub"""
        # Query local DB for GitHub issue mapping
        # Update GitHub issue
        # If sync fails, send notification
        pass

# Flask route
webhook_handler = LarkWebhookHandler(
    verification_token=os.getenv("LARK_VERIFICATION_TOKEN")
)

@app.route('/webhooks/lark', methods=['POST'])
def lark_webhook():
    data = request.json
    
    # Handle URL verification (first-time setup)
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})
    
    # Verify request
    if not webhook_handler.verify_request(data):
        return jsonify({"error": "Invalid token"}), 401
    
    # Handle event
    result = webhook_handler.handle_event(data)
    
    return jsonify(result), 200
```

## User API

### Get User Information

**Endpoint**: `GET https://open.feishu.cn/open-apis/contact/v3/users/{user_id}`

**Python Implementation**:
```python
class LarkUserAPI:
    def __init__(self, auth: LarkAuth):
        self.auth = auth
        self.base_url = "https://open.feishu.cn/open-apis/contact/v3"
    
    def get_user(self, user_id, user_id_type="open_id"):
        """Get user information"""
        url = f"{self.base_url}/users/{user_id}"
        
        params = {"user_id_type": user_id_type}
        
        response = requests.get(
            url,
            params=params,
            headers=self.auth.get_headers()
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to get user: {data.get('msg')}")
        
        return data["data"]["user"]
```

## Error Handling

### Common Error Codes

- `0`: Success
- `99991663`: Invalid token
- `99991664`: Token expired
- `99991665`: Insufficient permissions
- `230001`: Task not found
- `230002`: Invalid task parameter

### Retry Logic

```python
import time
from functools import wraps

def retry_on_failure(max_retries=3, backoff_factor=2):
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
                    
                    # Check if it's a rate limit or server error
                    if hasattr(e, 'response') and e.response:
                        status_code = e.response.status_code
                        if status_code in [429, 500, 502, 503, 504]:
                            sleep_time = backoff_factor ** attempt
                            print(f"Retry {attempt + 1}/{max_retries} after {sleep_time}s...")
                            time.sleep(sleep_time)
                            continue
                    raise
        return wrapper
    return decorator

# Usage
@retry_on_failure(max_retries=3, backoff_factor=2)
def create_task_with_retry(summary, description):
    return task_api.create_task(summary, description)
```

## Rate Limiting

- **Default**: 200 requests per minute per app
- **Tenant access token**: 2-hour expiry
- Use caching and batch operations when possible

## Testing

### Mock Lark API for Testing

```python
import unittest
from unittest.mock import Mock, patch

class TestLarkAPI(unittest.TestCase):
    def setUp(self):
        self.auth = LarkAuth("test_app_id", "test_secret")
        self.task_api = LarkTaskAPI(self.auth)
    
    @patch('requests.post')
    def test_create_task(self, mock_post):
        # Mock response
        mock_post.return_value.json.return_value = {
            "code": 0,
            "data": {
                "task": {
                    "guid": "task_123",
                    "summary": "Test task"
                }
            }
        }
        
        task = self.task_api.create_task("Test task")
        self.assertEqual(task["guid"], "task_123")
```

## Best Practices

1. **Token Management**: Cache tenant access token, refresh before expiry
2. **Error Handling**: Implement retry logic with exponential backoff
3. **Webhook Security**: Always verify webhook tokens
4. **Rate Limiting**: Batch operations, implement request queuing
5. **Logging**: Log all API calls for debugging
6. **User Privacy**: Only request necessary user permissions
7. **Message Content**: Use rich cards for better UX

## Resources

- [Lark Open Platform Documentation](https://open.feishu.cn/document/)
- [Task API Reference](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/task-v2/overview)
- [Messaging API Reference](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/im-v1/message/create)
- [Event Subscription Guide](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)
- [Lark SDK (Python)](https://github.com/larksuite/oapi-sdk-python)
