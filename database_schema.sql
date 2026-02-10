-- Project Position System Database Schema
-- SQLite Database for Local Synchronization

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Tasks table (central source of truth for all tasks)
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_uuid TEXT UNIQUE NOT NULL,  -- Unique identifier across systems
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',  -- 'open', 'in_progress', 'completed', 'cancelled'
    priority TEXT DEFAULT 'medium',  -- 'low', 'medium', 'high', 'critical'
    complexity TEXT DEFAULT 'medium',  -- 'low', 'medium', 'high'
    parent_task_id INTEGER,  -- For subtasks
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    due_date TIMESTAMP,
    completed_at TIMESTAMP,
    created_by TEXT,  -- User who created the task
    FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CHECK (status IN ('open', 'in_progress', 'completed', 'cancelled')),
    CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    CHECK (complexity IN ('low', 'medium', 'high'))
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_uuid ON tasks(task_uuid);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_tasks_timestamp 
AFTER UPDATE ON tasks
FOR EACH ROW
BEGIN
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- =============================================================================
-- EMPLOYEE MANAGEMENT
-- =============================================================================

-- Employees table
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    github_username TEXT,
    lark_user_id TEXT,  -- Lark Open ID
    lark_union_id TEXT,  -- Lark Union ID (for multi-tenant)
    position TEXT NOT NULL,  -- 'frontend', 'backend', 'fullstack', 'devops', 'designer', 'qa', etc.
    expertise TEXT,  -- JSON array of skills/technologies
    max_concurrent_tasks INTEGER DEFAULT 5,  -- Capacity management
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_employees_github ON employees(github_username);
CREATE INDEX IF NOT EXISTS idx_employees_lark ON employees(lark_user_id);
CREATE INDEX IF NOT EXISTS idx_employees_position ON employees(position);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_employees_timestamp 
AFTER UPDATE ON employees
FOR EACH ROW
BEGIN
    UPDATE employees SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- =============================================================================
-- TASK ASSIGNMENTS
-- =============================================================================

-- Task assignments (many-to-many relationship)
CREATE TABLE IF NOT EXISTS task_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'assigned',  -- 'assigned', 'accepted', 'rejected', 'completed'
    assigned_by TEXT,  -- Who assigned this task (can be 'system', 'manual', or user ID)
    notes TEXT,  -- Assignment notes
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    UNIQUE(task_id, employee_id),
    CHECK (status IN ('assigned', 'accepted', 'rejected', 'completed'))
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_assignments_task ON task_assignments(task_id);
CREATE INDEX IF NOT EXISTS idx_assignments_employee ON task_assignments(employee_id);
CREATE INDEX IF NOT EXISTS idx_assignments_status ON task_assignments(status);

-- =============================================================================
-- GITHUB INTEGRATION
-- =============================================================================

-- GitHub issues mapping
CREATE TABLE IF NOT EXISTS github_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    issue_url TEXT,
    github_status TEXT,  -- 'open', 'closed'
    github_state_reason TEXT,  -- 'completed', 'not_planned', 'reopened'
    labels TEXT,  -- JSON array of labels
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP,
    sync_enabled BOOLEAN DEFAULT 1,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    UNIQUE(repo_owner, repo_name, issue_number)
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_github_task ON github_issues(task_id);
CREATE INDEX IF NOT EXISTS idx_github_repo ON github_issues(repo_owner, repo_name);
CREATE INDEX IF NOT EXISTS idx_github_issue_number ON github_issues(issue_number);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_github_issues_timestamp 
AFTER UPDATE ON github_issues
FOR EACH ROW
BEGIN
    UPDATE github_issues SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- =============================================================================
-- LARK INTEGRATION
-- =============================================================================

-- Lark tasks mapping
CREATE TABLE IF NOT EXISTS lark_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    lark_task_guid TEXT UNIQUE NOT NULL,
    lark_task_url TEXT,
    lark_status TEXT,  -- Lark task status
    lark_tasklist_guid TEXT,  -- Which tasklist it belongs to
    lark_section_guid TEXT,  -- Which section in the tasklist
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP,
    sync_enabled BOOLEAN DEFAULT 1,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_lark_task ON lark_tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_lark_guid ON lark_tasks(lark_task_guid);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_lark_tasks_timestamp 
AFTER UPDATE ON lark_tasks
FOR EACH ROW
BEGIN
    UPDATE lark_tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- =============================================================================
-- SYNC MANAGEMENT
-- =============================================================================

-- Sync logs for debugging and auditing
CREATE TABLE IF NOT EXISTS sync_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    source TEXT NOT NULL,  -- 'github', 'lark', 'manual', 'system'
    target TEXT,  -- 'github', 'lark', 'local'
    action TEXT NOT NULL,  -- 'create', 'update', 'delete', 'sync'
    status TEXT NOT NULL,  -- 'success', 'failed', 'pending', 'retrying'
    error_code TEXT,
    error_message TEXT,
    request_payload TEXT,  -- JSON of request data
    response_payload TEXT,  -- JSON of response data
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    CHECK (source IN ('github', 'lark', 'manual', 'system')),
    CHECK (status IN ('success', 'failed', 'pending', 'retrying'))
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_sync_logs_task ON sync_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_status ON sync_logs(status);
CREATE INDEX IF NOT EXISTS idx_sync_logs_source ON sync_logs(source);
CREATE INDEX IF NOT EXISTS idx_sync_logs_created ON sync_logs(created_at);

-- Sync state tracking (prevents duplicate syncs)
CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    last_github_sync TIMESTAMP,
    last_lark_sync TIMESTAMP,
    github_etag TEXT,  -- GitHub ETag for conditional requests
    lark_version TEXT,  -- Lark version for optimistic locking
    is_syncing BOOLEAN DEFAULT 0,  -- Lock to prevent concurrent syncs
    sync_started_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    UNIQUE(task_id)
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_sync_state_task ON sync_state(task_id);
CREATE INDEX IF NOT EXISTS idx_sync_state_syncing ON sync_state(is_syncing);

-- =============================================================================
-- PROJECT CONTEXT
-- =============================================================================

-- Projects table (for organizing tasks by project)
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    github_repo TEXT,  -- Format: "owner/repo"
    lark_tasklist_guid TEXT,
    status TEXT DEFAULT 'active',  -- 'active', 'on_hold', 'completed', 'archived'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (status IN ('active', 'on_hold', 'completed', 'archived'))
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_projects_timestamp 
AFTER UPDATE ON projects
FOR EACH ROW
BEGIN
    UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Project documents (store uploaded documents for context)
CREATE TABLE IF NOT EXISTS project_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,  -- 'markdown', 'pdf', 'docx', 'txt', etc.
    content_hash TEXT,  -- SHA256 hash for change detection
    processed_content TEXT,  -- Extracted and processed text
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_project_docs_project ON project_documents(project_id);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_project_documents_timestamp 
AFTER UPDATE ON project_documents
FOR EACH ROW
BEGIN
    UPDATE project_documents SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Link tasks to projects
CREATE TABLE IF NOT EXISTS project_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    UNIQUE(project_id, task_id)
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_project_tasks_project ON project_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_project_tasks_task ON project_tasks(task_id);

-- =============================================================================
-- LLM PROCESSING
-- =============================================================================

-- LLM processing history
CREATE TABLE IF NOT EXISTS llm_processing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    input_text TEXT NOT NULL,
    output_text TEXT NOT NULL,
    model_name TEXT,  -- 'gpt-4', 'claude-3', etc.
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    processing_time_ms INTEGER,
    status TEXT DEFAULT 'completed',  -- 'completed', 'failed', 'pending'
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    CHECK (status IN ('completed', 'failed', 'pending'))
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_llm_processing_task ON llm_processing(task_id);
CREATE INDEX IF NOT EXISTS idx_llm_processing_status ON llm_processing(status);
CREATE INDEX IF NOT EXISTS idx_llm_processing_created ON llm_processing(created_at);

-- =============================================================================
-- NOTIFICATIONS
-- =============================================================================

-- Notification queue
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_employee_id INTEGER,
    recipient_lark_id TEXT,
    notification_type TEXT NOT NULL,  -- 'sync_failure', 'task_assigned', 'status_change', 'mention'
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',  -- 'low', 'normal', 'high', 'urgent'
    channel TEXT DEFAULT 'lark',  -- 'lark', 'email', 'webhook'
    status TEXT DEFAULT 'pending',  -- 'pending', 'sent', 'failed'
    task_id INTEGER,
    metadata TEXT,  -- JSON for additional data
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recipient_employee_id) REFERENCES employees(id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    CHECK (status IN ('pending', 'sent', 'failed'))
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_employee_id);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);

-- =============================================================================
-- CONFIGURATION
-- =============================================================================

-- System configuration key-value store
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_system_config_timestamp 
AFTER UPDATE ON system_config
FOR EACH ROW
BEGIN
    UPDATE system_config SET updated_at = CURRENT_TIMESTAMP WHERE key = NEW.key;
END;

-- Insert default configuration
INSERT OR IGNORE INTO system_config (key, value, description) VALUES
('sync_interval_seconds', '300', 'Interval between automatic syncs in seconds'),
('retry_max_attempts', '3', 'Maximum number of retry attempts for failed operations'),
('retry_backoff_factor', '2', 'Backoff multiplier for retries'),
('llm_model', 'gpt-4-turbo', 'Default LLM model for task processing'),
('llm_temperature', '0.3', 'Temperature setting for LLM'),
('max_tasks_per_batch', '10', 'Maximum tasks to process in one batch'),
('github_sync_enabled', 'true', 'Enable GitHub synchronization'),
('lark_sync_enabled', 'true', 'Enable Lark synchronization'),
('auto_assign_tasks', 'true', 'Automatically assign tasks to employees'),
('notification_enabled', 'true', 'Enable notifications');

-- =============================================================================
-- VIEWS (for easier querying)
-- =============================================================================

-- View: Active tasks with assignments
CREATE VIEW IF NOT EXISTS v_active_tasks AS
SELECT 
    t.id,
    t.task_uuid,
    t.title,
    t.description,
    t.status,
    t.priority,
    t.complexity,
    t.created_at,
    t.updated_at,
    t.due_date,
    GROUP_CONCAT(e.name, ', ') as assignees,
    GROUP_CONCAT(e.github_username, ', ') as github_usernames
FROM tasks t
LEFT JOIN task_assignments ta ON t.id = ta.task_id
LEFT JOIN employees e ON ta.employee_id = e.id
WHERE t.status IN ('open', 'in_progress')
GROUP BY t.id;

-- View: Sync status overview
CREATE VIEW IF NOT EXISTS v_sync_status AS
SELECT 
    t.id as task_id,
    t.title,
    t.status as task_status,
    g.issue_number as github_issue,
    g.github_status,
    g.last_synced_at as github_last_sync,
    l.lark_task_guid,
    l.last_synced_at as lark_last_sync,
    CASE 
        WHEN g.id IS NULL AND l.id IS NULL THEN 'not_synced'
        WHEN g.id IS NOT NULL AND l.id IS NOT NULL THEN 'fully_synced'
        WHEN g.id IS NOT NULL THEN 'github_only'
        WHEN l.id IS NOT NULL THEN 'lark_only'
    END as sync_status
FROM tasks t
LEFT JOIN github_issues g ON t.id = g.task_id
LEFT JOIN lark_tasks l ON t.id = l.task_id;

-- View: Employee workload
CREATE VIEW IF NOT EXISTS v_employee_workload AS
SELECT 
    e.id,
    e.name,
    e.position,
    e.max_concurrent_tasks,
    COUNT(ta.id) as assigned_tasks,
    e.max_concurrent_tasks - COUNT(ta.id) as available_capacity
FROM employees e
LEFT JOIN task_assignments ta ON e.id = ta.employee_id
LEFT JOIN tasks t ON ta.task_id = t.id
WHERE e.is_active = 1
  AND (t.status IN ('open', 'in_progress') OR t.status IS NULL)
GROUP BY e.id;

-- =============================================================================
-- SAMPLE DATA (for testing)
-- =============================================================================

-- Insert sample employees
INSERT OR IGNORE INTO employees (name, email, github_username, position, expertise) VALUES
('John Doe', 'john@example.com', 'johndoe', 'fullstack', '["Python", "React", "Node.js", "PostgreSQL"]'),
('Jane Smith', 'jane@example.com', 'janesmith', 'backend', '["Python", "Django", "FastAPI", "Redis"]'),
('Bob Wilson', 'bob@example.com', 'bobwilson', 'frontend', '["React", "TypeScript", "CSS", "Next.js"]'),
('Alice Chen', 'alice@example.com', 'alicechen', 'devops', '["Docker", "Kubernetes", "AWS", "GitHub Actions"]');

-- Insert sample project
INSERT OR IGNORE INTO projects (name, description, status) VALUES
('Project Position System', 'Automated task management and synchronization system', 'active');
