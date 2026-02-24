# CONFIG_KEYS (No Secrets)

This document lists the **configuration keys** used by this project and where they come from. It intentionally does **not** contain any secret values.

## General Rules

- Never commit `.env`.
- Never hardcode Lark app secrets or GitHub PATs in any script.
- All saved demo logs under `demos/` must be **redacted**.

## GitHub

- **`GITHUB_TOKEN`** (required)
  - Source: GitHub PAT created in GitHub settings
  - Used by: `src/github_service.py`, `demos/*`
- **`OWNER`**, **`REPO`** (required for non-hardcoded execution)
  - Source: user-config
  - Used by: GitHub demo + sync

## Lark (via MCP server)

- **`LARK_MCP_CLIENT_ID`** (required if spawning MCP)
  - Source: Lark developer console (app credentials)
  - Used by: `src/mcp_client.py` (spawn args)
- **`LARK_MCP_CLIENT_SECRET`** (required if spawning MCP)
  - Source: Lark developer console (app credentials)
  - Used by: `src/mcp_client.py`
- **`LARK_MCP_DOMAIN`** (optional; default `https://open.larksuite.com/`)
  - Source: Lark region/domain
  - Used by: `src/mcp_client.py`
- **`LARK_MCP_USE_OAUTH`** (optional; default `true`)
  - Source: whether to use OAuth user login in MCP
  - Used by: `src/mcp_client.py`

## Lark Base (Bitable) Target

These are written to `.env` after the Lark lifecycle demo creates the Base/table:

- **`LARK_APP_TOKEN`**
  - Source: output of Base App creation
- **`LARK_TASKS_TABLE_ID`**
  - Source: output of table creation or table list

## Bitable Field Names (must match exactly)

- **`LARK_FIELD_TITLE`** (default `Task Name`)
- **`LARK_FIELD_STATUS`** (default `Status`)
- **`LARK_FIELD_ASSIGNEE`** (default `Assignee`)
- **`LARK_FIELD_GITHUB_ISSUE`** (default `GitHub Issue`)
- **`LARK_FIELD_LAST_SYNC`** (default `Last Sync`)

## Employee Identity

- **`EMPLOYEE_EMAIL`** (required for assignee demo)
  - Source: your enterprise email address inside the Lark tenant
  - Used by: contact lookup -> open_id -> Bitable assignment

## LLM (optional; future feature)

- **`LLM_API_KEY`**, **`LLM_BASE_URL`**, **`DEFAULT_LLM`**
  - Source: your model provider
  - Used by: `src/llm_processor.py` later

