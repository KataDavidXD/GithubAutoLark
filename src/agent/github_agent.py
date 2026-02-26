"""GitHub Issues sub-agent node for LangGraph."""

from __future__ import annotations

from typing import Any

from src.agent.state import AgentState
from src.agent.tools.github_tools import GitHubTools


def github_agent_node(state: AgentState, tools: GitHubTools) -> dict[str, Any]:
    """Execute GitHub issue action based on parsed intent."""
    action = state.get("action", "")
    entities = state.get("entities", {})
    messages = list(state.get("messages", []))
    messages.append(f"GitHub agent: action={action}")

    result = ""

    try:
        if action == "create":
            result = tools.create_issue(
                title=entities.get("title", "Untitled Issue"),
                body=entities.get("body", ""),
                assignee=entities.get("assignee"),
                labels=entities.get("labels"),
                send_to_lark=entities.get("send_to_lark", False),
                target_table=entities.get("target_table"),
            )

        elif action == "read":
            issue_number = entities.get("issue_number")
            if issue_number:
                result = tools.get_issue(issue_number)
            else:
                result = "Specify an issue number (e.g., #42)."

        elif action == "update":
            issue_number = entities.get("issue_number")
            if not issue_number:
                result = "Specify an issue number to update."
            else:
                result = tools.update_issue(
                    issue_number,
                    title=entities.get("title"),
                    body=entities.get("body"),
                    state=entities.get("state"),
                    assignee=entities.get("assignee"),
                    labels=entities.get("labels"),
                )

        elif action == "close":
            issue_number = entities.get("issue_number") or entities.get("issue_numbers")
            if issue_number:
                result = tools.close_issue(issue_number)
            else:
                result = "Specify an issue number to close."

        elif action == "reopen":
            issue_number = entities.get("issue_number") or entities.get("issue_numbers")
            if issue_number:
                result = tools.reopen_issue(issue_number)
            else:
                result = "Specify an issue number to reopen."

        elif action == "list":
            result = tools.list_issues(
                state=entities.get("state", "open"),
                assignee=entities.get("assignee"),
                labels=entities.get("labels_str"),
            )

        elif action == "convert":
            issue_number = entities.get("issue_number")
            if issue_number:
                result = tools.send_issue_to_lark(
                    issue_number,
                    target_table=entities.get("target_table"),
                )
            else:
                result = "Specify an issue number to convert."

        else:
            result = f"Unknown GitHub action: {action}"

    except Exception as e:
        result = f"GitHub agent error: {e}"

    messages.append(f"GitHub agent result: {result[:100]}")

    return {
        "result": result,
        "current_agent": "github_agent",
        "messages": messages,
    }
