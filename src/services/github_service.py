"""GitHub Issues REST API service — enhanced with member-aware operations.

Follows Interface Segregation: only exposes issue-related methods.
Depends on config abstraction (Dependency Inversion).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from src.config import get_github_config, GitHubConfig


@dataclass
class GitHubService:
    """GitHub Issues API client with member-aware operations."""

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

    @property
    def repo_slug(self) -> str:
        return f"{self.config.owner}/{self.config.repo}"

    # -- Issue CRUD ------------------------------------------------------------

    def create_issue(
        self,
        title: str,
        body: str = "",
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        if assignees:
            data["assignees"] = assignees
        resp = requests.post(self._url("/issues"), headers=self._headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def get_issue(self, issue_number: int) -> dict[str, Any]:
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

        resp = requests.patch(
            self._url(f"/issues/{issue_number}"), headers=self._headers, json=data
        )
        resp.raise_for_status()
        return resp.json()

    def close_issue(self, issue_number: int, reason: str = "completed") -> dict[str, Any]:
        return self.update_issue(issue_number, state="closed", state_reason=reason)

    def reopen_issue(self, issue_number: int) -> dict[str, Any]:
        return self.update_issue(issue_number, state="open", state_reason="reopened")

    # -- Comments --------------------------------------------------------------

    def create_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        resp = requests.post(
            self._url(f"/issues/{issue_number}/comments"),
            headers=self._headers,
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()

    def list_comments(self, issue_number: int) -> list[dict[str, Any]]:
        resp = requests.get(
            self._url(f"/issues/{issue_number}/comments"), headers=self._headers
        )
        resp.raise_for_status()
        return resp.json()

    # -- List / Search ---------------------------------------------------------

    def list_issues(
        self,
        state: str = "all",
        labels: Optional[str] = None,
        assignee: Optional[str] = None,
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"state": state, "per_page": per_page, "page": page}
        if labels:
            params["labels"] = labels
        if assignee:
            params["assignee"] = assignee
        resp = requests.get(self._url("/issues"), headers=self._headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def list_issues_by_assignee(
        self, username: str, state: str = "all"
    ) -> list[dict[str, Any]]:
        return self.list_issues(state=state, assignee=username)

    def search_issues(self, query: str) -> list[dict[str, Any]]:
        """Use the GitHub search API for complex queries."""
        url = "https://api.github.com/search/issues"
        full_query = f"repo:{self.config.owner}/{self.config.repo} {query}"
        resp = requests.get(
            url, headers=self._headers, params={"q": full_query, "per_page": 50}
        )
        resp.raise_for_status()
        return resp.json().get("items", [])

    # -- Organization / Collaborator management --------------------------------

    def list_repo_collaborators(self, per_page: int = 100) -> list[dict[str, Any]]:
        """List all collaborators of the repository."""
        resp = requests.get(
            self._url("/collaborators"),
            headers=self._headers,
            params={"per_page": per_page},
        )
        resp.raise_for_status()
        return resp.json()

    def list_org_members(self, org: Optional[str] = None, per_page: int = 100) -> list[dict[str, Any]]:
        """List members of an organization.
        
        Note: Requires organization membership or admin access.
        """
        org_name = org or self.config.owner
        url = f"https://api.github.com/orgs/{org_name}/members"
        resp = requests.get(
            url,
            headers=self._headers,
            params={"per_page": per_page},
        )
        resp.raise_for_status()
        return resp.json()

    def get_user(self, username: str) -> dict[str, Any]:
        """Get details of a GitHub user."""
        url = f"https://api.github.com/users/{username}"
        resp = requests.get(url, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def get_authenticated_user(self) -> dict[str, Any]:
        """Get the authenticated user's info."""
        url = "https://api.github.com/user"
        resp = requests.get(url, headers=self._headers)
        resp.raise_for_status()
        return resp.json()
