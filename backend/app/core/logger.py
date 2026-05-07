"""
Logger module - re-exports from logging_config for backward compatibility
"""

# Re-export from logging_config for compatibility
from app.core.logging_config import (
    SENSITIVE_FIELD_NAMES,
    JSONFormatter,
    SensitiveDataFilter,
    generate_request_id,
    get_logger,
    get_request_id,
    redact_sensitive_data,
    request_id_var,
    set_request_id,
    setup_logging,
)

__all__ = [
    "request_id_var",
    "SENSITIVE_FIELD_NAMES",
    "JSONFormatter",
    "SensitiveDataFilter",
    "setup_logging",
    "get_logger",
    "get_request_id",
    "set_request_id",
    "generate_request_id",
    "redact_sensitive_data",
]
