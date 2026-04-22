import asyncio
import logging
from typing import Any

from app.agents.base import BaseAgent
from app.core.model_router import route_task
from app.core.llm import llm_client
from app.core.event_bus import event_bus
from app.database import AsyncSessionLocal
from app.models.orchestration import AgentTask
from sqlalchemy import select

logger = logging.getLogger(__name__)

class AgentOrchestrator(BaseAgent):
    name = "orchestrator"

    async def start(self):
        """Start listening for delegated tasks and assigning them."""
        event_bus.subscribe("agent.task.delegated", self.on_task_delegated)
        event_bus.subscribe("agent.task.completed", self.on_task_completed)
        # Background task processing loop could be added here
        logger.info("Orchestrator online and listening to task events.")

    async def on_task_delegated(self, payload: dict[str, Any]):
        task_id = payload.get("task_id")
        assigned_to = payload.get("assigned_to")
        name = payload.get("name")
        logger.info(f"Orchestrator intercepted delegation: {name} to {assigned_to}")
        
        # Here we dynamically route the task to the correct agent module.
        # This acts as the central router for enterprise multi-agent workflows.
        try:
            module = __import__(f"app.agents.{assigned_to}", fromlist=[f"{assigned_to}_agent"])
            agent_instance = getattr(module, f"{assigned_to}_agent")
            
            # Fire and forget the agent's task execution
            asyncio.create_task(self._execute_agent_task(agent_instance, task_id))
        except Exception as e:
            logger.error(f"Orchestrator failed to route task to {assigned_to}: {e}")
            await self.fail_task(task_id, str(e))

    async def _execute_agent_task(self, agent_instance: BaseAgent, task_id: str):
        async with AsyncSessionLocal() as db:
            stmt = select(AgentTask).where(AgentTask.id == task_id)
            res = await db.execute(stmt)
            task = res.scalar_one_or_none()
            if not task:
                return

            task.status = "in_progress"
            await db.commit()
            
            try:
                # We assume agents have a `handle_task` method for delegated orchestration.
                if hasattr(agent_instance, "handle_task"):
                    result = await getattr(agent_instance, "handle_task")(task.description)
                else:
                    # Fallback to general LLM if agent is just a generic persona
                    routing = route_task("analysis")
                    result_text = await llm_client.complete(
                        system=f"You are the {agent_instance.name} agent. Execute this task.",
                        user=task.description,
                        model=routing.model,
                        task_class="analysis"
                    )
                    result = {"response": result_text}

                await agent_instance.complete_task(task_id, result)
            except Exception as e:
                logger.error(f"Agent {agent_instance.name} failed task {task_id}: {e}")
                await self.fail_task(task_id, str(e))

    async def fail_task(self, task_id: str, error_msg: str):
        async with AsyncSessionLocal() as db:
            stmt = select(AgentTask).where(AgentTask.id == task_id)
            res = await db.execute(stmt)
            task = res.scalar_one_or_none()
            if task:
                task.status = "failed"
                task.result = {"error": error_msg}
                await db.commit()

    async def on_task_completed(self, payload: dict[str, Any]):
        assigned_by = payload.get("assigned_by")
        assigned_to = payload.get("assigned_to")
        task_id = payload.get("task_id")
        logger.info(f"Task {task_id} completed by {assigned_to}. Notifying {assigned_by}.")
        
        # If assigned by orchestrator, check for next steps in goal
        if assigned_by == self.name:
            await self.log_audit("subtask_completed", {"task_id": task_id, "agent": assigned_to})

    async def orchestrate_goal(self, goal: str) -> list[dict]:
        routing = route_task("classification")
        system_prompt = "You are an orchestrator agent. Break the user's goal into subtasks. Return JSON list of tasks: [{'name': '...', 'description': '...', 'agent_type': 'researcher|drafter|briefer|classifier'}]."
        
        try:
            tasks_data = await llm_client.complete_json(
                system=system_prompt,
                user=f"Goal: {goal}",
                model=routing.model,
                task_class="classification"
            )
            tasks = tasks_data if isinstance(tasks_data, list) else tasks_data.get("tasks", [])
        except Exception as e:
            logger.warning(f"Failed to decompose goal: {e}")
            tasks = []

        subtasks = []
        for task in tasks:
            agent_type = task.get("agent_type", "research_collector")
            # For simplicity, map "researcher" to "research_collector"
            if agent_type == "researcher":
                agent_type = "research_collector"
                
            await self.delegate_task(
                name=task.get("name", "Subtask"),
                description=task.get("description", ""),
                to_agent=agent_type
            )
            subtasks.append(task)

        return subtasks

orchestrator_agent = AgentOrchestrator()
