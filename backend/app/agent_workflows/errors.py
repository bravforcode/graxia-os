"""Workflow engine errors."""
from __future__ import annotations


class WorkflowError(Exception):
    """Base workflow error."""
    pass


class WorkflowNotFoundError(WorkflowError):
    """Workflow type not registered."""
    pass


class WorkflowRunNotFoundError(WorkflowError):
    """Workflow run ID not found."""
    pass


class WorkflowPolicyViolationError(WorkflowError):
    """Workflow policy violation."""
    pass


class WorkflowStepFailedError(WorkflowError):
    """A required workflow step failed."""
    pass


class WorkflowMaxStepsExceededError(WorkflowError):
    """Workflow exceeded max steps."""
    pass


class WorkflowOrgMismatchError(WorkflowError):
    """Organization ID mismatch on workflow run."""
    pass
