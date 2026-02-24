"""LangGraph workflow — Supervisor pattern with sub-agent routing.

This is the main graph that processes user commands:
  parse_command → route_by_intent → sub-agent → format_response → END
"""

from __future__ import annotations

from functools import partial
from typing import Any, Literal

from langgraph.graph import StateGraph, END

from src.agent.state import AgentState
from src.agent.supervisor import (
    parse_command,
    route_by_intent,
    ask_clarification,
    format_response,
)
from src.agent.member_agent import member_agent_node
from src.agent.github_agent import github_agent_node
from src.agent.lark_agent import lark_agent_node
from src.agent.sync_agent import sync_agent_node
from src.agent.tools.member_tools import MemberTools
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.lark_tools import LarkTools
from src.agent.tools.sync_tools import SyncTools
from src.db.database import Database


def build_graph(
    db: Database,
    github_service: Any = None,
    lark_service: Any = None,
) -> StateGraph:
    """
    Build the supervisor graph with injected dependencies.

    The graph uses partial() to bind tool instances into agent nodes,
    following Dependency Inversion — agents receive services at build time.
    """

    # Instantiate tool collections (bound to services)
    member_tools = MemberTools(db, lark_service=lark_service, github_service=github_service)
    github_tools = GitHubTools(db, github_service=github_service, lark_service=lark_service)
    lark_tools = LarkTools(db, lark_service=lark_service, github_service=github_service)
    sync_tools = SyncTools(db, github_service=github_service, lark_service=lark_service)

    # Bind tools into agent node functions via partial
    bound_member = partial(member_agent_node, tools=member_tools)
    bound_github = partial(github_agent_node, tools=github_tools)
    bound_lark = partial(lark_agent_node, tools=lark_tools)
    bound_sync = partial(sync_agent_node, tools=sync_tools)

    # Build graph
    graph = StateGraph(AgentState)

    graph.add_node("parse_command", parse_command)
    graph.add_node("member_agent", bound_member)
    graph.add_node("github_agent", bound_github)
    graph.add_node("lark_agent", bound_lark)
    graph.add_node("sync_agent", bound_sync)
    graph.add_node("ask_clarification", ask_clarification)
    graph.add_node("format_response", format_response)

    graph.set_entry_point("parse_command")

    graph.add_conditional_edges(
        "parse_command",
        route_by_intent,
        {
            "member_agent": "member_agent",
            "github_agent": "github_agent",
            "lark_agent": "lark_agent",
            "sync_agent": "sync_agent",
            "ask_clarification": "ask_clarification",
        },
    )

    for node in ("member_agent", "github_agent", "lark_agent", "sync_agent", "ask_clarification"):
        graph.add_edge(node, "format_response")

    graph.add_edge("format_response", END)

    return graph


def compile_graph(
    db: Database,
    github_service: Any = None,
    lark_service: Any = None,
):
    """Build and compile the supervisor graph."""
    graph = build_graph(db, github_service, lark_service)
    return graph.compile()


def run_command(
    command: str,
    db: Database,
    github_service: Any = None,
    lark_service: Any = None,
) -> str:
    """One-shot: run a single user command through the agent graph."""
    app = compile_graph(db, github_service, lark_service)
    initial_state: AgentState = {
        "user_command": command,
        "messages": [],
    }
    final_state = app.invoke(initial_state)
    return final_state.get("result", "No result.")
