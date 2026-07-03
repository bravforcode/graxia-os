from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeWorkflowDefinition:
    workflow_name: str
    description: str
    backend_workflow_type: str | None = None
    requires_approval: bool = False
    queue_supported: bool = True


class RuntimeWorkflowRegistry:
    def __init__(self) -> None:
        self._definitions = {
            item.workflow_name: item
            for item in (
                RuntimeWorkflowDefinition(
                    workflow_name="daily_funnel_brief",
                    description="Daily funnel brief via Graxia workflow engine.",
                    backend_workflow_type="daily_funnel_brief",
                ),
                RuntimeWorkflowDefinition(
                    workflow_name="lead_followup_draft",
                    description="Lead follow-up draft alias to customer inbox triage draft-only workflow.",
                    backend_workflow_type="customer_inbox_triage",
                    requires_approval=True,
                ),
                RuntimeWorkflowDefinition(
                    workflow_name="checkout_abandonment_monitor",
                    description="Local placeholder boundary for checkout abandonment monitoring.",
                    backend_workflow_type=None,
                    requires_approval=False,
                ),
                RuntimeWorkflowDefinition(
                    workflow_name="delivery_failure_monitor",
                    description="Delivery failure monitor via Graxia workflow engine.",
                    backend_workflow_type="delivery_failure_monitor",
                ),
                RuntimeWorkflowDefinition(
                    workflow_name="weekly_revenue_review",
                    description="Weekly revenue review via Graxia workflow engine.",
                    backend_workflow_type="weekly_revenue_review",
                ),
                RuntimeWorkflowDefinition(
                    workflow_name="token_benchmark_review",
                    description="Token benchmark review via Graxia workflow engine.",
                    backend_workflow_type="token_benchmark_review",
                ),
            )
        }

    def list(self) -> list[RuntimeWorkflowDefinition]:
        return list(self._definitions.values())

    def get(self, workflow_name: str) -> RuntimeWorkflowDefinition:
        definition = self._definitions.get(workflow_name)
        if definition is None:
            raise KeyError(f"Unknown runtime workflow: {workflow_name}")
        return definition


runtime_workflow_registry = RuntimeWorkflowRegistry()
