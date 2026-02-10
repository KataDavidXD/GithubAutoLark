"""
Example usage of the Project Position System

This script demonstrates how to use the system to:
1. Create employees
2. Standardize tasks with LLM
3. Create tasks in the database
4. Assign tasks to employees
5. Sync tasks to GitHub and Lark
"""

import logging
from src.config import settings
from src.core import db
from src.models import Task, Employee
from src.services import TaskService, EmployeeService, LLMService, SyncService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main example workflow"""
    
    print("=" * 80)
    print("Project Position System - Example Usage")
    print("=" * 80)
    print()
    
    # Initialize services
    task_service = TaskService()
    employee_service = EmployeeService()
    llm_service = LLMService()
    sync_service = SyncService()
    
    # Step 1: Create employees (if not exists)
    print("Step 1: Setting up team members...")
    print("-" * 80)
    
    employees_data = [
        {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "github_username": "alice",
            "position": "backend",
            "expertise": '["Python", "Django", "PostgreSQL", "Redis"]'
        },
        {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "github_username": "bob",
            "position": "frontend",
            "expertise": '["React", "TypeScript", "CSS", "Next.js"]'
        }
    ]
    
    for emp_data in employees_data:
        existing = employee_service.get_employee_by_github(emp_data["github_username"])
        if not existing:
            emp = Employee(**emp_data)
            emp_id = employee_service.create_employee(emp)
            print(f"✓ Created employee: {emp_data['name']} (ID: {emp_id})")
        else:
            print(f"✓ Employee already exists: {emp_data['name']} (ID: {existing.id})")
    
    print()
    
    # Step 2: Standardize a raw task
    print("Step 2: Standardizing task with LLM...")
    print("-" * 80)
    
    raw_task = """
    We need to implement user authentication for the web app.
    Should support login, logout, and token refresh.
    Use JWT tokens and store them securely.
    """
    
    print(f"Raw task input:\n{raw_task}\n")
    
    # Get available employees for context
    all_employees = employee_service.list_employees()
    employee_positions = [
        {"name": e.name, "position": e.position, "expertise": e.expertise}
        for e in all_employees
    ]
    
    standardized = llm_service.standardize_task(
        raw_task=raw_task,
        project_context="Web application project for task management",
        employee_positions=employee_positions
    )
    
    print("Standardized task:")
    print(f"  Title: {standardized['title']}")
    print(f"  Priority: {standardized['priority']}")
    print(f"  Complexity: {standardized['complexity']}")
    print(f"  Suggested Assignee: {standardized.get('suggested_assignee', 'N/A')}")
    print()
    
    # Step 3: Create task in database
    print("Step 3: Creating task in database...")
    print("-" * 80)
    
    task = Task(
        title=standardized["title"],
        description=standardized["description"],
        priority=standardized["priority"],
        complexity=standardized["complexity"],
        created_by="system"
    )
    
    task_id = task_service.create_task(task)
    task.id = task_id
    print(f"✓ Created task ID: {task_id}")
    print()
    
    # Step 4: Assign task to employee
    print("Step 4: Assigning task to employee...")
    print("-" * 80)
    
    # Find backend developer
    backend_dev = next((e for e in all_employees if e.position == "backend"), None)
    
    if backend_dev:
        task_service.assign_task(task_id, backend_dev.id, "system")
        print(f"✓ Assigned task to: {backend_dev.name}")
        
        # Check workload
        workload = employee_service.get_employee_workload(backend_dev.id)
        print(f"  Current workload: {workload['assigned_tasks']}/{workload['max_concurrent_tasks']} tasks")
    else:
        print("⚠ No backend developer found")
    
    print()
    
    # Step 5: Sync to GitHub
    print("Step 5: Syncing to GitHub...")
    print("-" * 80)
    
    if settings.GITHUB_SYNC_ENABLED and settings.GITHUB_TOKEN:
        github_issue = sync_service.sync_task_to_github(task)
        if github_issue:
            print(f"✓ Created GitHub issue #{github_issue.issue_number}")
            print(f"  URL: {github_issue.issue_url}")
        else:
            print("⚠ Failed to sync to GitHub (check logs)")
    else:
        print("⚠ GitHub sync disabled or not configured")
    
    print()
    
    # Step 6: Sync to Lark
    print("Step 6: Syncing to Lark...")
    print("-" * 80)
    
    if settings.LARK_SYNC_ENABLED and settings.LARK_APP_ID:
        lark_task = sync_service.sync_task_to_lark(task)
        if lark_task:
            print(f"✓ Created Lark task: {lark_task.lark_task_guid}")
            if lark_task.lark_task_url:
                print(f"  URL: {lark_task.lark_task_url}")
        else:
            print("⚠ Failed to sync to Lark (check logs)")
    else:
        print("⚠ Lark sync disabled or not configured")
    
    print()
    
    # Step 7: List all tasks
    print("Step 7: Listing all active tasks...")
    print("-" * 80)
    
    active_tasks = task_service.list_tasks(status="open")
    print(f"Found {len(active_tasks)} open task(s):")
    for t in active_tasks[:5]:  # Show first 5
        assignees = task_service.get_task_assignees(t.id)
        assignee_names = ", ".join([a.name for a in assignees]) if assignees else "Unassigned"
        print(f"  • [{t.priority}] {t.title} (Assigned to: {assignee_names})")
    
    print()
    print("=" * 80)
    print("Example completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
