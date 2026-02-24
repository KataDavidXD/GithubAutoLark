"""Member Management sub-agent node for LangGraph."""

from __future__ import annotations

from typing import Any

from src.agent.state import AgentState
from src.agent.tools.member_tools import MemberTools


def member_agent_node(state: AgentState, tools: MemberTools) -> dict[str, Any]:
    """Execute member management action based on parsed intent."""
    action = state.get("action", "")
    entities = state.get("entities", {})
    messages = list(state.get("messages", []))
    messages.append(f"Member agent: action={action}")

    result = ""

    try:
        if action == "create":
            result = tools.create_member(
                name=entities.get("name", "Unknown"),
                email=entities.get("email", ""),
                role=entities.get("role", "member"),
                position=entities.get("position"),
                team=entities.get("team"),
                github_username=entities.get("github_username"),
            )

        elif action == "read":
            identifier = (
                entities.get("email")
                or entities.get("name")
                or entities.get("identifier", "")
            )
            if "work" in state.get("user_command", "").lower():
                result = tools.view_member_work(identifier)
            else:
                result = tools.get_member(identifier)

        elif action == "update":
            identifier = entities.get("email") or entities.get("name", "")
            fields = {}
            for k in ("role", "position", "team", "github_username"):
                if k in entities:
                    fields[k] = entities[k]

            if entities.get("table_name"):
                result = tools.assign_table(identifier, entities["table_name"])
            elif fields:
                result = tools.update_member(identifier, **fields)
            else:
                result = "No fields to update. Specify role, position, team, or table."

        elif action == "delete":
            identifier = entities.get("email") or entities.get("name", "")
            result = tools.deactivate_member(identifier)

        elif action == "list":
            result = tools.list_members(
                role=entities.get("role"),
                team=entities.get("team"),
            )

        elif action == "convert":
            identifier = entities.get("email") or entities.get("name", "")
            table_name = entities.get("table_name")
            if table_name:
                result = tools.assign_table(identifier, table_name)
            else:
                result = "Specify a table name to assign."

        else:
            result = f"Unknown member action: {action}"

    except Exception as e:
        result = f"Member agent error: {e}"

    messages.append(f"Member agent result: {result[:100]}")

    return {
        "result": result,
        "current_agent": "member_agent",
        "messages": messages,
    }
