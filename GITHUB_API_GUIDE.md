# GitHub API Integration Guide

## Overview

This guide covers the setup and usage of GitHub API for the Project Position System.

## Authentication Setup

### 1. Create a GitHub Personal Access Token (PAT)

#### For Organization/Repository Access:
1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Name: `project-position-system`
4. Expiration: Set according to your security policy
5. Select scopes:
   - ✅ `repo` (Full control of private repositories)
     - `repo:status`
     - `repo_deployment`
     - `public_repo`
     - `repo:invite`
   - ✅ `write:discussion` (Write discussions)
   - ✅ `project` (Full control of projects)
   - ✅ `admin:org_hook` (if using webhooks at org level)

6. Click "Generate token"
7. **IMPORTANT**: Copy the token immediately (you won't see it again)

#### For Fine-Grained Personal Access Token (Recommended):
1. Go to Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Click "Generate new token"
3. Token name: `project-position-system`
4. Expiration: Set appropriate expiration
5. Repository access: Select specific repositories
6. Permissions:
   - **Repository permissions**:
     - Issues: Read and write
     - Metadata: Read-only
     - Projects: Read and write
     - Pull requests: Read and write (optional)
     - Webhooks: Read and write
   - **Organization permissions** (if applicable):
     - Members: Read-only
     - Projects: Read and write

### 2. Store Token Securely

```bash
# Add to .env file (never commit this file)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_ORG=your-organization-name
GITHUB_REPO=your-repository-name
```

## API Endpoints Reference

### Base URL
```
https://api.github.com
```

### Common Headers
```python
headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}
```

### Core Operations

#### 1. Create an Issue

**Endpoint**: `POST /repos/{owner}/{repo}/issues`

**Request Body**:
```json
{
  "title": "Task: Implement user authentication",
  "body": "## Description\n\nImplement JWT-based authentication...\n\n## Acceptance Criteria\n\n- [ ] Login endpoint\n- [ ] Token generation\n- [ ] Token validation",
  "assignees": ["username1", "username2"],
  "labels": ["enhancement", "backend", "high-priority"],
  "milestone": 1
}
```

**Python Example**:
```python
import requests
import os

def create_github_issue(title, description, assignees=None, labels=None):
    """Create a GitHub issue"""
    url = f"https://api.github.com/repos/{os.getenv('GITHUB_ORG')}/{os.getenv('GITHUB_REPO')}/issues"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    payload = {
        "title": title,
        "body": description,
    }
    
    if assignees:
        payload["assignees"] = assignees
    if labels:
        payload["labels"] = labels
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    return response.json()

# Example usage
issue = create_github_issue(
    title="Implement user login",
    description="Create login API endpoint with JWT authentication",
    assignees=["johndoe"],
    labels=["backend", "authentication"]
)
print(f"Created issue #{issue['number']}: {issue['html_url']}")
```

#### 2. Update an Issue

**Endpoint**: `PATCH /repos/{owner}/{repo}/issues/{issue_number}`

**Request Body**:
```json
{
  "state": "closed",
  "state_reason": "completed",
  "labels": ["completed", "backend"],
  "assignees": ["username1"]
}
```

**Python Example**:
```python
def update_github_issue(issue_number, state=None, labels=None, assignees=None):
    """Update a GitHub issue"""
    url = f"https://api.github.com/repos/{os.getenv('GITHUB_ORG')}/{os.getenv('GITHUB_REPO')}/issues/{issue_number}"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    payload = {}
    if state:
        payload["state"] = state  # "open" or "closed"
    if labels is not None:
        payload["labels"] = labels
    if assignees is not None:
        payload["assignees"] = assignees
    
    response = requests.patch(url, json=payload, headers=headers)
    response.raise_for_status()
    
    return response.json()
```

#### 3. List Issues

**Endpoint**: `GET /repos/{owner}/{repo}/issues`

**Query Parameters**:
- `state`: `open`, `closed`, `all`
- `labels`: Comma-separated label names
- `assignee`: Username
- `since`: ISO 8601 timestamp
- `per_page`: Results per page (max 100)
- `page`: Page number

**Python Example**:
```python
def list_github_issues(state="open", labels=None, assignee=None):
    """List GitHub issues"""
    url = f"https://api.github.com/repos/{os.getenv('GITHUB_ORG')}/{os.getenv('GITHUB_REPO')}/issues"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    params = {"state": state}
    if labels:
        params["labels"] = ",".join(labels)
    if assignee:
        params["assignee"] = assignee
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    return response.json()
```

#### 4. Get a Specific Issue

**Endpoint**: `GET /repos/{owner}/{repo}/issues/{issue_number}`

**Python Example**:
```python
def get_github_issue(issue_number):
    """Get a specific GitHub issue"""
    url = f"https://api.github.com/repos/{os.getenv('GITHUB_ORG')}/{os.getenv('GITHUB_REPO')}/issues/{issue_number}"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    return response.json()
```

#### 5. Add Comment to Issue

**Endpoint**: `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`

**Python Example**:
```python
def add_issue_comment(issue_number, comment_body):
    """Add a comment to an issue"""
    url = f"https://api.github.com/repos/{os.getenv('GITHUB_ORG')}/{os.getenv('GITHUB_REPO')}/issues/{issue_number}/comments"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    payload = {"body": comment_body}
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    return response.json()
```

## Webhook Setup

### 1. Configure Webhook in GitHub Repository

1. Go to Repository → Settings → Webhooks → Add webhook
2. Payload URL: `https://your-domain.com/webhooks/github`
3. Content type: `application/json`
4. Secret: Generate a random secret and save it
5. Select events:
   - ✅ Issues
   - ✅ Issue comments
   - ✅ Label
6. Active: ✅
7. Click "Add webhook"

### 2. Webhook Payload Examples

#### Issue Opened Event
```json
{
  "action": "opened",
  "issue": {
    "number": 1,
    "title": "Task title",
    "body": "Task description",
    "state": "open",
    "assignees": [],
    "labels": []
  },
  "repository": {
    "full_name": "org/repo"
  },
  "sender": {
    "login": "username"
  }
}
```

#### Issue Edited Event
```json
{
  "action": "edited",
  "issue": {
    "number": 1,
    "state": "open"
  },
  "changes": {
    "title": {
      "from": "Old title"
    }
  }
}
```

#### Issue Closed Event
```json
{
  "action": "closed",
  "issue": {
    "number": 1,
    "state": "closed",
    "closed_at": "2026-02-10T12:00:00Z"
  }
}
```

### 3. Verify Webhook Signature

**Python Implementation**:
```python
import hmac
import hashlib

def verify_github_signature(payload_body, signature_header, secret):
    """Verify GitHub webhook signature"""
    if not signature_header:
        return False
    
    # GitHub sends signature as "sha256=<hash>"
    hash_algorithm, github_signature = signature_header.split('=')
    
    # Calculate expected signature
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures
    return hmac.compare_digest(expected_signature, github_signature)

# Flask example
from flask import Flask, request, abort

app = Flask(__name__)

@app.route('/webhooks/github', methods=['POST'])
def github_webhook():
    # Verify signature
    signature = request.headers.get('X-Hub-Signature-256')
    if not verify_github_signature(request.data, signature, os.getenv('GITHUB_WEBHOOK_SECRET')):
        abort(401)
    
    # Process event
    event_type = request.headers.get('X-GitHub-Event')
    payload = request.json
    
    if event_type == 'issues':
        handle_issue_event(payload)
    elif event_type == 'issue_comment':
        handle_comment_event(payload)
    
    return {'status': 'ok'}, 200
```

## Rate Limiting

### Rate Limit Information

- **Authenticated requests**: 5,000 requests per hour
- **Search API**: 30 requests per minute
- **GraphQL API**: 5,000 points per hour

### Check Rate Limit Status

```python
def check_rate_limit():
    """Check current rate limit status"""
    url = "https://api.github.com/rate_limit"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json"
    }
    
    response = requests.get(url, headers=headers)
    data = response.json()
    
    core = data['resources']['core']
    print(f"Remaining: {core['remaining']}/{core['limit']}")
    print(f"Reset at: {core['reset']}")
    
    return data
```

### Handle Rate Limiting

```python
import time

def github_api_call_with_retry(func, *args, max_retries=3, **kwargs):
    """Make GitHub API call with automatic retry on rate limit"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                # Check if it's a rate limit error
                if 'rate limit' in e.response.text.lower():
                    reset_time = int(e.response.headers.get('X-RateLimit-Reset', 0))
                    sleep_time = max(reset_time - time.time(), 0) + 1
                    print(f"Rate limited. Sleeping for {sleep_time} seconds...")
                    time.sleep(sleep_time)
                    continue
            raise
    
    raise Exception(f"Failed after {max_retries} retries")
```

## GraphQL API (Alternative)

For complex queries, GraphQL API is more efficient.

### Example: Fetch Issues with Custom Fields

```python
def fetch_issues_graphql(repo_owner, repo_name, first=10):
    """Fetch issues using GraphQL API"""
    url = "https://api.github.com/graphql"
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Content-Type": "application/json"
    }
    
    query = """
    query($owner: String!, $name: String!, $first: Int!) {
      repository(owner: $owner, name: $name) {
        issues(first: $first, states: OPEN) {
          nodes {
            number
            title
            body
            state
            createdAt
            updatedAt
            assignees(first: 10) {
              nodes {
                login
              }
            }
            labels(first: 10) {
              nodes {
                name
              }
            }
          }
        }
      }
    }
    """
    
    variables = {
        "owner": repo_owner,
        "name": repo_name,
        "first": first
    }
    
    response = requests.post(
        url,
        json={"query": query, "variables": variables},
        headers=headers
    )
    response.raise_for_status()
    
    return response.json()
```

## Best Practices

1. **Use Conditional Requests**: Use ETags to avoid unnecessary data transfer
2. **Pagination**: Always handle pagination for list endpoints
3. **Webhook Security**: Always verify webhook signatures
4. **Error Handling**: Implement exponential backoff for retries
5. **Token Security**: Use environment variables, rotate tokens regularly
6. **API Versioning**: Always specify API version in headers
7. **Logging**: Log all API calls for debugging and monitoring

## Testing

### Using GitHub API in Development

```python
# Use a test repository for development
GITHUB_TEST_ORG=your-test-org
GITHUB_TEST_REPO=test-repo

# Create test issues with a special label
test_issue = create_github_issue(
    title="[TEST] Sample task",
    description="This is a test issue",
    labels=["test", "auto-generated"]
)
```

## Troubleshooting

### Common Issues

1. **401 Unauthorized**: Check token validity and permissions
2. **403 Forbidden**: Rate limit exceeded or insufficient permissions
3. **404 Not Found**: Repository/issue doesn't exist or no access
4. **422 Unprocessable Entity**: Invalid request body format

### Debug Mode

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("requests").setLevel(logging.DEBUG)
```

## Resources

- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [GitHub GraphQL API Documentation](https://docs.github.com/en/graphql)
- [GitHub Webhooks Guide](https://docs.github.com/en/webhooks)
- [PyGithub Library](https://github.com/PyGithub/PyGithub) - Python wrapper for GitHub API
