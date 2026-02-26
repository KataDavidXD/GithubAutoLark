# GitHub Issue API Operations Documentation

This document details the tested operations for the GitHub Issues API. All tests were performed using the repository `KataDavidXD/GithubAutoLark`.

## Environment Setup
- **Base URL**: `https://api.github.com/repos/{OWNER}/{REPO}`
- **Authentication**: Bearer Token (`Authorization: Bearer <GITHUB_TOKEN>`)
- **API Version**: `2022-11-28`
- **Accept Header**: `application/vnd.github+json`

## Tested Operations

| Operation | HTTP Method | Endpoint | Description | Status Code (Success) |
| :--- | :--- | :--- | :--- | :--- |
| **Create Issue** | `POST` | `/issues` | Creates a new issue with title, body, and labels. | `201 Created` |
| **Get Issue** | `GET` | `/issues/{issue_number}` | Retrieves details of a specific issue. | `200 OK` |
| **Update Issue** | `PATCH` | `/issues/{issue_number}` | Updates issue details (e.g., body, labels). | `200 OK` |
| **Create Comment** | `POST` | `/issues/{issue_number}/comments` | Adds a comment to an issue. | `201 Created` |
| **List Comments** | `GET` | `/issues/{issue_number}/comments` | Lists all comments on an issue. | `200 OK` |
| **Close Issue** | `PATCH` | `/issues/{issue_number}` | Closes an issue by setting `state` to `closed`. | `200 OK` |

## Example Usage (Python/Requests)

### 1. Create Issue
```python
url = f"{BASE_URL}/issues"
data = {
    "title": "Issue Title",
    "body": "Issue Body",
    "labels": ["bug"]
}
response = requests.post(url, headers=HEADERS, json=data)
```

### 2. Update Issue
```python
url = f"{BASE_URL}/issues/{issue_number}"
data = {
    "body": "Updated Body",
    "labels": ["bug", "updated"]
}
response = requests.patch(url, headers=HEADERS, json=data)
```

### 3. Create Comment
```python
url = f"{BASE_URL}/issues/{issue_number}/comments"
data = {
    "body": "Comment text"
}
response = requests.post(url, headers=HEADERS, json=data)
```

### 4. Close Issue
```python
url = f"{BASE_URL}/issues/{issue_number}"
data = {
    "state": "closed",
    "state_reason": "completed"
}
response = requests.patch(url, headers=HEADERS, json=data)
```

## Test Results
A full lifecycle test was executed successfully:
1. Created Issue #3
2. Verified Issue #3 details
3. Updated Issue #3 body and labels
4. Added a comment to Issue #3
5. Listed comments for Issue #3
6. Closed Issue #3

All operations returned expected success status codes (200/201).
