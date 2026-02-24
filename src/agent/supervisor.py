"""Supervisor agent — LangGraph command router.

Classifies user intent via LLM and dispatches to the appropriate sub-agent.
Falls back to keyword matching if LLM is not configured.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from src.agent.state import AgentState


# ---------------------------------------------------------------------------
# Intent classification (keyword-based fallback)
# ---------------------------------------------------------------------------

_MEMBER_KEYWORDS = [
    "add member", "create member", "show member", "update member",
    "remove member", "delete member", "deactivate member", "list member",
    "assign member", "member's work", "'s work", "show work", "view work",
    "who is", "team member",
]

_GITHUB_KEYWORDS = [
    "send issue", "create issue", "open issue", "show issue", "get issue",
    "update issue", "close issue", "reopen issue", "list issue",
    "github issue", "comment on issue",
]

_LARK_KEYWORDS = [
    "send record", "create record", "create task in", "show record", "get record",
    "update record", "list record", "list table", "lark table",
    "register table", "create table",
]

_SYNC_KEYWORDS = [
    "sync pending", "sync status", "process sync", "retry failed",
    "run sync", "sync all",
]


def classify_intent_keywords(command: str) -> tuple[str, str, dict[str, Any]]:
    """
    Rule-based intent classifier (no LLM required).

    Returns: (intent, action, entities)

    Uses the *original* command for entity extraction to preserve casing.
    """
    lower = command.lower().strip()
    original = command.strip()

    # --- Member ---
    for kw in _MEMBER_KEYWORDS:
        if kw in lower:
            action = _extract_action(lower, "member")
            entities = _extract_entities_member(original)
            return ("member_management", action, entities)

    # --- GitHub ---
    for kw in _GITHUB_KEYWORDS:
        if kw in lower:
            action = _extract_action(lower, "issue")
            entities = _extract_entities_github(original)
            return ("github_issues", action, entities)

    # --- Lark ---
    for kw in _LARK_KEYWORDS:
        if kw in lower:
            action = _extract_action(lower, "record")
            entities = _extract_entities_lark(original)
            return ("lark_tables", action, entities)

    # --- Sync ---
    for kw in _SYNC_KEYWORDS:
        if kw in lower:
            return ("cross_platform_sync", "sync", {})

    return ("unknown", "unknown", {})


def _extract_action(text: str, domain: str) -> str:
    action_map = {
        "create": "create", "add": "create", "open": "create",
        "show": "read", "get": "read", "view": "read",
        "update": "update", "change": "update", "assign": "update",
        "close": "close", "delete": "delete", "remove": "delete",
        "deactivate": "delete",
        "list": "list",
        "send": "convert",
        "who": "read",
    }
    for keyword, action in action_map.items():
        if keyword in text:
            return action
    return "read"


def _extract_entities_member(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}

    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    if email_match:
        entities["email"] = email_match.group()

    # Match role keywords that appear after "as" or standalone role words
    role_match = re.search(
        r"\bas\s+(admin|manager|developer|designer|qa|member)\b", text, re.IGNORECASE
    )
    if not role_match:
        role_match = re.search(
            r"\brole\s+(?:to\s+)?(admin|manager|developer|designer|qa)\b", text, re.IGNORECASE
        )
    if role_match:
        entities["role"] = role_match.group(1).lower()

    # Extract name: word(s) after "member" that start with uppercase
    name_match = re.search(
        r"member\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text
    )
    if not name_match:
        # Fallback: possessive form like "Alice's work"
        name_match = re.search(r"(\b[A-Z][a-z]+)\s*'s\s+work", text)
    if name_match:
        entities["name"] = name_match.group(1).strip()

    return entities


def _extract_entities_github(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}

    num_match = re.search(r"#(\d+)", text)
    if num_match:
        entities["issue_number"] = int(num_match.group(1))

    title_match = re.search(r"['\"](.+?)['\"]", text)
    if title_match:
        entities["title"] = title_match.group(1)

    assignee_match = re.search(r"(?:assign(?:ed)?\s+to|by)\s+(\S+)", text, re.IGNORECASE)
    if assignee_match:
        entities["assignee"] = assignee_match.group(1)

    if "send" in text.lower() and "lark" in text.lower():
        entities["send_to_lark"] = True
        table_match = re.search(r"(?:table|to lark)\s+(\w[\w\s]*\w)", text, re.IGNORECASE)
        if table_match:
            entities["target_table"] = table_match.group(1).strip()

    label_matches = re.findall(r"label[:\s]+(\w+)", text, re.IGNORECASE)
    if label_matches:
        entities["labels"] = label_matches

    return entities


def _extract_entities_lark(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}

    title_match = re.search(r"['\"](.+?)['\"]", text)
    if title_match:
        entities["title"] = title_match.group(1)

    table_match = re.search(r"(?:in table|table)\s+(\w[\w\s]*\w)", text, re.IGNORECASE)
    if table_match:
        entities["table_name"] = table_match.group(1).strip()

    rec_match = re.search(r"(rec_\w+)", text)
    if rec_match:
        entities["record_id"] = rec_match.group(1)

    assignee_match = re.search(r"(?:assign(?:ed)?\s+to|by)\s+(\S+)", text, re.IGNORECASE)
    if assignee_match:
        entities["assignee"] = assignee_match.group(1)

    if "send" in text.lower() and "github" in text.lower():
        entities["send_to_github"] = True

    return entities


# ---------------------------------------------------------------------------
# Supervisor graph node functions
# ---------------------------------------------------------------------------

def parse_command(state: AgentState) -> dict[str, Any]:
    """Parse the user command into intent, action, and entities."""
    command = state.get("user_command", "")
    messages = list(state.get("messages", []))
    messages.append(f"Parsing command: {command}")

    intent, action, entities = classify_intent_keywords(command)

    messages.append(f"Intent: {intent}, Action: {action}")
    if entities:
        messages.append(f"Entities: {entities}")

    return {
        "intent": intent,
        "action": action,
        "entities": entities,
        "messages": messages,
    }


def route_by_intent(
    state: AgentState,
) -> Literal["member_agent", "github_agent", "lark_agent", "sync_agent", "ask_clarification"]:
    """Route to the appropriate sub-agent based on classified intent."""
    intent = state.get("intent", "unknown")
    route_map = {
        "member_management": "member_agent",
        "github_issues": "github_agent",
        "lark_tables": "lark_agent",
        "cross_platform_sync": "sync_agent",
    }
    return route_map.get(intent, "ask_clarification")


def ask_clarification(state: AgentState) -> dict[str, Any]:
    """Fallback node when intent is unclear."""
    command = state.get("user_command", "")
    return {
        "result": (
            f"I couldn't understand the command: '{command}'\n\n"
            "Available commands:\n"
            "  - Member: add/show/update/remove member, list members, show <name>'s work\n"
            "  - GitHub: create/show/update/close issue, list issues, send issue to lark\n"
            "  - Lark: create record, list records, list tables, send record to github\n"
            "  - Sync: sync pending, sync status, retry failed"
        ),
        "current_agent": "clarification",
    }


def format_response(state: AgentState) -> dict[str, Any]:
    """Final node: format the response for the user."""
    result = state.get("result", "Operation completed.")
    error = state.get("error")
    if error:
        result = f"Error: {error}"
    return {"result": result}
