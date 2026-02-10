# Project Position System

An intelligent task management and distribution platform that processes project documentation, assigns tasks to employees, and maintains synchronization between GitHub Issues and Lark (Feishu) workspace.

## Features

- **Intelligent Task Standardization**: Uses LLM (GPT-4/Claude) to standardize and normalize task descriptions
- **Automatic Task Decomposition**: Breaks down large tasks into smaller, actionable issues
- **GitHub Integration**: Auto-creates and syncs GitHub Issues
- **Lark Integration**: Bidirectional sync with Lark Tasks
- **Smart Assignment**: AI-powered task assignment based on employee skills and workload
- **Sync Management**: Maintains consistency between GitHub and Lark with conflict resolution
- **Notification System**: Alerts for sync failures and status changes

## System Architecture

```
Input Layer → LLM Processing → Sync Layer (GitHub ↔ Local DB ↔ Lark) → Notifications
```

For detailed architecture, see [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md)

## Setup

### 1. Prerequisites

- Python 3.9+
- GitHub account with repository access
- Lark (Feishu) workspace and app credentials
- OpenAI API key (optional, for LLM features)

### 2. Installation

```bash
# Clone the repository
git clone <repository-url>
cd project-position-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env and fill in your credentials
nano .env
```

Required configuration:
- `GITHUB_TOKEN`: GitHub Personal Access Token
- `GITHUB_ORG` and `GITHUB_REPO`: Target repository
- `LARK_APP_ID` and `LARK_APP_SECRET`: Lark app credentials
- `OPENAI_API_KEY`: OpenAI API key (optional)

### 4. Database Initialization

```bash
# Initialize database
python -c "from src.core import db; print('Database initialized')"
```

## Usage

### Command Line Interface

```python
from src.services import TaskService, LLMService, SyncService
from src.models import Task

# Create a task
task_service = TaskService()
llm_service = LLMService()

# Standardize a raw task
raw_task = "Implement user authentication with JWT"
standardized = llm_service.standardize_task(raw_task)

# Create task in database
task = Task(
    title=standardized["title"],
    description=standardized["description"],
    priority=standardized["priority"],
    complexity=standardized["complexity"]
)
task_id = task_service.create_task(task)

# Sync to GitHub and Lark
sync_service = SyncService()
sync_service.sync_task_to_github(task)
sync_service.sync_task_to_lark(task)
```

### API Server (Coming Soon)

Run the webhook server to handle real-time updates:

```bash
python -m src.api.server
```

## API Integration Guides

- [GitHub API Guide](GITHUB_API_GUIDE.md) - Setup and usage of GitHub API
- [Lark API Guide](LARK_API_GUIDE.md) - Setup and usage of Lark API

## Project Structure

```
project-position-system/
├── src/
│   ├── config/          # Configuration management
│   ├── core/            # Core utilities (database, etc.)
│   ├── models/          # Data models
│   ├── integrations/    # GitHub and Lark API clients
│   ├── services/        # Business logic
│   ├── api/             # API endpoints and webhooks
│   └── utils/           # Helper functions
├── data/                # Database and uploaded files
├── logs/                # Application logs
├── tests/               # Unit and integration tests
├── database_schema.sql  # Database schema
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Database Schema

The system uses SQLite with the following main tables:

- `tasks` - Central task storage
- `employees` - Team member information
- `task_assignments` - Task-to-employee mapping
- `github_issues` - GitHub issue sync mapping
- `lark_tasks` - Lark task sync mapping
- `sync_logs` - Sync operation audit log

See [database_schema.sql](database_schema.sql) for complete schema.

## Workflow

### 1. Task Creation and Standardization

```
User Input (Raw Task + Project Docs + Employee Info)
  ↓
LLM Processing (Standardize, Classify, Decompose)
  ↓
Create Tasks in Local Database
```

### 2. Synchronization

```
Local Task Created
  ↓
Create GitHub Issue (with assignees, labels)
  ↓
Create Lark Task (with assignees, due date)
  ↓
Store Mappings in Database
```

### 3. Bidirectional Sync

```
Lark Task Status Changed
  ↓
Webhook → Update Local DB → Update GitHub Issue
  ↓
If Sync Fails → Send Lark Notification
```

## Security

- Store API keys in environment variables (never commit `.env`)
- Validate webhook signatures (GitHub and Lark)
- Use HTTPS for webhook endpoints
- Implement rate limiting for API calls
- Regular database backups

## Troubleshooting

### Database Issues

```bash
# Reset database
rm data/project_position.db
python -c "from src.core import db; print('Database reset')"
```

### Sync Issues

Check sync logs in database:
```sql
SELECT * FROM sync_logs WHERE status = 'failed' ORDER BY created_at DESC LIMIT 10;
```

### API Rate Limits

- GitHub: 5,000 requests/hour
- Lark: 200 requests/minute

Monitor rate limits and implement backoff strategies.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/`
5. Submit a pull request

## License

See [LICENSE](LICENSE) file.

## Support

For issues and questions:
- Check [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for architecture details
- Review API guides: [GitHub](GITHUB_API_GUIDE.md) and [Lark](LARK_API_GUIDE.md)
- Open an issue in the repository

## Roadmap

- [ ] Web UI for task management
- [ ] Advanced ML-based assignee prediction
- [ ] Multi-repository support
- [ ] Analytics dashboard
- [ ] Time tracking integration
- [ ] Slack integration
- [ ] Email notifications
