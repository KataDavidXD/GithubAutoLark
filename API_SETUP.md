# API_SETUP

This document is a practical survey/checklist for setting up **GitHub** and **Lark** APIs for this project. It is written for Windows and for a workflow that will run **real lifecycle + sync demos**.

## 1) GitHub API Setup

### Required Credentials

- **GitHub Personal Access Token (PAT)** in `.env` as `GITHUB_TOKEN`
  - Must have permission to create and update issues in the target repo.

### Recommended Token Scopes

- If the repo is **private**: `repo`
- If the repo is **public**: `public_repo` is often sufficient
- For issues, comments, labels: included in the above scopes

### API Conventions Used

- Base URL: `https://api.github.com/repos/{OWNER}/{REPO}`
- Headers:
  - `Authorization: Bearer <GITHUB_TOKEN>`
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2022-11-28`

### Connectivity Test

The repo contains lifecycle scripts (will be replaced by a structured module + demo runner):
- `test_github_api.py`
- `test_github_lifecycle.py`

These exercise:
- Create Issue
- Get Issue
- Update Issue
- Create Comment
- List Comments
- Close Issue

## 2) Lark API Setup (via Lark MCP)

This project uses Lark MCP tooling to call Lark APIs for:
- Bitable (Base) app/table/record operations
- Contact lookup (email -> open_id)
- Messaging (notify drift)

### Required Credentials / Setup Paths

Lark MCP credentials **must** be set in `.env` (not hardcoded in scripts):
- `LARK_MCP_CLIENT_ID` - App ID from Lark developer console
- `LARK_MCP_CLIENT_SECRET` - App Secret from Lark developer console
- `LARK_MCP_DOMAIN` - API domain (default: `https://open.larksuite.com/`)
- `LARK_MCP_USE_OAUTH` - `true` for OAuth user auth, `false` for tenant token

There are two authentication modes:

1. **OAuth user auth (recommended for interactive dev)**
   - Set `LARK_MCP_USE_OAUTH=true`
   - MCP server started with `--oauth`
   - Requires Lark app configured with OAuth redirect and required API permissions.

2. **App identity (tenant token)**
   - Set `LARK_MCP_USE_OAUTH=false`
   - Requires app/tenant configuration and permission grants
   - Useful for headless servers, but depends on enterprise policy

### Required Lark Permissions (high level)

Your Lark app must be granted API permissions for:

- **Bitable**: create app, list tables, create table, list fields, create/search/update records
- **Contacts**: resolve user id via email/mobile (`contact_v3_user_batchGetId`)
- **IM** (optional but required for drift notifications): send messages (`im_v1_message_create`)

Exact permission names differ by region/tenant. Validate in the Lark developer console by enabling the APIs that correspond to:
- `bitable.v1.*`
- `contact.v3.*`
- `im.v1.*`

### Lark “Assignee” Field Requirements

To assign a person in Bitable:
- Table must have a **User** field (type `11`) (e.g. `"Assignee"`)
- Value format uses `open_id` entries:
  - `Assignee: [{"id": "ou_..."}]`

The open_id is resolved from email using `contact_v3_user_batchGetId`.

## 3) Local Runtime Setup (Windows)

### Encoding Guardrails (avoid GBK errors)

Set environment variables before running Python demos:

- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`

All file writes use `encoding="utf-8"`.

### Environment Template

This repo will include `.env.template` with required keys. Copy it to `.env` locally and fill values.

## 4) Operational Survey Questions (for your org)

Answer these to finalize the production setup:

1. **GitHub**: Is the target repo public or private? (Determines PAT scope.)
2. **GitHub**: Are we allowed to create issues automatically on failures? Any labeling/assignee conventions?
3. **Lark**: Should we use OAuth user tokens or tenant/app tokens for production?
4. **Lark**: Which workspace/tenant should own the Base app? Who are admins/collaborators?
5. **Lark**: Do we need to notify a group chat or DM individuals when drift is detected?
6. **Data retention**: Where should SQLite DB live? What is the retention policy for sync logs?

