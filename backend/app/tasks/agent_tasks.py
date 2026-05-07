import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.core.agent_registry import agent_registry
from app.database import AsyncSessionLocal
from app.models.orchestration import AgentTask
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.agent_tasks.run_agent_task", bind=True, max_retries=3)
def run_agent_task(self, task_id_str: str):
    """
    Synchronous Celery wrapper that runs the asynchronous agent task.
    """
    return asyncio.run(_execute_task(task_id_str))


async def _execute_task(task_id_str: str):
    task_id = UUID(task_id_str)

    async with AsyncSessionLocal() as db:
        stmt = select(AgentTask).where(AgentTask.id == task_id)
        res = await db.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            logger.error(f"Task {task_id} not found in database.")
            return {"error": "not_found"}

        if task.status == "completed":
            return {"status": "already_completed"}

        task.status = "in_progress"
        await db.commit()

        agent_instance = agent_registry.get_agent(task.assigned_to)
        if not agent_instance:
            logger.error(f"Agent {task.assigned_to} not found for task {task_id}")
            task.status = "failed"
            task.result = {"error": f"Agent {task.assigned_to} not found"}
            await db.commit()
            return task.result

        try:
            logger.info(f"Executing task {task_id} with agent {task.assigned_to}")
            result = await agent_instance.handle_task(task.description)

            # Use the agent's complete_task method to ensure consistency (events, persistence)
            await agent_instance.complete_task(task_id_str, result)
            return {"status": "success", "task_id": task_id_str}

        except Exception as e:
            logger.error(f"Agent execution failed for task {task_id}: {e}", exc_info=True)
            task.status = "failed"
            task.result = {"error": str(e)}
            await db.commit()
            return task.result
