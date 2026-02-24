"""
GitHub Lifecycle Demo Script

This script demonstrates the full GitHub Issues lifecycle:
1. Create Issue
2. Get Issue (Read)
3. Update Issue (body, labels)
4. Create Comment
5. List Comments
6. Close Issue

Output is saved (redacted) to demos/github_lifecycle_output.txt
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_github_config, get_demos_dir
from src.github_service import GitHubService
from src.redact import redact_text


class OutputCapture:
    """Capture print output for saving to file."""
    
    def __init__(self):
        self.buffer = StringIO()
        self._stdout = sys.stdout
    
    def write(self, text: str) -> None:
        self._stdout.write(text)
        self.buffer.write(text)
    
    def flush(self) -> None:
        self._stdout.flush()
    
    def get_output(self) -> str:
        return self.buffer.getvalue()


def main() -> None:
    capture = OutputCapture()
    sys.stdout = capture
    
    try:
        run_demo()
    finally:
        sys.stdout = capture._stdout
        
        # Save redacted output
        output = capture.get_output()
        redacted = redact_text(output)
        
        demos_dir = get_demos_dir()
        demos_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = demos_dir / "github_lifecycle_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# GitHub Lifecycle Demo - {datetime.now().isoformat()}\n")
            f.write("# Output is REDACTED for security\n\n")
            f.write(redacted)
        
        print(f"\n[Output saved to {output_file}]")


def run_demo() -> None:
    config = get_github_config()
    svc = GitHubService(config)
    
    print("=" * 60)
    print("GITHUB LIFECYCLE DEMO")
    print("=" * 60)
    print(f"Repository: {config.owner}/{config.repo}")
    print(f"Base URL: {config.base_url}")
    print()
    
    issue_number = None
    
    try:
        # -----------------------------------------------------------------
        # Step 1: Create Issue
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 1: Create Issue")
        print("-" * 40)
        
        title = f"[DEMO] Lifecycle Test {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        body = (
            "This is a test issue created by the GitHub lifecycle demo script.\n\n"
            "Testing: Create -> Read -> Update -> Comment -> Close\n\n"
            "- Created by: demo_github_lifecycle.py"
        )
        labels = ["test", "demo"]
        
        print(f"Creating issue: {title}")
        issue = svc.create_issue(title, body, labels=labels)
        issue_number = issue["number"]
        
        print(f"Created Issue #{issue_number}")
        print(f"  URL: {issue['html_url']}")
        print(f"  State: {issue['state']}")
        print(f"  Labels: {[l['name'] for l in issue.get('labels', [])]}")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 2: Get Issue (Read)
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 2: Get Issue (Read)")
        print("-" * 40)
        
        issue = svc.get_issue(issue_number)
        print(f"Retrieved Issue #{issue_number}")
        print(f"  Title: {issue['title']}")
        print(f"  State: {issue['state']}")
        print(f"  Created: {issue['created_at']}")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 3: Update Issue
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 3: Update Issue (body, labels)")
        print("-" * 40)
        
        updated_body = body + "\n\n**Updated:** This body was modified by the demo script."
        updated_labels = ["test", "demo", "updated"]
        
        issue = svc.update_issue(
            issue_number,
            body=updated_body,
            labels=updated_labels,
        )
        
        print(f"Updated Issue #{issue_number}")
        print(f"  Labels: {[l['name'] for l in issue.get('labels', [])]}")
        print(f"  Updated at: {issue['updated_at']}")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 4: Create Comment
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 4: Create Comment")
        print("-" * 40)
        
        comment_body = (
            "This is a test comment added by the demo script.\n\n"
            f"Timestamp: {datetime.now().isoformat()}"
        )
        
        comment = svc.create_comment(issue_number, comment_body)
        print(f"Created Comment #{comment['id']}")
        print(f"  URL: {comment['html_url']}")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 5: List Comments
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 5: List Comments")
        print("-" * 40)
        
        comments = svc.list_comments(issue_number)
        print(f"Found {len(comments)} comment(s):")
        for c in comments:
            print(f"  - #{c['id']}: {c['body'][:50]}...")
        print()
        time.sleep(1)
        
        # -----------------------------------------------------------------
        # Step 6: Close Issue
        # -----------------------------------------------------------------
        print("-" * 40)
        print("Step 6: Close Issue")
        print("-" * 40)
        
        issue = svc.close_issue(issue_number, reason="completed")
        print(f"Closed Issue #{issue_number}")
        print(f"  State: {issue['state']}")
        print(f"  State Reason: {issue.get('state_reason', 'N/A')}")
        print()
        
        print("=" * 60)
        print("GITHUB LIFECYCLE DEMO COMPLETE")
        print("=" * 60)
        print(f"Final Issue URL: {issue['html_url']}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        
        # Try to clean up by closing the issue
        if issue_number:
            try:
                print(f"Attempting to close issue #{issue_number}...")
                svc.close_issue(issue_number, reason="not_planned")
            except Exception:
                pass
        
        raise


if __name__ == "__main__":
    main()
