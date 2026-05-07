import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.core.agent_registry import agent_registry
from app.core.event_bus import event_bus
from app.core.llm import llm_client
from app.core.model_router import route_task
from app.database import AsyncSessionLocal
from app.models.orchestration import AgentTask

logger = logging.getLogger(__name__)

class AgentOrchestrator(BaseAgent):
    name = "orchestrator"

    def __init__(self):
        super().__init__()
        self.semaphore = asyncio.Semaphore(50)

    async def start(self):
        """Start MAS orchestration services."""
        event_bus.subscribe("agent.task.delegated", self.on_task_delegated)
        event_bus.subscribe("agent.task.completed", self.on_task_completed)
        logger.info("Enterprise Orchestrator online.")

    async def on_task_delegated(self, payload: dict[str, Any]):
        task_id_str = payload.get("task_id")
        assigned_to = payload.get("assigned_to")
        
        if not task_id_str: return
        task_id = UUID(task_id_str)
        
        async with AsyncSessionLocal() as db:
            stmt = select(AgentTask).where(AgentTask.id == task_id)
            res = await db.execute(stmt)
            task = res.scalar_one_or_none()
            if not task:
                return

            # Dependency check
            if task.dependencies:
                dep_uuids = [UUID(d) for d in task.dependencies]
                dep_stmt = select(AgentTask).where(AgentTask.id.in_(dep_uuids))
                dep_res = await db.execute(dep_stmt)
                deps = dep_res.scalars().all()
                if any(d.status != "completed" for d in deps):
                    task.status = "waiting"
                    await db.commit()
                    logger.info(f"Task {task_id} is waiting for dependencies.")
                    return

            agent_instance = agent_registry.get_agent(assigned_to)
            if agent_instance:
                asyncio.create_task(self._bounded_execute(agent_instance, task_id))
            else:
                logger.error(f"Unknown agent: {assigned_to}")
                await self.fail_task(task_id, f"Agent {assigned_to} not found.")

    async def _bounded_execute(self, agent_instance: BaseAgent, task_id: UUID):
        async with self.semaphore:
            await self._execute_agent_task(agent_instance, task_id)

    async def _execute_agent_task(self, agent_instance: BaseAgent, task_id: UUID):
        async with AsyncSessionLocal() as db:
            stmt = select(AgentTask).where(AgentTask.id == task_id)
            res = await db.execute(stmt)
            task = res.scalar_one_or_none()
            if not task: return

            task.status = "in_progress"
            await db.commit()
            
            try:
                result = await agent_instance.handle_task(task.description)
                await agent_instance.complete_task(str(task_id), result)
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                await self.fail_task(task_id, str(e))

    async def fail_task(self, task_id: UUID, error_msg: str):
        async with AsyncSessionLocal() as db:
            stmt = select(AgentTask).where(AgentTask.id == task_id)
            res = await db.execute(stmt)
            task = res.scalar_one_or_none()
            if task:
                task.status = "failed"
                task.result = {"error": error_msg}
                await db.commit()

    async def on_task_completed(self, payload: dict[str, Any]):
        task_id_str = payload.get("task_id")
        if not task_id_str: return
        
        # Check for blocked sibling tasks
        async with AsyncSessionLocal() as db:
            stmt = select(AgentTask).where(AgentTask.status == "waiting")
            res = await db.execute(stmt)
            waiting_tasks = res.scalars().all()
            
            for wt in waiting_tasks:
                if wt.dependencies and task_id_str in wt.dependencies:
                    # Re-trigger task
                    await self.on_task_delegated({"task_id": str(wt.id), "assigned_to": wt.assigned_to})

    async def orchestrate_goal(self, goal: str) -> str:
        """Entry point for autonomous goal execution."""
        routing = route_task("classification")
        
        system_prompt = (
            "You are the Enterprise Orchestrator. Break down the user's high-level goal into a sequence of agent tasks.\n"
            "Identify dependencies. Return JSON: {'tasks': [{'name': '...', 'agent': '...', 'desc': '...', 'depends_on_index': [0, 1]}]}"
        )
        
        try:
            plan = await llm_client.complete_json(system=system_prompt, user=goal, model=routing.model)
            tasks_data = plan.get("tasks", [])
        except Exception:
            tasks_data = []

        # Create master goal task
        master_task_id = await self.delegate_task("Master Goal", goal, self.name)
        
        created_task_ids = []
        for i, t_info in enumerate(tasks_data):
            deps = [created_task_ids[j] for j in t_info.get("depends_on_index", []) if j < len(created_task_ids)]
            
            tid = await self.delegate_task(
                name=t_info.get("name"),
                description=t_info.get("desc"),
                to_agent=t_info.get("agent"),
                parent_id=master_task_id,
                dependencies=deps
            )
            created_task_ids.append(tid)

        return master_task_id

orchestrator_agent = AgentOrchestrator()