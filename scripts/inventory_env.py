import os
from pathlib import Path

from dotenv import dotenv_values


REPO_ROOT = Path(__file__).resolve().parents[1]


def _mask_presence(val: str | None) -> str:
    if val is None:
        return "MISSING"
    if val == "":
        return "EMPTY"
    return f"SET(len={len(val)})"


def main() -> None:
    env_path = REPO_ROOT / ".env"
    template_path = REPO_ROOT / ".env.template"

    print("Inventory (keys only). Values are not printed.")
    print(f"- repo_root: {REPO_ROOT}")
    print(f"- .env exists: {env_path.exists()}")
    print(f"- .env.template exists: {template_path.exists()}")
    print("")

    if env_path.exists():
        env = dotenv_values(env_path)
    else:
        env = {}

    # Merge OS env with .env (OS env wins) for presence checks only
    combined = dict(env)
    combined.update({k: v for k, v in os.environ.items() if k in combined or k.startswith("LARK_") or k.startswith("GITHUB_") or k.startswith("LLM_")})

    keys_of_interest = [
        "GITHUB_TOKEN",
        "OWNER",
        "REPO",
        "LARK_MCP_CLIENT_ID",
        "LARK_MCP_CLIENT_SECRET",
        "LARK_MCP_DOMAIN",
        "LARK_MCP_USE_OAUTH",
        "LARK_APP_TOKEN",
        "LARK_TASKS_TABLE_ID",
        "LARK_NOTIFY_CHAT_ID",
        "LARK_FIELD_TITLE",
        "LARK_FIELD_STATUS",
        "LARK_FIELD_ASSIGNEE",
        "LARK_FIELD_GITHUB_ISSUE",
        "LARK_FIELD_LAST_SYNC",
        "EMPLOYEE_EMAIL",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "DEFAULT_LLM",
    ]

    print("Key presence:")
    for k in keys_of_interest:
        print(f"- {k}: {_mask_presence(combined.get(k))}")


if __name__ == "__main__":
    main()

