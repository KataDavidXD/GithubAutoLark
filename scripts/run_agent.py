"""
Run the LangGraph Sync Agent

The agent parses fuzzy markdown documents using LLM and syncs to GitHub/Lark.

Usage:
    python scripts/run_agent.py
    python scripts/run_agent.py --direction github_to_lark
    python scripts/run_agent.py --input /path/to/input/folder

Input folder structure:
    input/
    ├── *project*.md or *structure*.md  -> Project description
    ├── *todo*.md or *task*.md          -> Fuzzy task list (LLM parses)
    ├── *team*.md or *member*.md        -> Team info (optional)
    └── config.yaml                     -> Optional config overrides
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_demos_dir, get_repo_root
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


def main():
    parser = argparse.ArgumentParser(description="Run the GitHub-Lark sync agent")
    parser.add_argument(
        "--direction",
        choices=["github_to_lark", "lark_to_github", "bidirectional"],
        default="bidirectional",
        help="Sync direction (default: bidirectional)",
    )
    parser.add_argument(
        "--input",
        default=str(get_repo_root() / "input"),
        help="Path to input folder containing markdown docs",
    )
    parser.add_argument(
        "--save-output",
        action="store_true",
        help="Save output to demos folder",
    )
    
    args = parser.parse_args()
    
    # Capture output if saving
    capture = None
    if args.save_output:
        capture = OutputCapture()
        sys.stdout = capture
    
    try:
        run_demo(args)
    finally:
        if capture:
            sys.stdout = capture._stdout
            
            # Save redacted output
            output = capture.get_output()
            redacted = redact_text(output)
            
            demos_dir = get_demos_dir()
            demos_dir.mkdir(parents=True, exist_ok=True)
            
            output_file = demos_dir / f"agent_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(f"# Agent Run - {datetime.now().isoformat()}\n")
                f.write("# Output is REDACTED for security\n\n")
                f.write(redacted)
            
            print(f"\n[Output saved to {output_file}]")


def run_demo(args):
    print("=" * 60)
    print("LANGGRAPH SYNC AGENT")
    print("=" * 60)
    print(f"Direction: {args.direction}")
    print(f"Input folder: {args.input}")
    print()
    print("This agent parses fuzzy markdown docs using LLM and syncs to GitHub/Lark.")
    print()
    
    try:
        from src.agent.graph import run_agent
        
        result = run_agent(
            input_path=args.input,
            sync_direction=args.direction,
        )
        
        print("\n" + "-" * 40)
        print("Agent Messages:")
        print("-" * 40)
        for msg in result.get("messages", []):
            print(f"  {msg}")
        
        print("\n" + "-" * 40)
        print("Results Summary:")
        print("-" * 40)
        
        # Members
        members_std = result.get("members_standardized", [])
        print(f"\nStandardized Members ({len(members_std)}):")
        for m in members_std:
            print(f"  - {m.get('email')}: GitHub={m.get('github_username')}, Lark={m.get('lark_open_id', '')[:20]}...")
        
        # Todos aligned
        todos_aligned = result.get("todos_aligned", [])
        print(f"\nAligned Todos ({len(todos_aligned)}):")
        for t in todos_aligned:
            gh = f"#{t.get('github_issue_number')}" if t.get('github_issue_number') else "N/A"
            lark = t.get('lark_record_id', 'N/A')[:12] + "..." if t.get('lark_record_id') else "N/A"
            print(f"  - {t.get('title')[:40]}... -> GH: {gh}, Lark: {lark}")
        
        # Sync results
        synced_gh = result.get("synced_to_github", [])
        synced_lark = result.get("synced_to_lark", [])
        errors = result.get("sync_errors", [])
        
        print(f"\nSync Results:")
        print(f"  GitHub: {len(synced_gh)} synced")
        print(f"  Lark: {len(synced_lark)} synced")
        print(f"  Errors: {len(errors)}")
        
        if errors:
            print("\nErrors:")
            for err in errors:
                print(f"  - {err}")
        
        print("\n" + "=" * 60)
        print("AGENT RUN COMPLETE")
        print("=" * 60)
        
    except ImportError as e:
        print(f"\nError: LangGraph not installed. Run: pip install langgraph langchain-core")
        print(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError running agent: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
