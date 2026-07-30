"""Logging redaction middleware — automatically redacts secrets from log output."""

import re
from typing import Any

_PATTERNS = [
    (re.compile(r"bot\d+:[A-Za-z0-9_-]{35,}"), "TELEGRAM_TOKEN_REDACTED"),
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"(api_key|apikey|secret)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+"), "Bearer ***REDACTED***"),
]


class RedactingFilter:
    """Logging filter that redacts sensitive patterns."""

    def __init__(self, patterns: list[tuple[re.Pattern, str]] | None = None):
        self.patterns = patterns or _PATTERNS

    def filter(self, record: Any) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self.patterns:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args and isinstance(record.args, tuple):
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in self.patterns:
                        arg = pattern.sub(replacement, arg)
                new_args.append(arg)
            record.args = tuple(new_args)
        return True
