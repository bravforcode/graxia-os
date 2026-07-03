"""Context Engine — error classes.

All errors are safe and never contain raw tracebacks, secrets, or paths.
"""
from __future__ import annotations


class ContextEngineError(Exception):
    """Base error for all context engine errors."""

    def __init__(self, message: str = "Context engine error.", safe_to_retry: bool = False) -> None:
        self.message = message
        self.safe_to_retry = safe_to_retry
        super().__init__(self.message)


class ExclusionError(ContextEngineError):
    """Error during secret-safe exclusion."""

    def __init__(self, message: str = "Exclusion policy error.") -> None:
        super().__init__(message=message, safe_to_retry=True)


class IndexError(ContextEngineError):
    """Error during project indexing."""

    def __init__(self, message: str = "Project index error.", path: str | None = None) -> None:
        self.path = path
        super().__init__(message=message, safe_to_retry=True)


class PackError(ContextEngineError):
    """Error during context pack building."""

    def __init__(self, message: str = "Context pack error.") -> None:
        super().__init__(message=message, safe_to_retry=True)


class CacheError(ContextEngineError):
    """Error during cache operations."""

    def __init__(self, message: str = "Cache error.") -> None:
        super().__init__(message=message, safe_to_retry=True)


class DiffError(ContextEngineError):
    """Error during diff protocol."""

    def __init__(self, message: str = "Diff protocol error.") -> None:
        super().__init__(message=message, safe_to_retry=True)


class GraphError(ContextEngineError):
    """Error during context graph building."""

    def __init__(self, message: str = "Context graph error.") -> None:
        super().__init__(message=message, safe_to_retry=True)


class NotFoundError(ContextEngineError):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found.") -> None:
        super().__init__(message=message, safe_to_retry=False)
