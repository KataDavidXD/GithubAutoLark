# Quick Start Guide

Get started with the Project Position System in 5 minutes.

## 1. Installation

```bash
# Clone and setup
git clone <your-repo-url>
cd project-position-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 2. Configuration

```bash
# Create environment file
cp .env.example .env

# Edit .env with your credentials
# Minimum required:
# - GITHUB_TOKEN (for GitHub sync)
# - GITHUB_ORG and GITHUB_REPO
# - LARK_APP_ID and LARK_APP_SECRET (for Lark sync)
# - OPENAI_API_KEY (optional, for LLM features)
```

## 3. Initialize Database

```bash
python -c "from src.core import db; print('Database initialized at', db.db_path)"
```

## 4. Run Example

```bash
python example_usage.py
```

This will:
- Create sample employees
- Standardize a task using LLM
- Create the task in the database
- Assign it to an employee
- Sync to GitHub and Lark

## 5. API Integration Setup

### GitHub Setup

1. Create a Personal Access Token:
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Generate new token with `repo` scope
   - Copy token to `.env` as `GITHUB_TOKEN`

2. Set your repository:
   ```bash
   GITHUB_ORG=your-org
   GITHUB_REPO=your-repo
   ```

See [GITHUB_API_GUIDE.md](GITHUB_API_GUIDE.md) for detailed setup.

### Lark Setup

1. Create a Lark App:
   - Go to [Lark Open Platform](https://open.feishu.cn)
   - Create custom app
   - Get App ID and App Secret

2. Configure permissions:
   - `task:task` - Task management
   - `im:message` - Send messages
   - `contact:user.id:readonly` - User info

3. Add credentials to `.env`:
   ```bash
   LARK_APP_ID=cli_xxxxxxxxxx
   LARK_APP_SECRET=your_secret_here
   ```

See [LARK_API_GUIDE.md](LARK_API_GUIDE.md) for detailed setup.

## 6. Basic Usage

### Create and Sync a Task

```python
from src.services import TaskService, SyncService
from src.models import Task

# Create task
task = Task(
    title="Implement feature X",
    description="Detailed description",
    priority="high",
    complexity="medium"
)

task_service = TaskService()
task_id = task_service.create_task(task)
task.id = task_id

# Sync to GitHub and Lark
sync_service = SyncService()
sync_service.sync_task_to_github(task)
sync_service.sync_task_to_lark(task)
```

### Use LLM to Standardize Tasks

```python
from src.services import LLMService

llm_service = LLMService()

raw_task = "need to add login page asap"
standardized = llm_service.standardize_task(raw_task)

print(standardized["title"])        # "Implement Login Page"
print(standardized["priority"])     # "critical"
print(standardized["complexity"])   # "medium"
```

### List Tasks

```python
from src.services import TaskService

task_service = TaskService()

# Get all open tasks
open_tasks = task_service.list_tasks(status="open")

# Get tasks for specific employee
my_tasks = task_service.list_tasks(assignee_id=1)
```

## 7. Webhooks (Optional)

To enable real-time sync, set up webhooks:

### GitHub Webhook

1. Go to Repository → Settings → Webhooks
2. Add webhook:
   - URL: `https://your-domain.com/webhooks/github`
   - Content type: `application/json`
   - Secret: Set in `.env` as `GITHUB_WEBHOOK_SECRET`
   - Events: Issues, Issue comments

### Lark Webhook

1. Go to App → Event Subscriptions
2. Set Request URL: `https://your-domain.com/webhooks/lark`
3. Subscribe to events:
   - `task.task.updated_v2`
   - `task.task.created_v2`

## Troubleshooting

### Database Issues

```bash
# Reset database
rm data/project_position.db
python -c "from src.core import db"
```

### Check Sync Logs

```python
from src.core import db

logs = db.execute_query(
    "SELECT * FROM sync_logs WHERE status = 'failed' ORDER BY created_at DESC LIMIT 5"
)
for log in logs:
    print(f"{log['created_at']}: {log['error_message']}")
```

### API Rate Limits

```python
from src.integrations import GitHubClient

client = GitHubClient()
rate_limit = client.check_rate_limit()
print(f"Remaining: {rate_limit['resources']['core']['remaining']}")
```

## Next Steps

- Read [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for architecture details
- Review API guides for [GitHub](GITHUB_API_GUIDE.md) and [Lark](LARK_API_GUIDE.md)
- Customize employee positions and expertise in the database
- Set up automated sync jobs (cron/scheduled tasks)
- Deploy webhook server for real-time updates

## Support

- Check database with: `sqlite3 data/project_position.db`
- View logs in: `logs/` directory
- Review sync status: Query `sync_logs` table

For more help, see [README.md](README.md)
