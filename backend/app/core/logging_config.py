"""
Centralized Logging Configuration

Structured JSON logging with request tracking.
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from contextvars import ContextVar
import uuid


# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar('request_id', default='')

SENSITIVE_FIELD_NAMES = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "csrf_token",
    "email",
    "encryption_key",
    "password",
    "refresh_token",
    "secret",
    "set-cookie",
    "token",
}

NON_REDACTED_FIELD_NAMES = {
    "created_at",
    "line",
    "request_id",
    "timestamp",
    "updated_at",
}

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
KEY_VALUE_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|csrf[_-]?token|password|refresh[_-]?token|secret|token)\b"
    r"\s*[:=]\s*([^\s,;&]+)"
)
TOKEN_PREFIX_PATTERN = re.compile(r"\b(?:sk|pk|ghp|xox[baprs])-[A-Za-z0-9._-]{8,}\b")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_sensitive_field(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return normalized in SENSITIVE_FIELD_NAMES or any(part in normalized for part in ("password", "secret", "token", "api_key"))


def _redact_string(value: str) -> str:
    value = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    value = PHONE_PATTERN.sub("[REDACTED_PHONE]", value)
    value = BEARER_PATTERN.sub("Bearer [REDACTED_TOKEN]", value)
    value = TOKEN_PREFIX_PATTERN.sub("[REDACTED_TOKEN]", value)
    return KEY_VALUE_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def redact_sensitive_data(value: Any, *, field_name: str | None = None) -> Any:
    if field_name and field_name.lower() in NON_REDACTED_FIELD_NAMES:
        return value
    if field_name and _is_sensitive_field(field_name):
        return "[REDACTED]"
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return {
            key: redact_sensitive_data(child, field_name=str(key))
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive_data(child) for child in value]
    return value


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def _build_file_handler(
    path: Path,
    *,
    formatter: logging.Formatter,
    level: int | None = None,
) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"[logging] file handler disabled for {path}: {exc}\n")
        return None
    if level is not None:
        handler.setLevel(level)
    handler.setFormatter(formatter)
    handler._bravos_json_logging = True
    return handler


class JSONFormatter(logging.Formatter):
    """Format logs as JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": _utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add request ID if available
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = redact_sensitive_data(self.formatException(record.exc_info))
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(redact_sensitive_data(record.extra))
        
        return json.dumps(redact_sensitive_data(log_data), default=str)


def setup_logging(level: str = "INFO") -> None:
    """Setup centralized logging configuration."""
    root_logger = logging.getLogger()
    if any(getattr(handler, "_bravos_json_logging", False) for handler in root_logger.handlers):
        root_logger.setLevel(getattr(logging, level.upper()))
        return

    # Create JSON formatter
    json_formatter = JSONFormatter()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(json_formatter)
    console_handler._bravos_json_logging = True
    
    # Root logger
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(console_handler)
    error_handler = _build_file_handler(
        LOG_DIR / "error.log",
        formatter=json_formatter,
        level=logging.ERROR,
    )
    if error_handler is not None:
        root_logger.addHandler(error_handler)
    all_handler = _build_file_handler(
        LOG_DIR / "app.log",
        formatter=json_formatter,
    )
    if all_handler is not None:
        root_logger.addHandler(all_handler)
    
    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get logger with name."""
    return logging.getLogger(name)


def set_request_id(request_id: str = None) -> str:
    """Set request ID for current context."""
    if request_id is None:
        request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    return request_id


def get_request_id() -> str:
    """Get request ID from current context."""
    return request_id_var.get()


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    **kwargs
) -> None:
    """Log message with additional context."""
    extra = {
        "request_id": get_request_id(),
        **kwargs
    }
    
    log_func = getattr(logger, level.lower())
    log_func(message, extra={"extra": extra})


# Create logs directory if it doesn't exist
os.makedirs(LOG_DIR, exist_ok=True)
