"""
LangGraph Agent - Workflow graph for GitHub-Lark sync.

This module defines the agent graph with nodes for:
1. Loading input files (project, members, todos)
2. Loading existing data (GitHub issues, Lark records, SQLite tasks)
3. Standardizing members across platforms
4. Aligning todos with existing data
5. Bidirectional sync (GitHub <-> Lark)
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import StateGraph, END

from src.agent.state import AgentState
from src.agent.nodes import (
    load_input_files,
    parse_with_llm,
    load_existing_data,
    standardize_members,
    align_todos,
    sync_github_to_lark,
    sync_lark_to_github,
    finalize,
)


def create_sync_agent() -> StateGraph:
    """
    Create the LangGraph agent for GitHub-Lark sync.
    
    Graph structure:
    
    ┌─────────────────┐
    │ load_input_files │  <- Load markdown docs from input/
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  parse_with_llm  │  <- LLM extracts structured todos from fuzzy docs
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │load_existing_data│  <- Load existing GitHub/Lark/SQLite data
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │standardize_members│  <- Resolve email -> Lark open_id
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   align_todos    │  <- Match todos with existing issues/records
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │ decide_direction │ ─── Router (github_to_lark / lark_to_github / bidirectional)
    └────────┬────────┘
             │
     ┌───────┴───────┐
     ▼               ▼
    ┌─────────┐  ┌─────────┐
    │lark2gh  │  │gh2lark  │
    └────┬────┘  └────┬────┘
         │            │
         └──────┬─────┘
                │
    ┌───────────▼───────────┐
    │       finalize        │
    └───────────┬───────────┘
                │
               END
    """
    
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("load_input_files", load_input_files)
    workflow.add_node("parse_with_llm", parse_with_llm)
    workflow.add_node("load_existing_data", load_existing_data)
    workflow.add_node("standardize_members", standardize_members)
    workflow.add_node("align_todos", align_todos)
    workflow.add_node("sync_lark_to_github", sync_lark_to_github)
    workflow.add_node("sync_github_to_lark", sync_github_to_lark)
    workflow.add_node("finalize", finalize)
    
    # Define the flow
    workflow.set_entry_point("load_input_files")
    
    workflow.add_edge("load_input_files", "parse_with_llm")
    workflow.add_edge("parse_with_llm", "load_existing_data")
    workflow.add_edge("load_existing_data", "standardize_members")
    workflow.add_edge("standardize_members", "align_todos")
    
    # Conditional routing based on sync direction
    def route_sync(state: AgentState) -> Literal["sync_lark_to_github", "sync_github_to_lark"]:
        direction = state.get("sync_direction", "bidirectional")
        project = state.get("project", {})
        
        if project:
            sync_config = project.get("sync", {})
            direction = sync_config.get("direction", direction)
        
        if direction == "github_to_lark":
            return "sync_github_to_lark"
        else:
            # For bidirectional or lark_to_github, start with lark_to_github
            return "sync_lark_to_github"
    
    workflow.add_conditional_edges(
        "align_todos",
        route_sync,
        {
            "sync_lark_to_github": "sync_lark_to_github",
            "sync_github_to_lark": "sync_github_to_lark",
        }
    )
    
    # After first sync, check if bidirectional
    def route_after_lark_sync(state: AgentState) -> Literal["sync_github_to_lark", "finalize"]:
        direction = state.get("sync_direction", "bidirectional")
        project = state.get("project", {})
        
        if project:
            sync_config = project.get("sync", {})
            direction = sync_config.get("direction", direction)
        
        if direction == "bidirectional":
            return "sync_github_to_lark"
        else:
            return "finalize"
    
    workflow.add_conditional_edges(
        "sync_lark_to_github",
        route_after_lark_sync,
        {
            "sync_github_to_lark": "sync_github_to_lark",
            "finalize": "finalize",
        }
    )
    
    def route_after_github_sync(state: AgentState) -> Literal["sync_lark_to_github", "finalize"]:
        direction = state.get("sync_direction", "bidirectional")
        project = state.get("project", {})
        
        if project:
            sync_config = project.get("sync", {})
            direction = sync_config.get("direction", direction)
        
        # If we started with github_to_lark and it's bidirectional, now do lark_to_github
        # But if we already did lark_to_github (came from that node), go to finalize
        current_node = state.get("current_node", "")
        
        if direction == "bidirectional" and current_node == "sync_github_to_lark":
            # Check if we already did lark sync (by checking synced_to_lark)
            if not state.get("synced_to_lark"):
                # We came directly here, need to sync back
                return "sync_lark_to_github"
        
        return "finalize"
    
    workflow.add_conditional_edges(
        "sync_github_to_lark",
        route_after_github_sync,
        {
            "sync_lark_to_github": "sync_lark_to_github",
            "finalize": "finalize",
        }
    )
    
    # Final edge
    workflow.add_edge("finalize", END)
    
    return workflow


def compile_agent():
    """Compile the agent graph."""
    workflow = create_sync_agent()
    return workflow.compile()


def run_agent(
    input_path: str = None,
    sync_direction: str = "bidirectional",
) -> dict[str, Any]:
    """
    Run the sync agent.
    
    The agent loads markdown documents from input_path:
    - *project*.md or *structure*.md -> project description
    - *todo*.md or *task*.md -> fuzzy task list (LLM will parse)
    - *team*.md or *member*.md -> team info (optional)
    - config.yaml -> optional overrides
    
    Args:
        input_path: Path to input folder (default: ./input)
        sync_direction: 'github_to_lark', 'lark_to_github', or 'bidirectional'
    
    Returns:
        Final agent state with sync results
    """
    app = compile_agent()
    
    initial_state: AgentState = {
        "messages": [],
        "sync_direction": sync_direction,  # type: ignore
    }
    
    if input_path:
        initial_state["input_path"] = input_path
    
    # Run the graph
    result = app.invoke(initial_state)
    
    return result


if __name__ == "__main__":
    print("Testing LangGraph agent...")
    result = run_agent()
    
    print("\nMessages:")
    for msg in result.get("messages", []):
        print(f"  {msg}")
