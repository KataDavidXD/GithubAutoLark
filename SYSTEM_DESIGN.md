# Project Position System - System Architecture

## Overview

The Project Position System is an intelligent task management and distribution platform that processes project documentation, assigns tasks to employees, and maintains synchronization between GitHub Issues and Lark (Feishu) workspace.

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                              │
│  • Project Structure Documents                                   │
│  • Manual Employee Position Assignments                          │
│  • Task Descriptions (Todos)                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PROCESSING LAYER                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  LLM Processing Engine                                   │   │
│  │  • Document Analysis & Context Understanding             │   │
│  │  • Task Standardization & Normalization                  │   │
│  │  • Task Decomposition (Large → Small Issues)             │   │
│  │  • Priority & Complexity Assessment                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SYNCHRONIZATION LAYER                         │
│                                                                  │
│  ┌─────────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  GitHub API     │◄──►│  Local DB    │◄──►│   Lark API    │  │
│  │  Integration    │    │  (SQLite)    │    │  Integration  │  │
│  └─────────────────┘    └──────────────┘    └───────────────┘  │
│                                                                  │
│  Sync Operations:                                                │
│  • Create GitHub Issues from standardized tasks                 │
│  • Auto-assign to employees based on position                   │
│  • Bidirectional status sync (GitHub ↔ Lark)                    │
│  • Conflict resolution & notification                            │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      NOTIFICATION LAYER                          │
│  • Lark Messages for sync failures                              │
│  • Status change notifications                                   │
│  • Assignment alerts                                             │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Document Processor
**Purpose**: Parse and extract structured information from project documents

**Responsibilities**:
- Read various document formats (MD, PDF, DOCX, TXT)
- Extract project structure, requirements, and context
- Identify key entities (features, modules, dependencies)

**Technologies**:
- Python docx, PyPDF2, markdown parsers
- NLP preprocessing for text normalization

### 2. LLM Task Standardizer
**Purpose**: Use Large Language Models to standardize and decompose tasks

**Responsibilities**:
- Analyze raw task descriptions with project context
- Standardize task format (title, description, acceptance criteria)
- Break down large tasks into smaller, actionable GitHub issues
- Estimate complexity and suggest appropriate assignees
- Generate proper labels and tags

**LLM Strategy**:
- Primary: OpenAI GPT-4 / Anthropic Claude
- Fallback: Local LLM (for sensitive data)
- Prompt templates for consistent output

**Input Format**:
```json
{
  "project_context": "...",
  "employee_positions": {...},
  "raw_task": "..."
}
```

**Output Format**:
```json
{
  "standardized_tasks": [
    {
      "title": "...",
      "description": "...",
      "acceptance_criteria": [...],
      "estimated_complexity": "low|medium|high",
      "suggested_assignee": "...",
      "labels": [...],
      "parent_task": "..."
    }
  ]
}
```

### 3. GitHub Integration Module
**Purpose**: Manage GitHub Issues as task tracking system

**Responsibilities**:
- Create issues from standardized tasks
- Auto-assign based on employee positions
- Sync status changes (open, in-progress, closed)
- Manage labels, milestones, and project boards
- Handle webhooks for real-time updates

**GitHub API Usage**:
- REST API v3 for CRUD operations
- GraphQL API v4 for complex queries
- Webhooks for event-driven sync

**Key Endpoints**:
- `POST /repos/{owner}/{repo}/issues` - Create issue
- `PATCH /repos/{owner}/{repo}/issues/{issue_number}` - Update issue
- `GET /repos/{owner}/{repo}/issues` - List issues
- Webhooks: `issues`, `issue_comment`, `label`

### 4. Lark (Feishu) Integration Module
**Purpose**: Bidirectional sync with Lark workspace for team collaboration

**Responsibilities**:
- Create/update Lark tasks from GitHub issues
- Monitor Lark task status changes
- Send notifications for sync failures
- Provide task dashboard in Lark

**Lark API Usage**:
- Task API for task management
- Message API for notifications
- Bot API for interactive features

**Sync Logic**:
```
Lark Task Status Changed
  ↓
Check if GitHub issue exists
  ↓
If exists: Update GitHub issue
  ↓
If sync fails: Send Lark notification to responsible person
  ↓
If no GitHub issue: Log warning, notify admin
```

### 5. Local Database (Sync State Manager)
**Purpose**: Maintain mapping and state between GitHub and Lark

**Database Schema** (SQLite):

```sql
-- Tasks table (central source of truth)
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_uuid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,  -- 'open', 'in_progress', 'completed', 'cancelled'
    priority TEXT,  -- 'low', 'medium', 'high', 'critical'
    complexity TEXT,  -- 'low', 'medium', 'high'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    parent_task_id INTEGER,
    FOREIGN KEY (parent_task_id) REFERENCES tasks(id)
);

-- GitHub sync mapping
CREATE TABLE github_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    issue_url TEXT,
    github_status TEXT,
    last_synced_at TIMESTAMP,
    UNIQUE(repo_owner, repo_name, issue_number),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Lark sync mapping
CREATE TABLE lark_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    lark_task_guid TEXT UNIQUE NOT NULL,
    lark_task_url TEXT,
    lark_status TEXT,
    last_synced_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Employee positions
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    github_username TEXT,
    lark_user_id TEXT,
    position TEXT NOT NULL,  -- 'frontend', 'backend', 'fullstack', 'devops', etc.
    expertise TEXT,  -- JSON array of skills
    capacity INTEGER DEFAULT 5  -- Max concurrent tasks
);

-- Task assignments
CREATE TABLE task_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'assigned',  -- 'assigned', 'accepted', 'rejected'
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

-- Sync logs for debugging
CREATE TABLE sync_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    source TEXT NOT NULL,  -- 'github', 'lark', 'manual'
    action TEXT NOT NULL,  -- 'create', 'update', 'delete', 'sync'
    status TEXT NOT NULL,  -- 'success', 'failed', 'pending'
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
```

### 6. Notification Service
**Purpose**: Alert users about important events

**Notification Types**:
- Sync failures (GitHub ↔ Lark mismatch)
- Task assignments
- Status changes requiring attention
- System errors

**Channels**:
- Lark direct messages
- Lark group messages
- Email (optional)

## Data Flow

### Workflow 1: New Task Creation
```
1. User inputs: Project docs + Employee positions + Raw todos
2. Document Processor extracts project context
3. LLM Task Standardizer:
   - Analyzes each todo with context
   - Generates standardized task format
   - Decomposes large tasks into subtasks
   - Suggests assignee based on employee position
4. Tasks saved to local DB
5. GitHub Integration creates issues with labels/assignees
6. Lark Integration creates corresponding tasks
7. Sync mappings recorded in DB
8. Notifications sent to assignees
```

### Workflow 2: Lark Status Update → GitHub Sync
```
1. User updates task status in Lark
2. Lark webhook triggers event
3. System receives Lark task update
4. Query local DB for GitHub issue mapping
5. If mapping exists:
   a. Update GitHub issue via API
   b. Update local DB
   c. Log successful sync
6. If mapping missing or sync fails:
   a. Send Lark notification to task owner
   b. Log error with details
   c. Create manual review task
```

### Workflow 3: GitHub Status Update → Lark Sync
```
1. GitHub webhook receives issue update
2. Query local DB for Lark task mapping
3. If mapping exists:
   a. Update Lark task via API
   b. Update local DB
   c. Log successful sync
4. If sync fails:
   a. Retry with exponential backoff (3 attempts)
   b. Send notification if all retries fail
```

## Configuration

### Environment Variables
```bash
# LLM Configuration
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo
LLM_TEMPERATURE=0.3

# GitHub Configuration
GITHUB_TOKEN=ghp_...
GITHUB_ORG=your-org
GITHUB_REPO=your-repo
GITHUB_WEBHOOK_SECRET=...

# Lark Configuration
LARK_APP_ID=cli_...
LARK_APP_SECRET=...
LARK_BOT_NAME=ProjectPositionBot
LARK_WEBHOOK_VERIFICATION_TOKEN=...

# Database
DATABASE_PATH=./data/project_position.db

# Sync Settings
SYNC_INTERVAL_SECONDS=300
RETRY_MAX_ATTEMPTS=3
RETRY_BACKOFF_FACTOR=2
```

## API Integration Details

### GitHub API Setup
**Required Scopes**:
- `repo` - Full repository access
- `write:discussion` - Create discussions
- `project` - Project board access

**Webhook Events**:
- `issues` - Issue creation/updates
- `issue_comment` - Comments
- `label` - Label changes

### Lark API Setup
**Required Permissions**:
- `task:task` - Task management
- `im:message` - Send messages
- `contact:user.id:readonly` - Read user info

**Event Subscriptions**:
- Task status change
- Task assignment change
- Task comment

## Security Considerations

1. **API Keys**: Store in environment variables, never commit
2. **Webhook Security**: Validate signatures for GitHub/Lark webhooks
3. **Database**: Encrypt sensitive data, regular backups
4. **Rate Limiting**: Implement exponential backoff for API calls
5. **Access Control**: Role-based permissions for system operations

## Scalability Considerations

1. **Task Queue**: Use Celery/Redis for async processing
2. **Caching**: Redis for frequently accessed data
3. **Database**: Migration path to PostgreSQL for production
4. **Monitoring**: Prometheus + Grafana for metrics
5. **Logging**: Structured logging with ELK stack

## Error Handling

1. **Sync Failures**: Retry with exponential backoff, then notify
2. **API Rate Limits**: Queue requests, implement backoff
3. **LLM Failures**: Fallback to simpler processing or manual review
4. **Data Conflicts**: Last-write-wins with conflict log for review

## Future Enhancements

1. **Advanced Assignment**: ML-based assignee prediction
2. **Time Tracking**: Integration with time tracking tools
3. **Analytics Dashboard**: Task completion metrics, team velocity
4. **Smart Notifications**: AI-powered notification summarization
5. **Multi-repo Support**: Manage tasks across multiple repositories
