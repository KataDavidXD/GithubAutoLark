# Demo Outputs

This directory contains redacted output logs from the demo scripts.

## Available Demos

| Script | Output File | Description |
|--------|-------------|-------------|
| `scripts/demo_lark_lifecycle.py` | `lark_lifecycle_output.txt` | Full Lark Bitable lifecycle: create app, table, fields, records, assign member, update status |
| `scripts/demo_github_lifecycle.py` | `github_lifecycle_output.txt` | Full GitHub Issues lifecycle: create, read, update, comment, close |
| `scripts/demo_sync.py` | `sync_demo_output.txt` | Bidirectional sync: local task -> GitHub + Lark, detect status changes, propagate updates |

## Running the Demos

### Prerequisites

1. Copy `.env.template` to `.env` and fill in your credentials:
   - `GITHUB_TOKEN` - GitHub PAT with issue permissions
   - `LARK_MCP_CLIENT_ID` - Lark app client ID
   - `LARK_MCP_CLIENT_SECRET` - Lark app client secret
   - `EMPLOYEE_EMAIL` - Your Lark enterprise email (for assignee demo)

2. Install dependencies:
   ```bash
   pip install requests python-dotenv
   ```

3. Ensure Node.js is available (for `npx @larksuiteoapi/lark-mcp`).

### Running

From the repository root:

```powershell
# Set UTF-8 encoding (Windows)
$env:PYTHONUTF8=1
$env:PYTHONIOENCODING="utf-8"

# Run Lark lifecycle demo
python scripts/demo_lark_lifecycle.py

# Run GitHub lifecycle demo
python scripts/demo_github_lifecycle.py

# Run bidirectional sync demo
python scripts/demo_sync.py
```

## Output Notes

- All outputs are **redacted** to remove secrets, emails, and personal identifiers.
- Timestamps in filenames indicate when the demo was run.
- Errors are captured and included in the output.

## Security

- **Never commit `.env`** - it contains secrets.
- Output files in this directory are safe to share (redacted).
- The `src/redact.py` module handles redaction automatically.
