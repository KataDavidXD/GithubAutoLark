"""
LLM Processor - Parse fuzzy markdown documents into structured todos.

Uses OpenAI-compatible API to extract structured data from natural language.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import requests

from src.config import get_llm_config, LLMConfig


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a project management assistant. Your job is to parse project documents and extract structured task information.

Given project structure documents and fuzzy todo notes, extract:
1. **Tasks**: Individual actionable items with title, description, priority, status
2. **Members**: Team member information (name, email, role)
3. **Assignments**: Which tasks are assigned to which members

Output MUST be valid JSON matching the schema below."""

EXTRACTION_PROMPT = """Parse the following project documents and extract structured information.

## Project Structure Document:
{project_doc}

## Todo / Tasks Document:
{todos_doc}

## Team Document (if available):
{team_doc}

---

Extract and return a JSON object with this EXACT structure:

```json
{{
  "project": {{
    "name": "Project name",
    "description": "Brief description"
  }},
  "members": [
    {{
      "name": "Full Name",
      "email": "email@example.com",
      "github_username": "github-user or null",
      "role": "developer/manager/etc"
    }}
  ],
  "todos": [
    {{
      "title": "Short task title",
      "body": "Detailed description",
      "assignee_email": "email@example.com or null",
      "priority": "high/medium/low",
      "status": "To Do/In Progress/Done",
      "labels": ["label1", "label2"]
    }}
  ]
}}
```

Rules:
- Extract ALL actionable tasks, not just explicitly listed ones
- Infer assignees from context (e.g., "Yang needs to work on X" -> assign to Yang)
- Default status is "To Do" unless stated otherwise
- Default priority is "medium" unless indicated as urgent/blocking/low
- Use labels to categorize (feature, bug, testing, docs, etc.)
- If email is mentioned anywhere, use it; otherwise leave assignee_email as null

Return ONLY the JSON object, no other text."""


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

@dataclass
class LLMProcessor:
    """
    Process fuzzy markdown documents using LLM.
    """
    
    config: LLMConfig
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_llm_config()
    
    def _call_llm(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        """Call the LLM API."""
        if not self.config.api_key:
            raise ValueError("LLM_API_KEY not configured in .env")
        
        base_url = self.config.base_url or "https://api.openai.com/v1"
        model = self.config.default_model or "gpt-4o-mini"
        
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=60,
        )
        
        response.raise_for_status()
        data = response.json()
        
        return data["choices"][0]["message"]["content"]
    
    def parse_documents(
        self,
        project_doc: str,
        todos_doc: str,
        team_doc: str = "",
    ) -> dict[str, Any]:
        """
        Parse project documents and extract structured data.
        
        Args:
            project_doc: Project structure markdown
            todos_doc: Fuzzy todo/task markdown
            team_doc: Optional team member markdown
        
        Returns:
            Structured dict with project, members, and todos
        """
        prompt = EXTRACTION_PROMPT.format(
            project_doc=project_doc or "(No project document provided)",
            todos_doc=todos_doc or "(No todos document provided)",
            team_doc=team_doc or "(No team document provided)",
        )
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        
        response = self._call_llm(messages)
        
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_str = response.strip()
        
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try to fix common issues
            json_str = json_str.replace("'", '"')
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {response[:500]}")
        
        return result
    
    def standardize_todos(self, parsed_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Standardize parsed todos into a consistent format.
        """
        todos = parsed_data.get("todos", [])
        standardized = []
        
        for todo in todos:
            std_todo = {
                "title": todo.get("title", "Untitled Task"),
                "body": todo.get("body", ""),
                "assignee_email": todo.get("assignee_email"),
                "priority": todo.get("priority", "medium").lower(),
                "status": self._normalize_status(todo.get("status", "To Do")),
                "labels": todo.get("labels", []),
            }
            standardized.append(std_todo)
        
        return standardized
    
    def _normalize_status(self, status: str) -> str:
        """Normalize status string."""
        status_lower = status.lower().replace(" ", "").replace("-", "").replace("_", "")
        
        if status_lower in ("todo", "new", "open", "pending"):
            return "To Do"
        elif status_lower in ("inprogress", "doing", "wip", "working"):
            return "In Progress"
        elif status_lower in ("done", "completed", "closed", "finished"):
            return "Done"
        else:
            return "To Do"


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def parse_project_docs(
    project_doc: str,
    todos_doc: str,
    team_doc: str = "",
) -> dict[str, Any]:
    """
    One-shot parsing of project documents.
    
    Returns dict with 'project', 'members', 'todos'.
    """
    processor = LLMProcessor()
    return processor.parse_documents(project_doc, todos_doc, team_doc)


if __name__ == "__main__":
    # Test with example files
    from pathlib import Path
    
    input_dir = Path(__file__).resolve().parents[1] / "input"
    
    project_doc = ""
    todos_doc = ""
    team_doc = ""
    
    project_file = input_dir / "example_project_structure.md"
    if project_file.exists():
        project_doc = project_file.read_text(encoding="utf-8")
    
    todos_file = input_dir / "example_todos.md"
    if todos_file.exists():
        todos_doc = todos_file.read_text(encoding="utf-8")
    
    team_file = input_dir / "example_team.md"
    if team_file.exists():
        team_doc = team_file.read_text(encoding="utf-8")
    
    print("Parsing documents with LLM...")
    result = parse_project_docs(project_doc, todos_doc, team_doc)
    
    print("\nProject:")
    print(f"  {result.get('project', {})}")
    
    print("\nMembers:")
    for m in result.get("members", []):
        print(f"  - {m}")
    
    print("\nTodos:")
    for t in result.get("todos", []):
        print(f"  - {t.get('title')} [{t.get('priority')}] -> {t.get('assignee_email')}")
