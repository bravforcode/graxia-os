from __future__ import annotations


class GatewayError(Exception):
    """Base runtime gateway error."""


class DangerousTaskBlockedError(GatewayError):
    """Task blocked by dangerous-tool policy."""


class ApprovalRequiredError(GatewayError):
    """Task requires approval before dispatch."""


class DispatchExecutionError(GatewayError):
    """Dispatcher execution failed."""
