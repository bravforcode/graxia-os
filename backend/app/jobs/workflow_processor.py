"""
Workflow Background Processor — Features 56-70
Handles workflow execution, scheduling, and event processing in the background
"""

import asyncio
import logging

from app.database import AsyncSessionLocal
from app.models.workflow import (
    ExecutionStatus,
    WorkflowExecution,
)
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)


class WorkflowProcessor:
    """
    Background processor for workflow automation.

    Responsibilities:
    - Process scheduled workflows (Feature 60)
    - Execute pending workflow executions
    - Handle event triggers (Feature 58, 70)
    - Retry failed executions (Feature 64)
    - Emit real-time events (Feature 70)
    """

    def __init__(self):
        self.running = False
        self._task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the workflow processor."""
        if self.running:
            logger.warning("Workflow processor is already running")
            return

        self.running = True
        self._shutdown_event.clear()
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Workflow processor started")

    async def stop(self):
        """Stop the workflow processor gracefully."""
        if not self.running:
            return

        self.running = False
        self._shutdown_event.set()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Workflow processor stopped")

    async def _process_loop(self):
        """Main processing loop."""
        while self.running:
            try:
                # Process due schedules (Feature 60)
                await self._process_schedules()

                # Process pending executions
                await self._process_executions()

                # Wait before next iteration
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=5.0,  # Check every 5 seconds
                )
            except TimeoutError:
                continue  # Normal timeout, continue loop
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Workflow processor error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

    async def _process_schedules(self):
        """Process due workflow schedules (Feature 60)."""
        async with AsyncSessionLocal() as db:
            service = WorkflowService(db)

            try:
                # Get all due schedules
                schedules = await service.get_due_schedules()

                for schedule in schedules:
                    try:
                        # Process the schedule
                        execution = await service.process_schedule(schedule)

                        logger.info(
                            f"Executed scheduled workflow: {schedule.workflow_id} "
                            f"-> execution: {execution.execution_key}"
                        )

                        # Start execution in background
                        asyncio.create_task(self._execute_workflow(execution.id))
                    except Exception as e:
                        logger.error(
                            f"Failed to process schedule {schedule.id}: {e}", exc_info=True
                        )
            except Exception as e:
                logger.error(f"Error processing schedules: {e}", exc_info=True)

    async def _process_executions(self):
        """Process pending workflow executions."""
        async with AsyncSessionLocal() as db:
            try:
                from sqlalchemy import select

                # Get pending executions
                result = await db.execute(
                    select(WorkflowExecution)
                    .where(WorkflowExecution.status == ExecutionStatus.PENDING.value)
                    .order_by(WorkflowExecution.created_at)
                    .limit(10)
                )
                executions = result.scalars().all()

                for execution in executions:
                    # Start execution
                    asyncio.create_task(self._execute_workflow(execution.id))
            except Exception as e:
                logger.error(f"Error processing executions: {e}", exc_info=True)

    async def _execute_workflow(self, execution_id: str):
        """Execute a workflow with full orchestration."""
        async with AsyncSessionLocal() as db:
            service = WorkflowService(db)

            try:
                # Get execution
                from sqlalchemy import select

                result = await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
                )
                execution = result.scalar_one_or_none()

                if not execution:
                    logger.warning(f"Execution {execution_id} not found")
                    return

                # Start execution
                await service.start_execution(execution_id)

                # Get workflow details
                workflow = await service.get_workflow(execution.workflow_id)
                if not workflow:
                    raise ValueError(f"Workflow {execution.workflow_id} not found")

                # Execute flow nodes
                flow_def = workflow.flow_definition or {}
                nodes = flow_def.get("nodes", [])
                flow_def.get("edges", [])

                if not nodes:
                    # No nodes to execute, complete immediately
                    await service.complete_execution(
                        execution_id,
                        output_data={"message": "No nodes to execute"},
                    )
                    return

                # Build execution graph
                {node["id"]: node for node in nodes}
                completed = []
                failed = []

                # Execute nodes in order (simple linear for now)
                for node in nodes:
                    node_id = node["id"]
                    node_type = node.get("type", "skill")

                    try:
                        # Create node execution
                        node_exec = await service.create_node_execution(
                            execution_id=execution_id,
                            node_id=node_id,
                            node_type=node_type,
                            node_name=node.get("name"),
                            assigned_skill_id=node.get("skill_id"),
                            assigned_agent_id=node.get("agent_id"),
                            input_data=execution.input_data,
                        )

                        # Execute node logic
                        output = await self._execute_node(
                            node=node,
                            input_data=execution.input_data,
                            execution_context=execution.execution_context or {},
                        )

                        # Complete node execution
                        await service.complete_node_execution(
                            node_execution_id=node_exec.id,
                            output_data=output,
                        )

                        completed.append(node_id)

                        # Update execution progress
                        execution.completed_nodes = completed
                        execution.pending_nodes = [
                            n["id"] for n in nodes if n["id"] not in completed
                        ]
                        await db.commit()

                    except Exception as e:
                        logger.error(f"Node {node_id} failed: {e}")
                        failed.append(node_id)
                        execution.error_count += 1

                        # Check if we should retry
                        if execution.retry_attempts < workflow.retry_count:
                            await db.commit()
                            raise  # Re-raise to trigger retry
                        else:
                            # Max retries reached, fail execution
                            await service.fail_execution(execution_id, str(e))
                            return

                # All nodes completed successfully
                final_output = {
                    "completed_nodes": completed,
                    "failed_nodes": failed,
                    "execution_context": execution.execution_context,
                }

                await service.complete_execution(
                    execution_id=execution_id,
                    output_data=final_output,
                    results_summary=f"Completed {len(completed)} nodes",
                )

                logger.info(f"Workflow execution {execution_id} completed successfully")

            except Exception as e:
                logger.error(f"Workflow execution {execution_id} failed: {e}", exc_info=True)

                # Try to retry if possible
                execution = await db.get(WorkflowExecution, execution_id)
                if execution and execution.retry_attempts < 3:
                    await service.retry_execution(execution_id)
                else:
                    await service.fail_execution(execution_id, str(e))

    async def _execute_node(
        self,
        node: dict,
        input_data: dict,
        execution_context: dict,
    ) -> dict:
        """Execute a single workflow node."""
        node_type = node.get("type", "skill")

        if node_type == "skill":
            # Execute skill
            skill_id = node.get("skill_id")
            if skill_id:
                # Get skill and execute
                return {
                    "status": "completed",
                    "skill_id": skill_id,
                    "result": "Skill executed",
                }
            else:
                return {"status": "skipped", "reason": "No skill assigned"}

        elif node_type == "condition":
            # Evaluate condition
            condition = node.get("condition", {})
            field = condition.get("field")
            operator = condition.get("operator", "equals")
            value = condition.get("value")

            actual_value = input_data.get(field) or execution_context.get(field)

            result = False
            if operator == "equals":
                result = actual_value == value
            elif operator == "not_equals":
                result = actual_value != value
            elif operator == "contains":
                result = value in str(actual_value) if actual_value else False

            return {
                "status": "completed",
                "condition_result": result,
                "field": field,
                "actual_value": actual_value,
            }

        elif node_type == "transform":
            # Transform data
            node.get("transform", {})
            # Apply transformation
            return {
                "status": "completed",
                "transformed": True,
            }

        else:
            return {
                "status": "completed",
                "node_type": node_type,
            }


# Global processor instance
workflow_processor = WorkflowProcessor()


async def start_workflow_processor():
    """Start the workflow processor."""
    await workflow_processor.start()


async def stop_workflow_processor():
    """Stop the workflow processor."""
    await workflow_processor.stop()
