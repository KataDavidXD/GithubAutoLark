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
            platform = entities.get("platform", "").lower()
            if platform == "lark" and "collaborator" in state.get("user_command", "").lower():
                result = tools.list_lark_collaborators()
            else:
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

        elif action == "query":
            identifier = entities.get("name") or entities.get("email", "")
            time_range = entities.get("time_range", "")
            
            if identifier:
                result = tools.view_member_work(identifier)
                if time_range:
                    result = f"[Query for {time_range}]\n{result}"
            elif entities.get("team"):
                result = tools.list_members(team=entities.get("team"))
            else:
                result = tools.list_members()

        elif action == "sync":
            platform = entities.get("platform", "all").lower()
            if platform == "github":
                result = tools.fetch_github_members()
            elif platform == "lark":
                result = tools.fetch_lark_members()
            else:
                result = tools.sync_all_members()

        elif action == "bind":
            identifier = entities.get("name") or entities.get("email", "")
            github_username = entities.get("github_username")
            lark_email = entities.get("lark_email")
            lark_open_id = entities.get("lark_open_id")
            
            if not identifier:
                result = "Please specify a member name or email to bind."
            else:
                result = tools.bind_member(
                    identifier,
                    github_username=github_username,
                    lark_email=lark_email,
                    lark_open_id=lark_open_id,
                )

        elif action == "transfer_permission":
            target_name = entities.get("name", "")
            permission = entities.get("permission", "full_access")
            
            if not target_name:
                result = "Please specify a member name to transfer permission to."
            else:
                result = tools.transfer_lark_permission(target_name, permission)

        elif action == "transfer_ownership":
            target_name = entities.get("name", "")
            
            if not target_name:
                result = "Please specify a member name to transfer ownership to."
            else:
                result = tools.transfer_lark_ownership(target_name)

        elif action == "link":
            # Link two members as same person (merge identities)
            member1 = entities.get("name", "") or entities.get("member1", "")
            member2 = entities.get("github_username", "") or entities.get("member2", "")
            
            if not member1 or not member2:
                result = "Please specify two members to link (e.g., 'link Yang Li with KataDavidXD')."
            else:
                result = tools.link_members(member1, member2)

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
