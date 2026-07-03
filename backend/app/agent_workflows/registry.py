"""Workflow registry — register and discover workflow definitions."""
from __future__ import annotations

from typing import Any

from app.agent_workflows.errors import WorkflowNotFoundError
from app.agent_workflows.schemas import WorkflowDefinition


class WorkflowRegistry:
    """Registry for workflow definitions."""

    def __init__(self) -> None:
        self._definitions: dict[str, WorkflowDefinition] = {}

    def register(self, definition: WorkflowDefinition) -> None:
        self._definitions[definition.workflow_type] = definition

    def get(self, workflow_type: str) -> WorkflowDefinition:
        definition = self._definitions.get(workflow_type)
        if definition is None:
            raise WorkflowNotFoundError(f"Workflow '{workflow_type}' not registered")
        return definition

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "workflow_type": d.workflow_type,
                "description": d.description,
                "risk_level": "LOW_WRITE",
                "allowed_tools": d.policy.allowed_tools,
                "blocked_tools": d.policy.blocked_tools,
            }
            for d in self._definitions.values()
        ]

    def has(self, workflow_type: str) -> bool:
        return workflow_type in self._definitions


# Global singleton registry
workflow_registry = WorkflowRegistry()
