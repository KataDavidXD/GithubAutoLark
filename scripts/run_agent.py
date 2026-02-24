#!/usr/bin/env python3
"""Interactive CLI for the unified GitHub-Lark agent system.

Supports both interactive (REPL) and single-command modes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(
        description="Unified GitHub-Lark Agent System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                 # Interactive mode
  %(prog)s -c "Add member Alice alice@co.com as developer"
  %(prog)s -c "Create issue 'Fix bug' label:bug"
  %(prog)s -c "List tables"
  %(prog)s -c "Sync status"
        """,
    )
    parser.add_argument("-c", "--command", type=str, help="Single command to execute")
    parser.add_argument("--no-lark", action="store_true", help="Disable Lark service")
    parser.add_argument("--no-github", action="store_true", help="Disable GitHub service")
    args = parser.parse_args()

    db, github_svc, lark_svc = _init_services(
        skip_lark=args.no_lark, skip_github=args.no_github
    )

    if args.command:
        _run_single(args.command, db, github_svc, lark_svc)
    else:
        _run_interactive(db, github_svc, lark_svc)


def _init_services(skip_lark: bool = False, skip_github: bool = False):
    from src.db.database import Database

    db = Database()
    db.init()

    github_svc = None
    if not skip_github:
        try:
            from src.services.github_service import GitHubService
            github_svc = GitHubService()
        except Exception as e:
            print(f"[warn] GitHub service unavailable: {e}")

    lark_svc = None
    if not skip_lark:
        try:
            from src.services.lark_service import LarkService
            lark_svc = LarkService()
            lark_svc.__enter__()
        except Exception as e:
            print(f"[warn] Lark service unavailable: {e}")

    return db, github_svc, lark_svc


def _run_single(command: str, db, github_svc, lark_svc):
    from src.agent.graph import run_command
    result = run_command(command, db=db, github_service=github_svc, lark_service=lark_svc)
    print(result)


def _run_interactive(db, github_svc, lark_svc):
    from src.agent.graph import run_command

    print("=" * 50)
    print("  Unified GitHub-Lark Agent System")
    print("  Type 'help' for commands, 'quit' to exit")
    print("=" * 50)
    print()

    while True:
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not command:
            continue
        if command.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break
        if command.lower() == "help":
            _print_help()
            continue

        result = run_command(
            command, db=db, github_service=github_svc, lark_service=lark_svc
        )
        print(result)
        print()


def _print_help():
    print("""
Available commands:

  Member Management:
    add member <Name> <email> as <role>
    show member <name or email>
    update member <name> role to <role>
    assign member <name> to table <table_name>
    list members [by role <role>] [by team <team>]
    show <name>'s work
    remove member <name>

  GitHub Issues:
    create issue '<title>' [assigned to <name>] [label:<label>]
    show issue #<number>
    update issue #<number> [title/body/state/assignee]
    close issue #<number>
    list issues [by <assignee>] [state open/closed]
    send issue #<number> to lark [table <name>]

  Lark Tables:
    create record '<title>' in table <name> [assigned to <name>]
    show record <record_id> [in table <name>]
    update record <record_id> [status/title/assignee]
    list records [in table <name>] [by <assignee>] [status <status>]
    list tables
    send record <record_id> to github

  Sync:
    sync pending
    sync status
    retry failed
""")


if __name__ == "__main__":
    main()
