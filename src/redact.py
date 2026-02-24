import re
from typing import Iterable


_DEFAULT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # GitHub PATs (classic and fine-grained commonly include "github_pat_")
    (re.compile(r"github_pat_[A-Za-z0-9_]+"), "github_pat_[REDACTED]"),
    # OpenAI-style keys (avoid leaking if present)
    (re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"), "sk-[REDACTED]"),
    # Bearer tokens
    (re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9_\-\.=]+", re.IGNORECASE), "Authorization: Bearer [REDACTED]"),
    # Lark open_id (personal identifier) - keep prefix for debugging
    (re.compile(r"\bou_[a-z0-9]{6,}\b", re.IGNORECASE), "ou_[REDACTED]"),
    # Emails
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
]


def redact_text(text: str, extra_patterns: Iterable[tuple[re.Pattern[str], str]] | None = None) -> str:
    """
    Redact secrets/PII from logs and demo outputs.
    This MUST be used before writing anything to demos/.
    """
    patterns = list(_DEFAULT_PATTERNS)
    if extra_patterns:
        patterns.extend(list(extra_patterns))

    redacted = text
    for pattern, repl in patterns:
        redacted = pattern.sub(repl, redacted)
    return redacted

