"""
Workflow & Automation Service — Features 56-70
Core service for managing workflows, triggers, executions, and pipelines
"""

import logging
import uuid as uuid_module
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    ExecutionStatus,
    Pipeline,
    PipelineRun,
    Workflow,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowNodeExecution,
    WorkflowSchedule,
    WorkflowStatus,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)


class WorkflowService:
    """
    Workflow & Automation Service

    Manages:
    - Workflow definitions and execution (Features 56-59)
    - Triggers and event handling (Features 58, 66-70)
    - Scheduling (Feature 60)
    - Pipeline building (Feature 62)
    - Batch processing (Feature 63)
    - Error handling and retries (Features 64, 65)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ═════════════════════════════════════════════════════════════════════════
    # WORKFLOW CRUD (Feature 59)
    # ═════════════════════════════════════════════════════════════════════════

    async def create_workflow(
        self,
        organization_id: UUID,
        workflow_key: str,
        name: str,
        description: str | None = None,
        workflow_type: str = "automation",
        flow_definition: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        auto_assign_agents: bool = True,
        required_skills: list[UUID] | None = None,
        timeout_seconds: int = 300,
        retry_count: int = 3,
        created_by_agent_id: UUID | None = None,
    ) -> Workflow:
        """Create a new workflow definition."""
        workflow = Workflow(
            organization_id=organization_id,
            workflow_key=workflow_key,
            name=name,
            description=description,
            workflow_type=workflow_type,
            flow_definition=flow_definition or {"nodes": [], "edges": []},
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            auto_assign_agents=auto_assign_agents,
            required_skills=required_skills or [],
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            created_by_agent_id=created_by_agent_id,
            status=WorkflowStatus.DRAFT.value,
        )

        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(f"Created workflow: {workflow_key} ({name}) for org {organization_id}")
        return workflow

    async def get_workflow(self, workflow_id: UUID, organization_id: UUID) -> Workflow | None:
        """Get workflow by ID for a specific organization."""
        from sqlalchemy import and_
        result = await self.db.execute(
            select(Workflow).where(and_(Workflow.id == workflow_id, Workflow.organization_id == organization_id))
        )
        return result.scalar_one_or_none()

    async def get_workflow_by_key(self, workflow_key: str, organization_id: UUID) -> Workflow | None:
        """Get workflow by unique key for a specific organization."""
        from sqlalchemy import and_
        result = await self.db.execute(
            select(Workflow).where(
                and_(Workflow.workflow_key == workflow_key, Workflow.organization_id == organization_id)
            )
        )
        return result.scalar_one_or_none()

    async def list_workflows(
        self,
        status: str | None = None,
        workflow_type: str | None = None,
        created_by_agent_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Workflow], int]:
        """List workflows with filters."""
        query = select(Workflow)

        if status:
            query = query.where(Workflow.status == status)
        if workflow_type:
            query = query.where(Workflow.workflow_type == workflow_type)
        if created_by_agent_id:
            query = query.where(Workflow.created_by_agent_id == created_by_agent_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Get paginated results
        query = query.order_by(desc(Workflow.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        workflows = result.scalars().all()

        return list(workflows), total or 0

    async def activate_workflow(self, workflow_id: UUID) -> Workflow | None:
        """Activate a workflow for execution."""
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return None

        workflow.status = WorkflowStatus.ACTIVE.value
        workflow.activated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(f"Activated workflow: {workflow.workflow_key}")
        return workflow

    # ═════════════════════════════════════════════════════════════════════════
    # WORKFLOW EXECUTION (Feature 59)
    # ═════════════════════════════════════════════════════════════════════════

    async def execute_workflow(
        self,
        workflow_id: UUID,
        input_data: dict[str, Any] | None = None,
        trigger_type: str = "manual",
        trigger_source: str | None = None,
        assigned_agent_ids: list[UUID] | None = None,
    ) -> WorkflowExecution:
        """Execute a workflow."""
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status != WorkflowStatus.ACTIVE.value:
            raise ValueError(f"Workflow {workflow_id} is not active")

        # Generate execution key
        execution_key = f"EXEC-{workflow.workflow_key}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid_module.uuid4().hex[:8]}"

        execution = WorkflowExecution(
            execution_key=execution_key,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_source=trigger_source,
            input_data=input_data or {},
            status=ExecutionStatus.PENDING.value,
            pending_nodes=[node["id"] for node in workflow.flow_definition.get("nodes", [])],
            assigned_agent_ids=assigned_agent_ids or [],
        )

        self.db.add(execution)

        # Update workflow stats
        workflow.execution_count += 1

        await self.db.commit()
        await self.db.refresh(execution)

        logger.info(f"Created workflow execution: {execution_key}")
        return execution

    async def start_execution(self, execution_id: UUID) -> WorkflowExecution | None:
        """Mark execution as started."""
        execution = await self.db.get(WorkflowExecution, execution_id)
        if not execution:
            return None

        execution.status = ExecutionStatus.RUNNING.value
        execution.started_at = datetime.utcnow()

        await self.db.commit()

        # Create event
        await self._create_execution_event(
            execution_id=execution_id,
            event_type="started",
            event_key="execution.started",
            payload={"started_at": execution.started_at.isoformat()},
        )

        return execution

    async def complete_execution(
        self,
        execution_id: UUID,
        output_data: dict[str, Any],
        results_summary: str | None = None,
    ) -> WorkflowExecution | None:
        """Mark execution as completed."""
        execution = await self.db.get(WorkflowExecution, execution_id)
        if not execution:
            return None

        execution.status = ExecutionStatus.COMPLETED.value
        execution.completed_at = datetime.utcnow()
        execution.output_data = output_data
        execution.results_summary = results_summary

        # Calculate duration
        if execution.started_at:
            execution.duration_ms = int(
                (execution.completed_at - execution.started_at).total_seconds() * 1000
            )

        # Update workflow stats
        workflow = await self.get_workflow(execution.workflow_id)
        if workflow:
            workflow.success_count += 1
            # Update average execution time
            if workflow.avg_execution_time_ms:
                workflow.avg_execution_time_ms = (
                    (workflow.avg_execution_time_ms * (workflow.success_count - 1))
                    + execution.duration_ms
                ) // workflow.success_count
            else:
                workflow.avg_execution_time_ms = execution.duration_ms

        await self.db.commit()

        # Create event
        await self._create_execution_event(
            execution_id=execution_id,
            event_type="completed",
            event_key="execution.completed",
            payload={
                "completed_at": execution.completed_at.isoformat(),
                "duration_ms": execution.duration_ms,
            },
        )

        return execution

    async def fail_execution(
        self,
        execution_id: UUID,
        error_message: str,
    ) -> WorkflowExecution | None:
        """Mark execution as failed."""
        execution = await self.db.get(WorkflowExecution, execution_id)
        if not execution:
            return None

        execution.status = ExecutionStatus.FAILED.value
        execution.completed_at = datetime.utcnow()
        execution.last_error = error_message
        execution.error_count += 1

        # Update workflow stats
        workflow = await self.get_workflow(execution.workflow_id)
        if workflow:
            workflow.failure_count += 1

        await self.db.commit()

        # Create event
        await self._create_execution_event(
            execution_id=execution_id,
            event_type="failed",
            event_key="execution.failed",
            severity="error",
            payload={
                "error": error_message,
                "failed_at": execution.completed_at.isoformat(),
            },
        )

        return execution

    async def _create_execution_event(
        self,
        execution_id: UUID,
        event_type: str,
        event_key: str,
        payload: dict[str, Any] | None = None,
        severity: str = "info",
        node_id: str | None = None,
    ) -> None:
        """Create an execution event for streaming (Feature 70)."""
        event = WorkflowEvent(
            execution_id=execution_id,
            event_type=event_type,
            event_key=event_key,
            node_id=node_id,
            payload=payload or {},
            severity=severity,
        )
        self.db.add(event)
        await self.db.commit()

    # ═════════════════════════════════════════════════════════════════════════
    # NODE EXECUTION
    # ═════════════════════════════════════════════════════════════════════════

    async def create_node_execution(
        self,
        execution_id: UUID,
        node_id: str,
        node_type: str,
        node_name: str | None = None,
        assigned_skill_id: UUID | None = None,
        assigned_agent_id: UUID | None = None,
        input_data: dict[str, Any] | None = None,
    ) -> WorkflowNodeExecution:
        """Create a node execution record."""
        node_execution = WorkflowNodeExecution(
            execution_id=execution_id,
            node_id=node_id,
            node_type=node_type,
            node_name=node_name,
            assigned_skill_id=assigned_skill_id,
            assigned_agent_id=assigned_agent_id,
            input_data=input_data or {},
            status=ExecutionStatus.PENDING.value,
        )

        self.db.add(node_execution)
        await self.db.commit()
        await self.db.refresh(node_execution)

        return node_execution

    async def complete_node_execution(
        self,
        node_execution_id: UUID,
        output_data: dict[str, Any],
    ) -> WorkflowNodeExecution | None:
        """Mark a node execution as completed."""
        node_execution = await self.db.get(WorkflowNodeExecution, node_execution_id)
        if not node_execution:
            return None

        node_execution.status = ExecutionStatus.COMPLETED.value
        node_execution.completed_at = datetime.utcnow()
        node_execution.output_data = output_data

        if node_execution.started_at:
            node_execution.duration_ms = int(
                (node_execution.completed_at - node_execution.started_at).total_seconds() * 1000
            )

        await self.db.commit()
        return node_execution

    # ═════════════════════════════════════════════════════════════════════════
    # TRIGGERS (Features 58, 66-70)
    # ═════════════════════════════════════════════════════════════════════════

    async def create_trigger(
        self,
        workflow_id: UUID,
        trigger_type: str,
        name: str,
        event_pattern: dict[str, Any] | None = None,
        conditions: list[dict[str, Any]] | None = None,
        webhook_url: str | None = None,
        input_mapping: dict[str, Any] | None = None,
        rate_limit_per_minute: int | None = None,
    ) -> WorkflowTrigger:
        """Create a workflow trigger."""
        trigger_key = (
            f"TRIG-{workflow_id}-{trigger_type}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        )

        trigger = WorkflowTrigger(
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_key=trigger_key,
            name=name,
            event_pattern=event_pattern or {},
            conditions=conditions or [],
            webhook_url=webhook_url,
            input_mapping=input_mapping or {},
            rate_limit_per_minute=rate_limit_per_minute,
            is_active=True,
        )

        self.db.add(trigger)
        await self.db.commit()
        await self.db.refresh(trigger)

        logger.info(f"Created trigger: {trigger_key} ({trigger_type})")
        return trigger

    async def process_event_trigger(
        self,
        event_type: str,
        event_data: dict[str, Any],
    ) -> list[WorkflowExecution]:
        """Process an event and trigger matching workflows (Feature 58, 70)."""
        executions = []

        # Find matching triggers
        result = await self.db.execute(
            select(WorkflowTrigger)
            .join(Workflow)
            .where(WorkflowTrigger.is_active)
            .where(Workflow.status == WorkflowStatus.ACTIVE.value)
        )
        triggers = result.scalars().all()

        for trigger in triggers:
            # Check if trigger matches event
            if await self._trigger_matches(trigger, event_type, event_data):
                # Map event data to workflow input
                input_data = await self._map_trigger_input(trigger, event_data)

                # Execute workflow
                execution = await self.execute_workflow(
                    workflow_id=trigger.workflow_id,
                    input_data=input_data,
                    trigger_type="event",
                    trigger_source=event_type,
                )
                executions.append(execution)

                # Update trigger stats
                trigger.last_triggered_at = datetime.utcnow()
                trigger.trigger_count += 1

        await self.db.commit()
        return executions

    async def _trigger_matches(
        self,
        trigger: WorkflowTrigger,
        event_type: str,
        event_data: dict[str, Any],
    ) -> bool:
        """Check if trigger matches the event."""
        # Check event pattern
        pattern = trigger.event_pattern or {}
        if pattern.get("event_type") and pattern["event_type"] != event_type:
            return False

        # Check conditions (Feature 61)
        conditions = trigger.conditions or []
        if not conditions:
            return True

        results = []
        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator", "equals")
            value = condition.get("value")

            actual_value = event_data.get(field)

            if operator == "equals":
                results.append(actual_value == value)
            elif operator == "not_equals":
                results.append(actual_value != value)
            elif operator == "contains":
                results.append(value in str(actual_value))
            elif operator == "greater_than":
                results.append(actual_value > value if actual_value else False)
            elif operator == "less_than":
                results.append(actual_value < value if actual_value else False)

        # Apply logic (AND/OR)
        if trigger.condition_logic == "AND":
            return all(results)
        else:
            return any(results)

    async def _map_trigger_input(
        self,
        trigger: WorkflowTrigger,
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Map event data to workflow input using trigger's mapping config."""
        mapping = trigger.input_mapping or {}

        if not mapping:
            return event_data

        input_data = {}
        for target_field, source_field in mapping.items():
            input_data[target_field] = event_data.get(source_field)

        return input_data

    # ═════════════════════════════════════════════════════════════════════════
    # SCHEDULING (Feature 60)
    # ═════════════════════════════════════════════════════════════════════════

    async def schedule_workflow(
        self,
        workflow_id: UUID,
        name: str,
        cron_expression: str | None = None,
        interval_seconds: int | None = None,
        run_at: datetime | None = None,
        is_recurring: bool = False,
        max_runs: int | None = None,
        default_input: dict[str, Any] | None = None,
    ) -> WorkflowSchedule:
        """Schedule a workflow for future execution."""
        # Calculate next run time
        next_run = None
        if run_at:
            next_run = run_at
        elif interval_seconds:
            next_run = datetime.utcnow() + timedelta(seconds=interval_seconds)

        schedule = WorkflowSchedule(
            workflow_id=workflow_id,
            name=name,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            run_at=run_at,
            is_recurring=is_recurring,
            max_runs=max_runs,
            default_input=default_input or {},
            next_run_at=next_run,
            is_active=True,
        )

        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)

        logger.info(f"Scheduled workflow: {workflow_id} - {name}")
        return schedule

    async def get_due_schedules(self) -> list[WorkflowSchedule]:
        """Get all schedules that are due for execution."""
        result = await self.db.execute(
            select(WorkflowSchedule)
            .where(WorkflowSchedule.is_active)
            .where(WorkflowSchedule.next_run_at <= datetime.utcnow())
        )
        return list(result.scalars().all())

    async def process_schedule(self, schedule: WorkflowSchedule) -> WorkflowExecution:
        """Process a due schedule and execute the workflow."""
        # Execute workflow
        execution = await self.execute_workflow(
            workflow_id=schedule.workflow_id,
            input_data=schedule.default_input,
            trigger_type="scheduled",
            trigger_source=f"schedule:{schedule.name}",
        )

        # Update schedule
        schedule.last_run_at = datetime.utcnow()
        schedule.run_count += 1

        # Calculate next run
        if schedule.is_recurring and (
            not schedule.max_runs or schedule.run_count < schedule.max_runs
        ):
            if schedule.interval_seconds:
                schedule.next_run_at = datetime.utcnow() + timedelta(
                    seconds=schedule.interval_seconds
                )
        else:
            schedule.is_active = False
            schedule.next_run_at = None

        await self.db.commit()
        return execution

    # ═════════════════════════════════════════════════════════════════════════
    # PIPELINES (Features 62, 63)
    # ═════════════════════════════════════════════════════════════════════════

    async def create_pipeline(
        self,
        pipeline_key: str,
        name: str,
        description: str | None = None,
        pipeline_type: str = "linear",
        nodes: list[dict[str, Any]] | None = None,
        batch_size: int = 1,
        is_parallel: bool = False,
    ) -> Pipeline:
        """Create a pipeline definition."""
        pipeline = Pipeline(
            pipeline_key=pipeline_key,
            name=name,
            description=description,
            pipeline_type=pipeline_type,
            nodes=nodes or [],
            batch_size=batch_size,
            is_parallel=is_parallel,
        )

        self.db.add(pipeline)
        await self.db.commit()
        await self.db.refresh(pipeline)

        logger.info(f"Created pipeline: {pipeline_key}")
        return pipeline

    async def run_pipeline(
        self,
        pipeline_id: UUID,
        input_data: dict[str, Any],
        batch_index: int = 0,
        total_batches: int = 1,
    ) -> PipelineRun:
        """Execute a pipeline run (Feature 63: Batch Processing)."""
        pipeline = await self.db.get(Pipeline, pipeline_id)
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        run = PipelineRun(
            pipeline_id=pipeline_id,
            status=ExecutionStatus.PENDING.value,
            batch_index=batch_index,
            total_batches=total_batches,
            input_data=input_data,
        )

        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        logger.info(f"Created pipeline run: {run.id} (batch {batch_index}/{total_batches})")
        return run

    # ═════════════════════════════════════════════════════════════════════════
    # RETRY & FALLBACK (Features 64, 65)
    # ═════════════════════════════════════════════════════════════════════════

    async def retry_execution(
        self,
        execution_id: UUID,
    ) -> WorkflowExecution | None:
        """Retry a failed execution (Feature 64)."""
        execution = await self.db.get(WorkflowExecution, execution_id)
        if not execution:
            return None

        workflow = await self.get_workflow(execution.workflow_id)
        if not workflow:
            return None

        # Check retry limit
        if execution.retry_attempts >= workflow.retry_count:
            logger.warning(f"Execution {execution_id} exceeded retry limit")
            return None

        # Reset execution state
        execution.status = ExecutionStatus.PENDING.value
        execution.retry_attempts += 1
        execution.error_count = 0
        execution.last_error = None
        execution.started_at = None
        execution.completed_at = None
        execution.duration_ms = None

        await self.db.commit()

        logger.info(f"Retrying execution: {execution_id} (attempt {execution.retry_attempts})")
        return execution

    async def trigger_fallback(
        self,
        execution_id: UUID,
        fallback_workflow_id: UUID,
    ) -> WorkflowExecution | None:
        """Trigger a fallback workflow (Feature 65)."""
        original = await self.db.get(WorkflowExecution, execution_id)
        if not original:
            return None

        # Mark original as using fallback
        original.fallback_triggered = True

        # Execute fallback
        fallback = await self.execute_workflow(
            workflow_id=fallback_workflow_id,
            input_data=original.input_data,
            trigger_type="fallback",
            trigger_source=f"fallback:{original.execution_key}",
        )

        await self.db.commit()

        logger.info(f"Triggered fallback for {execution_id} -> {fallback.execution_key}")
        return fallback
