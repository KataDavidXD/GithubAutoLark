# GithubAutoLark Project Structure

## Overview

This is a bidirectional sync system between GitHub Issues and Lark Bitable.

## Tech Stack

- **Language**: Python 3.10+
- **Database**: SQLite (local state)
- **APIs**: GitHub REST API, Lark MCP
- **Agent Framework**: LangGraph

## Module Structure

```
src/
├── config.py          # Environment config loader
├── db.py              # SQLite database layer
├── github_service.py  # GitHub API client
├── lark_service.py    # Lark Bitable operations
├── mcp_client.py      # Lark MCP JSON-RPC client
├── sync_engine.py     # Sync orchestration
└── agent/             # LangGraph agent
    ├── graph.py       # Workflow definition
    ├── nodes.py       # Node implementations
    └── state.py       # Shared state
```

## Key Features

1. **Bidirectional Sync**: Changes in Lark reflect in GitHub and vice versa
2. **Member Standardization**: Email -> GitHub username / Lark open_id
3. **ACID Consistency**: SQLite transactions + outbox pattern
4. **LLM Processing**: Parse fuzzy docs into structured todos

## Integration Points

- **GitHub**: `KataDavidXD/GithubAutoLark` repository
- **Lark Base**: Tasks table with fields (Task Name, Status, Assignee, GitHub Issue, Last Sync)
