"""Phase BE-P0 — Redaction for logs, reports, and artifacts."""
import re
import hashlib


REDACT_PATTERNS = [
    (r'\b\d{6,12}\b', 'ACCOUNT_REDACTED'),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+', 'PASSWORD_REDACTED'),
    (r'(?i)(api_key|apikey)\s*[=:]\s*\S+', 'API_KEY_REDACTED'),
    (r'(?i)(token|bearer)\s*[=:]\s*\S+', 'TOKEN_REDACTED'),
    (r'MetaQuotes-Demo', 'BROKER_REDACTED'),
]


class Redactor:
    """Redact sensitive patterns from text."""

    def __init__(self, extra_patterns: list[tuple[str, str]] = None):
        self._patterns = REDACT_PATTERNS.copy()
        if extra_patterns:
            self._patterns.extend(extra_patterns)

    def redact(self, text: str) -> str:
        """Redact all sensitive patterns."""
        result = text
        for pattern, replacement in self._patterns:
            result = re.sub(pattern, replacement, result)
        return result

    def redact_dict(self, data: dict) -> dict:
        """Redact all string values in a dictionary."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.redact(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value)
            else:
                result[key] = value
        return result

    def fingerprint(self, text: str) -> str:
        """Create a one-way fingerprint for correlation."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
