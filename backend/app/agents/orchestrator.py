import asyncio
import logging
from typing import Any

from app.agents.base import BaseAgent
from app.core.model_router import route_task
from app.core.llm import llm_client
from app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

class AgentOrchestrator(BaseAgent):
    name = "orchestrator"

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
            agent_type = task.get("agent_type", "researcher")
            subtasks.append({
                "id": str(len(subtasks) + 1),
                "name": task.get("name"),
                "agent_type": agent_type,
                "status": "pending"
            })

        for task in subtasks:
            await event_bus.emit("orchestrator.dispatch", task)

        summary_routing = route_task("short_summary")
        await llm_client.complete(
            system="Summarize the plan.",
            user=f"Plan: {subtasks}",
            model=summary_routing.model,
            task_class="short_summary"
        )
        return subtasks

orchestrator_agent = AgentOrchestrator()
