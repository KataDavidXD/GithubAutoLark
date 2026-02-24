# Input Folder

Place your project documents here. The LLM agent will parse and standardize them.

## Required Files

| File | Description |
|------|-------------|
| `project_structure.md` | Your project's architecture, modules, tech stack |
| `todos.md` | Fuzzy task list, assignments, priorities (can be rough notes) |

## Optional Files

| File | Description |
|------|-------------|
| `team.md` | Team member info (names, emails, roles) |
| `config.yaml` | Override GitHub/Lark targets (optional) |

## How It Works

1. You write natural markdown documents describing your project and todos
2. The LLM parses these fuzzy documents into structured tasks
3. Tasks are synced to GitHub Issues and Lark Bitable
4. Assignees are resolved automatically (email -> GitHub username / Lark open_id)

## Example

See the example files in this folder for reference.
