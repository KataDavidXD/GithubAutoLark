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

        elif action == "create_table":
            table_name = entities.get("table_name") or entities.get("title", "Team")
            table_type = entities.get("table_type", "")
            add_members = entities.get("add_members", False)
            tasks = entities.get("tasks", [])
            
            # Determine table type based on context
            # If tasks are provided -> task table
            # If add_members is True and no tasks -> team/member roster table
            # If table_type is explicitly "task" -> task table
            # If table_type is explicitly "team" or "member" -> team table
            
            if tasks:
                # Has task assignments -> create task table with tasks
                result = tools.create_task_table(table_name, tasks=tasks)
            elif table_type in ("task", "tasks"):
                # Explicitly a task table
                result = tools.create_task_table(table_name)
            elif table_type in ("team", "member", "members") or add_members:
                # Explicitly a team/member roster
                result = tools.create_team_table(table_name, add_all_members=add_members)
            else:
                # Default: if name suggests tasks, create task table
                lower_name = table_name.lower()
                if any(kw in lower_name for kw in ["task", "sprint", "project", "work"]):
                    result = tools.create_task_table(table_name)
                else:
                    # Otherwise create task table (most common use case)
                    result = tools.create_task_table(table_name)

        elif action == "create_tasks":
            table_name = entities.get("table_name", "")
            tasks = entities.get("tasks", [])
            if tasks and table_name:
                result = tools.create_tasks_batch(tasks, table_name)
            else:
                result = "Specify table_name and tasks list."

        elif action == "add_member":
            member_name = entities.get("name") or entities.get("assignee", "")
            table_name = entities.get("table_name", "")
            if member_name and table_name:
                result = tools.add_member_to_table(member_name, table_name)
            else:
                result = "Specify both member name and table name."

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
