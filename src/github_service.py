"""
GitHub Service - GitHub Issues API client.

All operations use the REST API with requests library.
Credentials come from environment via src/config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from src.config import get_github_config, GitHubConfig


@dataclass
class GitHubService:
    """
    GitHub Issues API client.
    
    Usage:
        svc = GitHubService()
        issue = svc.create_issue("Title", "Body", labels=["bug"])
        svc.close_issue(issue["number"])
    """
    
    config: GitHubConfig
    
    def __init__(self, config: Optional[GitHubConfig] = None):
        self.config = config or get_github_config()
    
    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    
    def _url(self, path: str) -> str:
        return f"{self.config.base_url}{path}"
    
    # -------------------------------------------------------------------------
    # Issue Operations
    # -------------------------------------------------------------------------
    
    def create_issue(
        self,
        title: str,
        body: str = "",
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Create a new issue.
        
        Returns the created issue object (contains 'number', 'html_url', etc.).
        """
        data: dict[str, Any] = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        if assignees:
            data["assignees"] = assignees
        
        resp = requests.post(self._url("/issues"), headers=self._headers, json=data)
        resp.raise_for_status()
        return resp.json()
    
    def get_issue(self, issue_number: int) -> dict[str, Any]:
        """Get a single issue by number."""
        resp = requests.get(self._url(f"/issues/{issue_number}"), headers=self._headers)
        resp.raise_for_status()
        return resp.json()
    
    def update_issue(
        self,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        state_reason: Optional[str] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Update an existing issue.
        
        state can be 'open' or 'closed'.
        state_reason can be 'completed', 'not_planned', or 'reopened'.
        """
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if state is not None:
            data["state"] = state
        if state_reason is not None:
            data["state_reason"] = state_reason
        if labels is not None:
            data["labels"] = labels
        if assignees is not None:
            data["assignees"] = assignees
        
        resp = requests.patch(self._url(f"/issues/{issue_number}"), headers=self._headers, json=data)
        resp.raise_for_status()
        return resp.json()
    
    def close_issue(self, issue_number: int, reason: str = "completed") -> dict[str, Any]:
        """Close an issue."""
        return self.update_issue(issue_number, state="closed", state_reason=reason)
    
    def reopen_issue(self, issue_number: int) -> dict[str, Any]:
        """Reopen a closed issue."""
        return self.update_issue(issue_number, state="open", state_reason="reopened")
    
    # -------------------------------------------------------------------------
    # Comment Operations
    # -------------------------------------------------------------------------
    
    def create_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        resp = requests.post(
            self._url(f"/issues/{issue_number}/comments"),
            headers=self._headers,
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()
    
    def list_comments(self, issue_number: int) -> list[dict[str, Any]]:
        """List all comments on an issue."""
        resp = requests.get(self._url(f"/issues/{issue_number}/comments"), headers=self._headers)
        resp.raise_for_status()
        return resp.json()
    
    # -------------------------------------------------------------------------
    # List/Search
    # -------------------------------------------------------------------------
    
    def list_issues(
        self,
        state: str = "all",
        labels: Optional[str] = None,
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """
        List issues in the repository.
        
        state: 'open', 'closed', or 'all'
        labels: comma-separated label names
        """
        params: dict[str, Any] = {"state": state, "per_page": per_page, "page": page}
        if labels:
            params["labels"] = labels
        
        resp = requests.get(self._url("/issues"), headers=self._headers, params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------
_default_service: Optional[GitHubService] = None


def get_service() -> GitHubService:
    global _default_service
    if _default_service is None:
        _default_service = GitHubService()
    return _default_service


if __name__ == "__main__":
    # Quick connectivity test
    svc = GitHubService()
    print(f"GitHub service configured for: {svc.config.owner}/{svc.config.repo}")
    print("Listing recent issues...")
    issues = svc.list_issues(state="all", per_page=5)
    for iss in issues:
        print(f"  #{iss['number']}: {iss['title']} [{iss['state']}]")
