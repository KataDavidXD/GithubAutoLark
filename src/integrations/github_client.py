"""
GitHub API client
"""
import requests
import time
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
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 403 and 'rate limit' in e.response.text.lower():
                        reset_time = int(e.response.headers.get('X-RateLimit-Reset', 0))
                        sleep_time = max(reset_time - time.time(), 0) + 1
                        logger.warning(f"Rate limited. Sleeping for {sleep_time} seconds...")
                        time.sleep(sleep_time)
                        continue
                    elif attempt == max_retries - 1:
                        raise
                    else:
                        sleep_time = backoff_factor ** attempt
                        logger.warning(f"Request failed. Retry {attempt + 1}/{max_retries} after {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    sleep_time = backoff_factor ** attempt
                    logger.warning(f"Request failed: {e}. Retry {attempt + 1}/{max_retries} after {sleep_time}s...")
                    time.sleep(sleep_time)
            
            raise Exception(f"Failed after {max_retries} retries")
        return wrapper
    return decorator


class GitHubClient:
    """GitHub API client"""
    
    def __init__(self, token: Optional[str] = None, org: Optional[str] = None, repo: Optional[str] = None):
        self.token = token or settings.GITHUB_TOKEN
        self.org = org or settings.GITHUB_ORG
        self.repo = repo or settings.GITHUB_REPO
        self.base_url = settings.GITHUB_API_BASE_URL
        
        if not self.token:
            raise ValueError("GitHub token is required")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def create_issue(
        self,
        title: str,
        body: Optional[str] = None,
        assignees: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
        milestone: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a GitHub issue"""
        if not self.org or not self.repo:
            raise ValueError("GitHub org and repo must be set")
        
        url = f"{self.base_url}/repos/{self.org}/{self.repo}/issues"
        
        payload = {"title": title}
        if body:
            payload["body"] = body
        if assignees:
            payload["assignees"] = assignees
        if labels:
            payload["labels"] = labels
        if milestone:
            payload["milestone"] = milestone
        
        logger.info(f"Creating GitHub issue: {title}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"Created issue #{data['number']}: {data['html_url']}")
        return data
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def update_issue(
        self,
        issue_number: int,
        state: Optional[str] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Update a GitHub issue"""
        if not self.org or not self.repo:
            raise ValueError("GitHub org and repo must be set")
        
        url = f"{self.base_url}/repos/{self.org}/{self.repo}/issues/{issue_number}"
        
        payload = {}
        if state:
            payload["state"] = state
        if title:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees
        
        logger.info(f"Updating GitHub issue #{issue_number}")
        response = requests.patch(url, json=payload, headers=self._get_headers())
        response.raise_for_status()
        
        return response.json()
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """Get a specific GitHub issue"""
        if not self.org or not self.repo:
            raise ValueError("GitHub org and repo must be set")
        
        url = f"{self.base_url}/repos/{self.org}/{self.repo}/issues/{issue_number}"
        
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        
        return response.json()
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def list_issues(
        self,
        state: str = "open",
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        per_page: int = 30,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """List GitHub issues"""
        if not self.org or not self.repo:
            raise ValueError("GitHub org and repo must be set")
        
        url = f"{self.base_url}/repos/{self.org}/{self.repo}/issues"
        
        params = {"state": state, "per_page": per_page, "page": page}
        if labels:
            params["labels"] = ",".join(labels)
        if assignee:
            params["assignee"] = assignee
        
        response = requests.get(url, params=params, headers=self._get_headers())
        response.raise_for_status()
        
        return response.json()
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def add_comment(self, issue_number: int, body: str) -> Dict[str, Any]:
        """Add a comment to an issue"""
        if not self.org or not self.repo:
            raise ValueError("GitHub org and repo must be set")
        
        url = f"{self.base_url}/repos/{self.org}/{self.repo}/issues/{issue_number}/comments"
        
        payload = {"body": body}
        
        logger.info(f"Adding comment to issue #{issue_number}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        response.raise_for_status()
        
        return response.json()
    
    @retry_on_failure(max_retries=3, backoff_factor=2)
    def close_issue(self, issue_number: int, state_reason: str = "completed") -> Dict[str, Any]:
        """Close a GitHub issue"""
        return self.update_issue(
            issue_number,
            state="closed",
            # Note: state_reason requires the issues API preview
        )
    
    def check_rate_limit(self) -> Dict[str, Any]:
        """Check current rate limit status"""
        url = f"{self.base_url}/rate_limit"
        
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        
        data = response.json()
        core = data['resources']['core']
        logger.info(f"Rate limit: {core['remaining']}/{core['limit']} remaining")
        
        return data
