"""Lark Tables sub-agent node for LangGraph."""

from __future__ import annotations

from typing import Any

from src.agent.state import AgentState
from src.agent.tools.lark_tools import LarkTools


def lark_agent_node(state: AgentState, tools: LarkTools) -> dict[str, Any]:
    """Execute Lark table action based on parsed intent."""
    action = state.get("action", "")
    entities = state.get("entities", {})
    messages = list(state.get("messages", []))
    messages.append(f"Lark agent: action={action}")

    result = ""

    try:
        if action == "create":
            result = tools.create_record(
                title=entities.get("title", "Untitled"),
                table_name=entities.get("table_name"),
                assignee=entities.get("assignee"),
                status=entities.get("status", "To Do"),
                body=entities.get("body"),
                send_to_github=entities.get("send_to_github", False),
            )

        elif action == "read":
            record_id = entities.get("record_id")
            if record_id:
                result = tools.get_record(record_id, table_name=entities.get("table_name"))
            else:
                result = "Specify a record ID."

        elif action == "update":
            record_id = entities.get("record_id")
            if not record_id:
                result = "Specify a record ID to update."
            else:
                field_updates = {}
                for k in ("status", "title", "assignee"):
                    if k in entities:
                        field_updates[k] = entities[k]
                result = tools.update_record(
                    record_id,
                    table_name=entities.get("table_name"),
                    **field_updates,
                )

        elif action == "list":
            if "table" in state.get("user_command", "").lower() and not entities.get("table_name"):
                result = tools.list_tables()
            else:
                result = tools.list_records(
                    table_name=entities.get("table_name"),
                    assignee=entities.get("assignee"),
                    status=entities.get("status"),
                )

        elif action == "convert":
            record_id = entities.get("record_id")
            if record_id:
                result = tools.send_record_to_github(
                    record_id, table_name=entities.get("table_name")
                )
            else:
                result = "Specify a record ID to convert."

        elif action == "delete":
            result = "Record deletion not yet implemented via agent."

        else:
            result = f"Unknown Lark action: {action}"

    except Exception as e:
        result = f"Lark agent error: {e}"

    messages.append(f"Lark agent result: {result[:100]}")

    return {
        "result": result,
        "current_agent": "lark_agent",
        "messages": messages,
    }
