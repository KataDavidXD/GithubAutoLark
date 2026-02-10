"""
Task service for managing tasks in the database
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.core import db
from src.models import Task, Employee, TaskAssignment

logger = logging.getLogger(__name__)


class TaskService:
    """Service for task CRUD operations"""
    
    @staticmethod
    def create_task(task: Task) -> int:
        """Create a new task"""
        query = """
            INSERT INTO tasks (
                task_uuid, title, description, status, priority, complexity,
                parent_task_id, due_date, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            task.task_uuid,
            task.title,
            task.description,
            task.status,
            task.priority,
            task.complexity,
            task.parent_task_id,
            task.due_date.isoformat() if task.due_date else None,
            task.created_by
        )
        
        task_id = db.execute_write(query, params)
        logger.info(f"Created task {task_id}: {task.title}")
        return task_id
    
    @staticmethod
    def get_task(task_id: int) -> Optional[Task]:
        """Get task by ID"""
        query = "SELECT * FROM tasks WHERE id = ?"
        result = db.execute_one(query, (task_id,))
        
        if result:
            return Task.from_dict(result)
        return None
    
    @staticmethod
    def get_task_by_uuid(task_uuid: str) -> Optional[Task]:
        """Get task by UUID"""
        query = "SELECT * FROM tasks WHERE task_uuid = ?"
        result = db.execute_one(query, (task_uuid,))
        
        if result:
            return Task.from_dict(result)
        return None
    
    @staticmethod
    def update_task(task_id: int, **updates) -> bool:
        """Update task fields"""
        allowed_fields = [
            'title', 'description', 'status', 'priority', 'complexity',
            'due_date', 'completed_at', 'parent_task_id'
        ]
        
        # Filter out fields that aren't in the task model
        updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        # Build update query
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        query = f"UPDATE tasks SET {set_clause} WHERE id = ?"
        params = tuple(updates.values()) + (task_id,)
        
        rows_affected = db.execute_write(query, params)
        logger.info(f"Updated task {task_id}: {updates}")
        return rows_affected > 0
    
    @staticmethod
    def list_tasks(
        status: Optional[str] = None,
        assignee_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Task]:
        """List tasks with optional filters"""
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if assignee_id:
            query += """ AND id IN (
                SELECT task_id FROM task_assignments WHERE employee_id = ?
            )"""
            params.append(assignee_id)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        results = db.execute_query(query, tuple(params))
        return [Task.from_dict(row) for row in results]
    
    @staticmethod
    def assign_task(task_id: int, employee_id: int, assigned_by: str = "system") -> int:
        """Assign task to employee"""
        query = """
            INSERT INTO task_assignments (task_id, employee_id, assigned_by)
            VALUES (?, ?, ?)
        """
        
        assignment_id = db.execute_write(query, (task_id, employee_id, assigned_by))
        logger.info(f"Assigned task {task_id} to employee {employee_id}")
        return assignment_id
    
    @staticmethod
    def get_task_assignees(task_id: int) -> List[Employee]:
        """Get all employees assigned to a task"""
        query = """
            SELECT e.* FROM employees e
            JOIN task_assignments ta ON e.id = ta.employee_id
            WHERE ta.task_id = ?
        """
        
        results = db.execute_query(query, (task_id,))
        return [Employee.from_dict(row) for row in results]
    
    @staticmethod
    def mark_completed(task_id: int) -> bool:
        """Mark task as completed"""
        query = """
            UPDATE tasks 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        
        rows_affected = db.execute_write(query, (task_id,))
        logger.info(f"Marked task {task_id} as completed")
        return rows_affected > 0


class EmployeeService:
    """Service for employee CRUD operations"""
    
    @staticmethod
    def create_employee(employee: Employee) -> int:
        """Create a new employee"""
        query = """
            INSERT INTO employees (
                name, email, github_username, lark_user_id, lark_union_id,
                position, expertise, max_concurrent_tasks, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            employee.name,
            employee.email,
            employee.github_username,
            employee.lark_user_id,
            employee.lark_union_id,
            employee.position,
            employee.expertise,
            employee.max_concurrent_tasks,
            employee.is_active
        )
        
        employee_id = db.execute_write(query, params)
        logger.info(f"Created employee {employee_id}: {employee.name}")
        return employee_id
    
    @staticmethod
    def get_employee(employee_id: int) -> Optional[Employee]:
        """Get employee by ID"""
        query = "SELECT * FROM employees WHERE id = ?"
        result = db.execute_one(query, (employee_id,))
        
        if result:
            return Employee.from_dict(result)
        return None
    
    @staticmethod
    def get_employee_by_github(github_username: str) -> Optional[Employee]:
        """Get employee by GitHub username"""
        query = "SELECT * FROM employees WHERE github_username = ?"
        result = db.execute_one(query, (github_username,))
        
        if result:
            return Employee.from_dict(result)
        return None
    
    @staticmethod
    def get_employee_by_lark(lark_user_id: str) -> Optional[Employee]:
        """Get employee by Lark user ID"""
        query = "SELECT * FROM employees WHERE lark_user_id = ?"
        result = db.execute_one(query, (lark_user_id,))
        
        if result:
            return Employee.from_dict(result)
        return None
    
    @staticmethod
    def list_employees(position: Optional[str] = None, is_active: bool = True) -> List[Employee]:
        """List employees with optional filters"""
        query = "SELECT * FROM employees WHERE is_active = ?"
        params = [is_active]
        
        if position:
            query += " AND position = ?"
            params.append(position)
        
        query += " ORDER BY name"
        
        results = db.execute_query(query, tuple(params))
        return [Employee.from_dict(row) for row in results]
    
    @staticmethod
    def get_employee_workload(employee_id: int) -> Dict[str, Any]:
        """Get employee's current workload"""
        query = """
            SELECT 
                e.max_concurrent_tasks,
                COUNT(ta.id) as assigned_tasks
            FROM employees e
            LEFT JOIN task_assignments ta ON e.id = ta.employee_id
            LEFT JOIN tasks t ON ta.task_id = t.id
            WHERE e.id = ? AND (t.status IN ('open', 'in_progress') OR t.status IS NULL)
            GROUP BY e.id
        """
        
        result = db.execute_one(query, (employee_id,))
        
        if result:
            return {
                "max_concurrent_tasks": result["max_concurrent_tasks"],
                "assigned_tasks": result["assigned_tasks"],
                "available_capacity": result["max_concurrent_tasks"] - result["assigned_tasks"]
            }
        
        return {"max_concurrent_tasks": 0, "assigned_tasks": 0, "available_capacity": 0}
