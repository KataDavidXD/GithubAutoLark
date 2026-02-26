"""Database schema DDL — all table definitions for the unified system."""

SCHEMA_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;

-- ==========================================================================
-- Unified Member Table (replaces old 'employees')
-- ==========================================================================
CREATE TABLE IF NOT EXISTS members (
    member_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    github_username TEXT,
    lark_open_id    TEXT,
    role            TEXT NOT NULL DEFAULT 'member'
                    CHECK(role IN ('admin','manager','developer','designer','qa','member')),
    position        TEXT,
    team            TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','inactive')),
    lark_tables     TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_members_email ON members(email);
CREATE INDEX IF NOT EXISTS idx_members_github ON members(github_username);
CREATE INDEX IF NOT EXISTS idx_members_lark ON members(lark_open_id);
CREATE INDEX IF NOT EXISTS idx_members_role ON members(role);

-- ==========================================================================
-- Task Table
-- ==========================================================================
CREATE TABLE IF NOT EXISTS tasks (
    task_id             TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    body                TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'To Do',
    priority            TEXT DEFAULT 'medium'
                        CHECK(priority IN ('critical','high','medium','low')),
    source              TEXT DEFAULT 'manual',
    assignee_member_id  TEXT REFERENCES members(member_id),
    labels              TEXT DEFAULT '[]',
    target_table        TEXT,
    due_date            TEXT,
    progress            INTEGER DEFAULT 0 CHECK(progress >= 0 AND progress <= 100),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_member_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);

-- ==========================================================================
-- Mapping Table (multi-table + multi-repo ready)
-- ==========================================================================
CREATE TABLE IF NOT EXISTS mappings (
    mapping_id          TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL REFERENCES tasks(task_id),
    github_issue_number INTEGER,
    github_repo         TEXT,
    lark_record_id      TEXT,
    lark_app_token      TEXT,
    lark_table_id       TEXT,
    field_mapping       TEXT DEFAULT '{}',
    sync_status         TEXT DEFAULT 'synced'
                        CHECK(sync_status IN ('synced','pending','conflict','error')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_mappings_task ON mappings(task_id);
CREATE INDEX IF NOT EXISTS idx_mappings_github ON mappings(github_issue_number);
CREATE INDEX IF NOT EXISTS idx_mappings_lark ON mappings(lark_record_id);

-- ==========================================================================
-- Lark Tables Registry
-- ==========================================================================
CREATE TABLE IF NOT EXISTS lark_tables_registry (
    registry_id     TEXT PRIMARY KEY,
    app_token       TEXT NOT NULL,
    table_id        TEXT NOT NULL,
    table_name      TEXT NOT NULL,
    description     TEXT,
    field_mapping   TEXT NOT NULL DEFAULT '{}',
    is_default      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(app_token, table_id)
);

-- ==========================================================================
-- Outbox (eventual consistency)
-- ==========================================================================
CREATE TABLE IF NOT EXISTS outbox (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','processing','sent','failed','dead')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,
    last_error      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
CREATE INDEX IF NOT EXISTS idx_outbox_type ON outbox(event_type);

-- ==========================================================================
-- Sync Log (audit trail)
-- ==========================================================================
CREATE TABLE IF NOT EXISTS sync_log (
    id          TEXT PRIMARY KEY,
    direction   TEXT NOT NULL,
    subject     TEXT NOT NULL,
    subject_id  TEXT,
    status      TEXT NOT NULL,
    message     TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_sync_log_subject ON sync_log(subject, subject_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_created ON sync_log(created_at);

-- ==========================================================================
-- Sync State (polling cursors)
-- ==========================================================================
CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
"""
