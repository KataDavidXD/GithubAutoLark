#!/usr/bin/env python3
"""
GithubAutoLark Chat Interface
============================

A conversational interface for managing GitHub issues and Lark tasks.

Usage:
    python chat.py              # Interactive chat mode
    python chat.py --once "your message"  # Single command mode
    python chat.py --status     # Show system status

Examples:
    > What did Alice do this week?
    > Create a task for fixing the login bug
    > Show me all open issues
    > Who is on the MAS Engine team?
    > List all tables
    > Sync status
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from src.db.database import Database
from src.services.github_service import GitHubService
from src.services.lark_service import LarkService
from src.agent.enhanced_graph import chat
from src.agent.llm_supervisor import get_llm_status


class ChatApp:
    """Interactive chat application for GithubAutoLark."""
    
    def __init__(self, db_path: str = "data/chat.db"):
        self.db = Database(path=Path(db_path))
        self.db.init()
        self.github_svc = GitHubService()
        self.lark_svc = LarkService()
        self.lark_svc.use_direct_api = True
    
    def show_status(self):
        """Show system status."""
        print("\n=== GithubAutoLark System Status ===\n")
        
        # LLM Status
        llm_status = get_llm_status()
        print("LLM Configuration:")
        print(f"  Enabled: {llm_status['enabled']}")
        if llm_status['enabled']:
            print(f"  Model: {llm_status['model']}")
            print(f"  Memory turns: {llm_status['memory_turns']}")
        
        # GitHub Status
        print("\nGitHub:")
        print(f"  Repo: {self.github_svc.repo_slug}")
        
        # Lark Status
        print("\nLark:")
        print(f"  App Token: {self.lark_svc.config.app_token[:8]}...")
        
        print()
    
    def process_message(self, message: str) -> str:
        """Process a single message and return response."""
        with self.lark_svc:
            return chat(
                message,
                db=self.db,
                github_service=self.github_svc,
                lark_service=self.lark_svc,
            )
    
    def run_interactive(self):
        """Run interactive chat loop."""
        print("\n" + "=" * 60)
        print("GithubAutoLark Chat")
        print("=" * 60)
        print("Type your message in natural language.")
        print("Commands: /status, /help, /quit")
        print("=" * 60 + "\n")
        
        with self.lark_svc:
            while True:
                try:
                    user_input = input("You: ").strip()
                    
                    if not user_input:
                        continue
                    
                    # Handle special commands
                    if user_input.lower() in ("/quit", "/exit", "/q"):
                        print("Goodbye!")
                        break
                    
                    if user_input.lower() == "/status":
                        self.show_status()
                        continue
                    
                    if user_input.lower() == "/help":
                        self._show_help()
                        continue
                    
                    # Process natural language
                    response = chat(
                        user_input,
                        db=self.db,
                        github_service=self.github_svc,
                        lark_service=self.lark_svc,
                    )
                    
                    print(f"\nAssistant: {response}\n")
                    
                except KeyboardInterrupt:
                    print("\nGoodbye!")
                    break
                except Exception as e:
                    print(f"\nError: {e}\n")
    
    def _show_help(self):
        """Show help message."""
        print("""
Available Commands (Natural Language):

Members:
  - "Add member John john@example.com as developer"
  - "Show Alice's work"
  - "List all members"
  - "Who is on the MAS Engine team?"

GitHub Issues:
  - "Create issue 'Fix login bug'"
  - "Show issue #5"
  - "List open issues"
  - "Close issue #10"

Lark Tasks:
  - "Create record 'Design API' in table Tasks"
  - "List records in MAS Engine"
  - "List all tables"

Sync:
  - "Sync status"
  - "Sync pending"

Queries:
  - "What did Alice do this week?"
  - "What's the progress of MAS Engine?"
  - "Show all tasks assigned to Bob"

Special Commands:
  /status - Show system status
  /help   - Show this help
  /quit   - Exit chat
""")


def main():
    parser = argparse.ArgumentParser(
        description="GithubAutoLark Chat Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--once", "-o",
        type=str,
        help="Process a single message and exit",
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show system status",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/chat.db",
        help="Database path (default: data/chat.db)",
    )
    
    args = parser.parse_args()
    
    app = ChatApp(db_path=args.db)
    
    if args.status:
        app.show_status()
        return
    
    if args.once:
        response = app.process_message(args.once)
        print(response)
        return
    
    app.run_interactive()


if __name__ == "__main__":
    main()
