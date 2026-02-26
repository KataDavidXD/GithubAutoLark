"""Unified Tool Registry — Maps tool names to actual method calls.

All 38 tool methods from the four tool classes are registered here
under short, LLM-friendly names.  The executor calls
``registry.execute(tool_name, params)`` for each step in the plan.
"""

from __future__ import annotations

from typing import Any, Callable

from src.db.database import Database
from src.agent.tools.member_tools import MemberTools
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.lark_tools import LarkTools
from src.agent.tools.sync_tools import SyncTools


class ToolRegistry:
    """Holds all tool instances and dispatches by name."""

    def __init__(
        self,
        db: Database,
        github_service: Any = None,
        lark_service: Any = None,
    ):
        self.member = MemberTools(db, lark_service=lark_service, github_service=github_service)
        self.github = GitHubTools(db, github_service=github_service, lark_service=lark_service)
        self.lark = LarkTools(db, lark_service=lark_service, github_service=github_service)
        self.sync = SyncTools(db, github_service=github_service, lark_service=lark_service)

        self._dispatch: dict[str, Callable[..., str]] = {
            # ── Members ──────────────────────────────────────────
            "list_members":             self.member.list_members,
            "get_member":               self.member.get_member,
            "create_member":            self.member.create_member,
            "update_member":            self.member.update_member,
            "deactivate_member":        self.member.deactivate_member,
            "fetch_github_members":     self.member.fetch_github_members,
            "fetch_lark_members":       self.member.fetch_lark_members,
            "sync_all_members":         self.member.sync_all_members,
            "link_members":             self._link_members,
            "bind_member":              self.member.bind_member,
            "view_member_work":         self._view_member_work,
            "assign_table":             self.member.assign_table,
            "transfer_lark_permission": self.member.transfer_lark_permission,
            "transfer_lark_ownership":  self.member.transfer_lark_ownership,
            "list_lark_collaborators":  self.member.list_lark_collaborators,

            # ── GitHub ───────────────────────────────────────────
            "list_issues":              self.github.list_issues,
            "get_issue":                self.github.get_issue,
            "create_issue":             self._create_issue,
            "update_issue":             self.github.update_issue,
            "assign_issue":             self.github.assign_issue,
            "close_issue":              self._close_issue,
            "reopen_issue":             self._reopen_issue,
            "send_issue_to_lark":       self.github.send_issue_to_lark,

            # ── Lark ────────────────────────────────────────────
            "list_tables":              self.lark.list_tables,
            "list_records":             self.lark.list_records,
            "get_record":               self.lark.get_record,
            "create_record":            self.lark.create_record,
            "update_record":            self.lark.update_record,
            "create_task_table":        self.lark.create_task_table,
            "create_team_table":        self.lark.create_team_table,
            "create_tasks_batch":       self.lark.create_tasks_batch,
            "register_table":           self.lark.register_table,
            "send_record_to_github":    self.lark.send_record_to_github,
            "add_member_to_table":      self.lark.add_member_to_table,

            # ── Sync ────────────────────────────────────────────
            "sync_status":              self.sync.sync_status,
            "sync_pending":             self.sync.sync_pending,
            "retry_failed":             self.sync.retry_failed,
        }

    # Thin adapters that normalize param names the LLM might use
    def _link_members(self, name1: str = "", name2: str = "", **kw: Any) -> str:
        n1 = name1 or kw.get("member1", "")
        n2 = name2 or kw.get("member2", "")
        return self.member.link_members(n1, n2)

    def _view_member_work(self, identifier: str = "", name: str = "", **kw: Any) -> str:
        who = identifier or name or kw.get("member", "")
        return self.member.view_member_work(who)

    def _create_issue(self, title: str = "", assignee: str = "", **kw: Any) -> str:
        who = assignee or kw.get("assign_to", "") or kw.get("assignees", "")
        if isinstance(who, list):
            who = who[0] if who else ""
        return self.github.create_issue(title=title, assignee=who or None, **{
            k: v for k, v in kw.items() if k in ("body", "labels", "send_to_lark", "target_table")
        })

    def _close_issue(self, issue_number=None, **kw: Any) -> str:
        val = issue_number if issue_number is not None else kw.get("issues", kw.get("numbers", kw.get("issue_numbers", None)))
        if val is None:
            return "Error: No issue number provided for close_issue."
        return self.github.close_issue(val)

    def _reopen_issue(self, issue_number=None, **kw: Any) -> str:
        val = issue_number if issue_number is not None else kw.get("issues", kw.get("numbers", kw.get("issue_numbers", None)))
        if val is None:
            return "Error: No issue number provided for reopen_issue."
        return self.github.reopen_issue(val)

    # ── Public API ──────────────────────────────────────────────

    def execute(self, tool_name: str, params: dict[str, Any]) -> str:
        """Look up *tool_name* and call it with *params*.  Returns a result string."""
        fn = self._dispatch.get(tool_name)
        if fn is None:
            return f"Unknown tool: '{tool_name}'. Available: {', '.join(sorted(self._dispatch))}"
        try:
            return fn(**params)
        except TypeError as e:
            return f"Tool '{tool_name}' parameter error: {e}"
        except Exception as e:
            return f"Tool '{tool_name}' failed: {e}"

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._dispatch.keys())
