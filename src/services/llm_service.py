"""
LLM service for task standardization and processing
"""
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.config import settings
from src.core import db

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM-based task processing"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        
        if not self.api_key:
            logger.warning("OpenAI API key not set. LLM features will be disabled.")
            self.client = None
        else:
            try:
                import openai
                self.client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                logger.error("OpenAI package not installed. Run: pip install openai")
                self.client = None
    
    def standardize_task(
        self,
        raw_task: str,
        project_context: Optional[str] = None,
        employee_positions: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Standardize a raw task description using LLM
        
        Returns:
            {
                "title": str,
                "description": str,
                "acceptance_criteria": List[str],
                "complexity": str,  # low, medium, high
                "priority": str,    # low, medium, high, critical
                "suggested_assignee": str,  # employee name or position
                "labels": List[str],
                "subtasks": List[Dict]  # If task should be broken down
            }
        """
        if not self.client:
            # Fallback: simple parsing
            return self._fallback_standardization(raw_task)
        
        try:
            # Build prompt
            prompt = self._build_standardization_prompt(raw_task, project_context, employee_positions)
            
            # Call OpenAI API
            start_time = datetime.now()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a project management AI that standardizes task descriptions."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=settings.LLM_MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Parse response
            result = json.loads(response.choices[0].message.content)
            
            # Log processing
            self._log_llm_processing(
                input_text=raw_task,
                output_text=response.choices[0].message.content,
                model_name=self.model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                processing_time_ms=int(processing_time),
                status="completed"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to standardize task with LLM: {e}")
            self._log_llm_processing(
                input_text=raw_task,
                output_text="",
                status="failed",
                error_message=str(e)
            )
            # Fallback to simple parsing
            return self._fallback_standardization(raw_task)
    
    def decompose_task(self, task_description: str, project_context: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Decompose a large task into smaller subtasks
        
        Returns:
            List of task dictionaries with title, description, complexity, etc.
        """
        if not self.client:
            return []
        
        try:
            prompt = self._build_decomposition_prompt(task_description, project_context)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a project management AI that breaks down complex tasks into smaller, actionable subtasks."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=settings.LLM_MAX_TOKENS,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("subtasks", [])
            
        except Exception as e:
            logger.error(f"Failed to decompose task with LLM: {e}")
            return []
    
    def suggest_assignee(
        self,
        task_description: str,
        available_employees: List[Dict[str, Any]],
        workload_info: Optional[Dict[str, int]] = None
    ) -> Optional[str]:
        """
        Suggest the best assignee for a task based on skills and workload
        
        Returns:
            Employee name or None
        """
        if not self.client or not available_employees:
            return None
        
        try:
            prompt = self._build_assignment_prompt(task_description, available_employees, workload_info)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a project management AI that assigns tasks to team members based on their skills and current workload."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("assignee")
            
        except Exception as e:
            logger.error(f"Failed to suggest assignee with LLM: {e}")
            return None
    
    # Private helper methods
    
    def _build_standardization_prompt(
        self,
        raw_task: str,
        project_context: Optional[str],
        employee_positions: Optional[List[Dict[str, str]]]
    ) -> str:
        """Build prompt for task standardization"""
        prompt_parts = [
            "Please standardize the following task description into a structured format.",
            "",
            "Raw task:",
            raw_task,
            ""
        ]
        
        if project_context:
            prompt_parts.extend([
                "Project context:",
                project_context,
                ""
            ])
        
        if employee_positions:
            prompt_parts.extend([
                "Available team members:",
                json.dumps(employee_positions, indent=2),
                ""
            ])
        
        prompt_parts.extend([
            "Please provide a JSON response with the following structure:",
            "{",
            '  "title": "Clear, concise task title",',
            '  "description": "Detailed task description with context",',
            '  "acceptance_criteria": ["Criterion 1", "Criterion 2", ...],',
            '  "complexity": "low|medium|high",',
            '  "priority": "low|medium|high|critical",',
            '  "suggested_assignee": "employee name or position",',
            '  "labels": ["label1", "label2", ...],',
            '  "should_decompose": true|false,',
            '  "estimated_hours": number',
            "}"
        ])
        
        return "\n".join(prompt_parts)
    
    def _build_decomposition_prompt(self, task_description: str, project_context: Optional[str]) -> str:
        """Build prompt for task decomposition"""
        prompt_parts = [
            "Please break down the following large task into smaller, actionable subtasks.",
            "",
            "Task:",
            task_description,
            ""
        ]
        
        if project_context:
            prompt_parts.extend([
                "Project context:",
                project_context,
                ""
            ])
        
        prompt_parts.extend([
            "Please provide a JSON response with the following structure:",
            "{",
            '  "subtasks": [',
            '    {',
            '      "title": "Subtask title",',
            '      "description": "Subtask description",',
            '      "complexity": "low|medium|high",',
            '      "order": 1,',
            '      "dependencies": []',
            '    },',
            '    ...',
            '  ]',
            "}"
        ])
        
        return "\n".join(prompt_parts)
    
    def _build_assignment_prompt(
        self,
        task_description: str,
        available_employees: List[Dict[str, Any]],
        workload_info: Optional[Dict[str, int]]
    ) -> str:
        """Build prompt for assignee suggestion"""
        prompt_parts = [
            "Please suggest the best team member to assign the following task to.",
            "",
            "Task:",
            task_description,
            "",
            "Available team members:",
            json.dumps(available_employees, indent=2),
            ""
        ]
        
        if workload_info:
            prompt_parts.extend([
                "Current workload (number of active tasks):",
                json.dumps(workload_info, indent=2),
                ""
            ])
        
        prompt_parts.extend([
            "Please provide a JSON response with the following structure:",
            "{",
            '  "assignee": "employee name",',
            '  "reasoning": "Brief explanation of why this person is the best fit"',
            "}"
        ])
        
        return "\n".join(prompt_parts)
    
    def _fallback_standardization(self, raw_task: str) -> Dict[str, Any]:
        """Fallback standardization when LLM is not available"""
        # Simple heuristics
        lines = raw_task.strip().split("\n")
        title = lines[0][:100] if lines else "Untitled Task"
        description = raw_task
        
        # Guess complexity based on length
        if len(raw_task) < 100:
            complexity = "low"
        elif len(raw_task) < 300:
            complexity = "medium"
        else:
            complexity = "high"
        
        # Guess priority based on keywords
        priority = "medium"
        urgent_keywords = ["urgent", "critical", "asap", "immediately", "blocker"]
        high_keywords = ["important", "priority", "needed soon"]
        
        raw_lower = raw_task.lower()
        if any(keyword in raw_lower for keyword in urgent_keywords):
            priority = "critical"
        elif any(keyword in raw_lower for keyword in high_keywords):
            priority = "high"
        
        return {
            "title": title,
            "description": description,
            "acceptance_criteria": [],
            "complexity": complexity,
            "priority": priority,
            "suggested_assignee": None,
            "labels": [],
            "should_decompose": False,
            "estimated_hours": None
        }
    
    def _log_llm_processing(
        self,
        input_text: str,
        output_text: str,
        model_name: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        processing_time_ms: Optional[int] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
        task_id: Optional[int] = None
    ):
        """Log LLM processing to database"""
        query = """
            INSERT INTO llm_processing (
                task_id, input_text, output_text, model_name,
                prompt_tokens, completion_tokens, total_tokens,
                processing_time_ms, status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        db.execute_write(query, (
            task_id,
            input_text[:1000],  # Truncate for storage
            output_text[:2000],
            model_name,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            processing_time_ms,
            status,
            error_message
        ))
