"""In-memory workflow store — ref-based, no DB migration needed."""
from __future__ import annotations

from app.agent_workflows.errors import WorkflowOrgMismatchError, WorkflowRunNotFoundError
from app.agent_workflows.schemas import WorkflowRun, WorkflowStatusSummary


class WorkflowStore:
    """In-memory workflow run storage.

    Waiver: No DB migration in this wave.
    Target: local workflow readiness, not production persistence.
    """

    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}

    def save_run(self, run: WorkflowRun) -> None:
        self._runs[run.workflow_run_id] = run

    def get_run(self, workflow_run_id: str, organization_id: str) -> WorkflowRun:
        run = self._runs.get(workflow_run_id)
        if run is None:
            raise WorkflowRunNotFoundError(f"Run {workflow_run_id} not found")
        if run.organization_id != organization_id:
            raise WorkflowOrgMismatchError(
                f"Run {workflow_run_id} belongs to org {run.organization_id}, not {organization_id}"
            )
        return run

    def list_runs(
        self, organization_id: str, workflow_type: str | None = None
    ) -> list[WorkflowRun]:
        results = [
            r for r in self._runs.values() if r.organization_id == organization_id
        ]
        if workflow_type:
            results = [r for r in results if r.workflow_type == workflow_type]
        return sorted(results, key=lambda r: r.started_at, reverse=True)

    def get_status(self, organization_id: str) -> WorkflowStatusSummary:
        runs = [
            r
            for r in self._runs.values()
            if r.organization_id == organization_id
        ]
        summary = WorkflowStatusSummary(total_runs=len(runs))
        for r in runs:
            if r.status == "completed":
                summary.completed += 1
            elif r.status == "failed":
                summary.failed += 1
            elif r.status == "blocked":
                summary.blocked += 1
            elif r.status == "running":
                summary.running += 1
        if runs:
            summary.latest_run_id = runs[0].workflow_run_id
        return summary

    def clear(self) -> None:
        self._runs.clear()


# Global singleton store
workflow_store = WorkflowStore()
