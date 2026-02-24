# Requirements Analysis (需求分析表)

> Version: 2.0 | Date: 2026-02-24
> Scope: Unified GitHub-Lark Project Management Agent System

---

## 1. Executive Summary

Refactor the existing batch-oriented GitHub-Lark sync pipeline into an **interactive, agent-driven project management system**. The system accepts natural-language commands from a chat interface and performs CRUD operations across GitHub Issues, Lark Bitable (multi-table), and a unified local Member registry — all with ACID local guarantees and transactional consistency.

---

## 2. Current System Analysis (AS-IS)

### 2.1 What Exists

| Component | File | Capability | Limitation |
|-----------|------|-----------|------------|
| GitHub Service | `src/github_service.py` | REST API for Issues CRUD | No assignee-member linkage, no label taxonomy |
| Lark Service | `src/lark_service.py` | Bitable CRUD via MCP | Single-table only, no multi-table routing |
| MCP Client | `src/mcp_client.py` | JSON-RPC stdio to Lark MCP | Works, but tightly coupled to one process |
| SQLite DB | `src/db.py` | employees, tasks, mappings, outbox, sync_log, sync_state | `employees` is email-only, no role/position/team |
| Sync Engine | `src/sync_engine.py` | Bidirectional sync with outbox pattern | Batch-only, no interactive CRUD |
| LangGraph Agent | `src/agent/` | Linear pipeline: load→parse→sync | No interactive routing, no command parsing, no multi-agent |
| LLM Processor | `src/llm_processor.py` | Markdown→structured JSON | Input-file oriented, not chat-command oriented |
| Config | `src/config.py` | Env-based config | Solid, reusable |

### 2.2 Key Gaps

| # | Gap | Impact |
|---|-----|--------|
| G1 | No interactive chat interface — system only reads files | Cannot accept real-time user commands |
| G2 | `employees` table lacks role, position, GitHub username, team assignment | Cannot manage team members as first-class entities |
| G3 | Lark integration is single-table | Cannot route tasks to different Lark tables by type/project |
| G4 | LangGraph is a linear pipeline, not a command-routed agent graph | Cannot handle diverse CRUD commands |
| G5 | No member-centric views (issues by person, records by person) | Core UX requirement missing |
| G6 | No GitHub↔Lark conversion commands | Users need explicit issue→Lark and record→GitHub flows |
| G7 | Outbox pattern exists but no dispatcher loop | Events enqueued but not reliably processed |

---

## 3. Stakeholder Requirements

### 3.1 Actors

| Actor | Description |
|-------|-------------|
| **Project Manager** | Issues commands to manage team, tasks, and sync operations |
| **Team Member** | Referenced in assignments; identity bridged across GitHub and Lark |
| **System (Agent)** | Interprets commands, performs CRUD, maintains consistency |

### 3.2 Interaction Model

```
User (Chat Box)
    │
    ▼
┌────────────────────┐
│  Command Router    │  ← LangGraph entry point
│  (Intent Parser)   │
└────────┬───────────┘
         │
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
 Member    GitHub     Lark Table
 Agent     Agent      Agent
```

---

## 4. Functional Requirements

### FR-1: Unified Member Management

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|-------------------|
| FR-1.1 | **Create member** with name, email, role, position, GitHub username, and Lark table assignments | P0 | Member persisted in `members` table with all fields |
| FR-1.2 | **Read member** by email, name, or role | P0 | Returns full member profile including cross-platform IDs |
| FR-1.3 | **Update member** role, position, Lark table assignments | P0 | Atomic update; linked issues/records reflect new assignment |
| FR-1.4 | **Delete member** (soft-delete with status flag) | P1 | Member marked inactive; assignments preserved for audit |
| FR-1.5 | **List members** with filters (by role, by team, by table) | P0 | Paginated list with filter support |
| FR-1.6 | **Resolve cross-platform IDs** — email→lark_open_id, email→github_username | P0 | Auto-resolution via Lark Contact API; fallback to manual |
| FR-1.7 | **View member's work** — all GitHub issues + all Lark records for a member | P0 | Aggregated view from both platforms |
| FR-1.8 | **Sync member progress** — update GitHub issue status and Lark record status together | P1 | Transactional: both updates succeed or both roll back via outbox |

### FR-2: GitHub Issues Management

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|-------------------|
| FR-2.1 | **Create issue** with title, body, labels, assignee (by member name/email) | P0 | Issue created in GitHub; mapping stored locally |
| FR-2.2 | **Read issue** by number, by title search, or by member | P0 | Returns issue details with local enrichment (member info) |
| FR-2.3 | **Update issue** title, body, status, labels, assignee | P0 | GitHub API call + local DB update in transaction |
| FR-2.4 | **Close/Reopen issue** | P0 | State change propagated to linked Lark record |
| FR-2.5 | **List issues** with filters (state, labels, assignee, date range) | P0 | Supports GitHub API query params + local member lookup |
| FR-2.6 | **Comment on issue** | P1 | Comment created via GitHub API |
| FR-2.7 | **Convert issue → Lark record** — push a GitHub issue to a specified Lark table | P0 | Creates Lark record, stores mapping, maintains bidirectional link |
| FR-2.8 | **Bulk operations** — close all issues by label, reassign by member | P1 | Batch with per-item error handling |

### FR-3: Lark Tables Management

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|-------------------|
| FR-3.1 | **Create record** in a specified Lark table with field values | P0 | Record created via MCP; mapping stored locally |
| FR-3.2 | **Read record** by record_id, by field search, or by member | P0 | Returns record with local enrichment |
| FR-3.3 | **Update record** fields (status, assignee, custom fields) | P0 | MCP update + local DB update in transaction |
| FR-3.4 | **Delete record** (Lark soft-delete where supported) | P1 | Remove mapping; log deletion |
| FR-3.5 | **List records** with filters (by member, by status, by time, by type/table) | P0 | Supports Lark search API filter conditions |
| FR-3.6 | **Multi-table routing** — members are assigned to specific Lark tables; CRUD targets the correct table | P0 | Table selection based on member's table assignment or explicit command |
| FR-3.7 | **Convert record → GitHub issue** — push a Lark record to GitHub | P0 | Creates GitHub issue, stores mapping, maintains bidirectional link |
| FR-3.8 | **Create new Lark table** with specified fields | P1 | Table created via MCP; registered in system config |
| FR-3.9 | **List available tables** in a Bitable app | P1 | Returns table names and IDs |

### FR-4: Cross-Platform Sync & Conversion

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|-------------------|
| FR-4.1 | **Bidirectional status sync** — status changes in either platform propagate to the other | P0 | Outbox-based eventual consistency |
| FR-4.2 | **Conflict detection** — if both sides changed, report conflict | P1 | Last-write-wins with audit log |
| FR-4.3 | **Conversion with field mapping** — configurable field mapping between GitHub issue fields and Lark table fields | P0 | Mapping config per table |
| FR-4.4 | **Transactional consistency** — local DB write + outbox enqueue in one ACID transaction | P0 | SQLite transaction wraps both operations |

### FR-5: Command Interface

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|-------------------|
| FR-5.1 | **Natural language command parsing** via LLM | P0 | User types in chat box; LLM extracts intent + entities |
| FR-5.2 | **Intent classification** — member_management, github_issues, lark_tables, sync | P0 | Router accurately dispatches to correct agent |
| FR-5.3 | **Entity extraction** — member name, issue number, table name, status, etc. | P0 | Extracted entities passed as typed parameters to agents |
| FR-5.4 | **Confirmation for destructive ops** — delete, bulk update, close | P1 | Agent asks for confirmation before executing |
| FR-5.5 | **Error reporting** — clear, actionable error messages returned to user | P0 | All agent nodes return structured error responses |

---

## 5. Non-Functional Requirements

| ID | Requirement | Category | Target |
|----|-------------|----------|--------|
| NFR-1 | ACID transactions for all local DB operations | Reliability | SQLite WAL mode, explicit transactions |
| NFR-2 | Outbox pattern for all external API calls | Consistency | Zero data loss on API failure |
| NFR-3 | Idempotent external operations | Resilience | Safe retries with deterministic keys |
| NFR-4 | Secrets never logged or committed | Security | Redaction layer; .env gitignored |
| NFR-5 | UTF-8 encoding enforced everywhere | Encoding | No GBK/ASCII errors on any platform |
| NFR-6 | Response time < 10s for simple CRUD commands | Performance | Direct API calls, no unnecessary LLM hops |
| NFR-7 | Extensible to new Lark tables without code changes | Extensibility | Table config driven, not hardcoded |
| NFR-8 | Comprehensive audit log for all sync operations | Auditability | `sync_log` table with direction, status, timestamp |

---

## 6. Data Model Requirements

### 6.1 Unified `members` Table (replaces `employees`)

```
members
├── member_id       TEXT PRIMARY KEY (UUID)
├── name            TEXT NOT NULL
├── email           TEXT UNIQUE NOT NULL
├── github_username TEXT
├── lark_open_id    TEXT
├── role            TEXT NOT NULL DEFAULT 'member'
│                   (admin | manager | developer | designer | qa | member)
├── position        TEXT
│                   (e.g., "Frontend Lead", "Backend Developer")
├── team            TEXT
├── status          TEXT NOT NULL DEFAULT 'active'
│                   (active | inactive)
├── lark_tables     TEXT
│                   JSON array of {app_token, table_id, table_name} assignments
├── created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
└── updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

### 6.2 `tasks` Table (enhanced)

```
tasks
├── task_id             TEXT PRIMARY KEY (UUID)
├── title               TEXT NOT NULL
├── body                TEXT DEFAULT ''
├── status              TEXT NOT NULL DEFAULT 'To Do'
├── priority            TEXT DEFAULT 'medium'
├── source              TEXT DEFAULT 'manual'
│                       (manual | github_sync | lark_sync | command)
├── assignee_member_id  TEXT REFERENCES members(member_id)
├── labels              TEXT  (JSON array)
├── target_table        TEXT  (lark table_id for routing)
├── created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
└── updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

### 6.3 `mappings` Table (enhanced for multi-table)

```
mappings
├── mapping_id          TEXT PRIMARY KEY (UUID)
├── task_id             TEXT NOT NULL REFERENCES tasks(task_id)
├── github_issue_number INTEGER
├── github_repo         TEXT  (owner/repo for multi-repo future)
├── lark_record_id      TEXT
├── lark_app_token      TEXT
├── lark_table_id       TEXT
├── field_mapping       TEXT  (JSON: custom field mapping overrides)
├── created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
└── updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

### 6.4 `lark_tables_registry` Table (new)

```
lark_tables_registry
├── registry_id     TEXT PRIMARY KEY (UUID)
├── app_token       TEXT NOT NULL
├── table_id        TEXT NOT NULL
├── table_name      TEXT NOT NULL
├── description     TEXT
├── field_mapping   TEXT NOT NULL
│                   JSON: {title_field, status_field, assignee_field, ...}
├── is_default      INTEGER DEFAULT 0
├── created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
└── updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

### 6.5 Retained Tables

- `outbox` — unchanged, still used for eventual consistency
- `sync_log` — unchanged, audit trail
- `sync_state` — unchanged, polling cursors

---

## 7. Command Interface Specification

### 7.1 Member Commands

| Command Pattern | Intent | Example |
|----------------|--------|---------|
| `add member <name> <email> as <role>` | Create member | "Add member Alice alice@co.com as developer" |
| `show member <name/email>` | Read member | "Show member Alice" |
| `update member <name> role to <role>` | Update role | "Update member Alice role to manager" |
| `assign member <name> to table <table>` | Assign Lark table | "Assign Alice to table ProjectA" |
| `list members [by role/team]` | List members | "List members by role developer" |
| `show <name>'s work` | View member's work | "Show Alice's work" |
| `remove member <name>` | Soft-delete | "Remove member Bob" |

### 7.2 GitHub Issue Commands

| Command Pattern | Intent | Example |
|----------------|--------|---------|
| `create issue <title> [body] [assignee] [labels]` | Create | "Create issue 'Fix login bug' assigned to Alice label:bug" |
| `show issue #<number>` | Read | "Show issue #42" |
| `update issue #<number> status/title/body/assignee` | Update | "Update issue #42 assign to Bob" |
| `close issue #<number>` | Close | "Close issue #42" |
| `list issues [by member/label/state]` | List | "List issues by Alice" or "List open issues" |
| `send issue #<number> to lark [table]` | Convert to Lark | "Send issue #42 to lark table ProjectA" |

### 7.3 Lark Table Commands

| Command Pattern | Intent | Example |
|----------------|--------|---------|
| `create task <title> in table <table> [assignee] [fields]` | Create record | "Create task 'Design mockup' in table Design assign to Alice" |
| `show record <id> in table <table>` | Read record | "Show record rec_xxx in table Design" |
| `update record <id> status to <status>` | Update record | "Update record rec_xxx status to Done" |
| `list records in table <table> [by member/status/time]` | List records | "List records in table Design by Alice" |
| `send record <id> to github` | Convert to GitHub | "Send record rec_xxx to github" |
| `list tables` | List available tables | "List tables" |
| `create table <name> with fields <field_list>` | Create new table | "Create table QA with fields Name,Status,Assignee" |

---

## 8. Use Case Flows

### UC-1: Add a New Team Member

```
User: "Add member David david@co.com as frontend developer"
 │
 ├─ 1. Command Router → intent: member_management, action: create
 ├─ 2. Member Agent: validate input (email unique, role valid)
 ├─ 3. Member Agent: resolve lark_open_id via Lark Contact API
 ├─ 4. Member Agent: INSERT into members table (ACID)
 ├─ 5. Member Agent: return confirmation with resolved IDs
 │
 └─ Response: "Member David added. Lark ID resolved. GitHub: david-gh."
```

### UC-2: Create GitHub Issue and Push to Lark

```
User: "Create issue 'Implement auth module' assigned to Alice label:feature, send to lark table Backend"
 │
 ├─ 1. Command Router → intent: github_issues + lark_sync
 ├─ 2. GitHub Agent: resolve Alice → GitHub username
 ├─ 3. GitHub Agent: POST /issues → get issue_number
 ├─ 4. GitHub Agent: INSERT task + mapping (ACID)
 ├─ 5. Lark Agent: create_record in Backend table
 ├─ 6. Lark Agent: UPDATE mapping with lark_record_id (ACID)
 │
 └─ Response: "Issue #55 created. Lark record synced to Backend table."
```

### UC-3: Check a Member's Progress Across Platforms

```
User: "Show Alice's work"
 │
 ├─ 1. Command Router → intent: member_management, action: view_work
 ├─ 2. Member Agent: lookup Alice → member_id, github_username, lark_open_id
 ├─ 3. GitHub Agent: list_issues(assignee=alice-gh)
 ├─ 4. Lark Agent: search_records(assignee=alice_open_id) across all assigned tables
 ├─ 5. Member Agent: aggregate and format results
 │
 └─ Response: "Alice has 3 open GitHub issues, 5 Lark tasks (2 Done, 2 In Progress, 1 To Do)"
```

### UC-4: Convert Lark Record to GitHub Issue

```
User: "Send record rec_abc123 to github"
 │
 ├─ 1. Command Router → intent: lark_tables, action: convert_to_github
 ├─ 2. Lark Agent: fetch record details from Lark
 ├─ 3. Lark Agent: map fields → GitHub issue fields using field_mapping config
 ├─ 4. GitHub Agent: create_issue with mapped fields
 ├─ 5. DB: INSERT/UPDATE mapping with both IDs (ACID)
 │
 └─ Response: "Lark record converted to GitHub Issue #60. Bidirectional link established."
```

---

## 9. Error Handling Requirements

| Scenario | Expected Behavior |
|----------|-------------------|
| GitHub API returns 401 | Report "GitHub authentication failed. Check GITHUB_TOKEN." |
| Lark MCP process crashes | Restart MCP process; retry operation once; report if still failing |
| Member email not found in Lark | Create member with `lark_open_id = NULL`; log warning |
| Duplicate member email | Reject with "Member with this email already exists" |
| Invalid command syntax | LLM attempts re-interpretation; if still unclear, ask for clarification |
| Network timeout on sync | Enqueue to outbox; process_outbox retries with exponential backoff |
| Conflicting status updates | Last-write-wins; log conflict in sync_log with both values |
| Lark table not found | Report "Table not found. Use 'list tables' to see available tables." |

---

## 10. Migration Plan (Current → New)

| Step | Action | Risk |
|------|--------|------|
| 1 | Create new `members` table; migrate data from `employees` | Low — additive |
| 2 | Add `lark_tables_registry` table | Low — new table |
| 3 | Refactor `tasks` to reference `members.member_id` | Medium — FK change |
| 4 | Refactor `mappings` for multi-table support | Medium — schema change |
| 5 | Build new LangGraph agent graph with command router | High — core logic |
| 6 | Implement Member/GitHub/Lark sub-agents | High — new code |
| 7 | Build interactive command parser (LLM-based) | Medium — new capability |
| 8 | Deprecate file-based input pipeline | Low — remove after validation |

---

## 11. Success Metrics

| Metric | Target |
|--------|--------|
| All CRUD commands for members, issues, records work end-to-end | 100% |
| Cross-platform conversion (issue↔record) works reliably | 100% |
| Member progress view aggregates both platforms correctly | 100% |
| No data loss on API failures (outbox pattern) | 100% |
| Average command response time | < 10 seconds |
| System handles 50+ members, 500+ tasks | Verified |

---

## 12. Glossary

| Term | Definition |
|------|-----------|
| **Member** | A unified identity representing a person across GitHub and Lark |
| **Task** | A local work item that may be linked to a GitHub Issue and/or Lark record |
| **Mapping** | The link between a local task and its remote representations |
| **Outbox** | A queue of pending external API calls for eventual consistency |
| **MCP** | Model Context Protocol — JSON-RPC interface to Lark's APIs |
| **Bitable** | Lark's spreadsheet-database product (similar to Airtable) |
| **Record** | A row in a Lark Bitable table |
| **Field Mapping** | Configuration that maps Lark table fields to system fields |
