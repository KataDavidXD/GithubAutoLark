"""Secret redaction utility — strip tokens/PII from logs."""

from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"ghp_[A-Za-z0-9_]{36,}"), "[GITHUB_TOKEN]"),
    (re.compile(r"gho_[A-Za-z0-9_]{36,}"), "[GITHUB_OAUTH]"),
    (re.compile(r"cli_[A-Za-z0-9]{20,}"), "[LARK_CLIENT_ID]"),
    (re.compile(r"[A-Za-z0-9]{32,}"), "[REDACTED_KEY]"),
    (re.compile(r"ou_[A-Za-z0-9]{20,}"), "[LARK_OPEN_ID]"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[EMAIL]"),
]


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
