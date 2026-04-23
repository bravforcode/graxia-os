import logging
from typing import Any
from datetime import datetime, timezone

from app.core.identity import identity
from app.core.llm import llm_client
from app.core.event_bus import event_bus
from app.database import AsyncSessionLocal
from app.models.orchestration import AgentTask
from sqlalchemy import select

logger = logging.getLogger(__name__)

class BaseAgent:
    """Base class for all agents with enterprise coordination capabilities."""
    name: str = "base"

    @property
    def agent_context(self) -> str:
        return identity.get_agent_context()

    @property
    def llm(self):
        return llm_client

    @property
    def bus(self):
        return event_bus

    async def handle_task(self, description: str) -> dict[str, Any]:
        """
        Default implementation for executing a task. 
        Override this in subclasses for specific tool use.
        """
        from app.core.model_router import route_task
        routing = route_task("analysis")
        
        system_prompt = f"You are the {self.name} agent in the brav os system.\n{self.agent_context}\nExecute the task provided."
        
        result_text = await self.llm.complete(
            system=system_prompt,
            user=description,
            model=routing.model,
            task_class="analysis"
        )
        
        return {"response": result_text, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def log_audit(self, action: str, details: dict[str, Any], success: bool = True, error: str | None = None, was_fallback: bool = False) -> None:
        try:
            from app.models.audit import AuditLog
            async with AsyncSessionLocal() as db:
                db.add(AuditLog(
                    action=action,
                    details=details,
                    triggered_by=self.name,
                    success=success,
                    error_message=error,
                    was_fallback=was_fallback,
                ))
                await db.commit()
        except Exception as e:
            logger.warning(f"audit log failed: {e}")

    async def delegate_task(self, name: str, description: str, to_agent: str, parent_id: Any = None, dependencies: list[str] = None) -> str:
        """Delegate a task to another agent with optional hierarchy and dependencies."""
        async with AsyncSessionLocal() as db:
            task = AgentTask(
                name=name,
                description=description,
                assigned_to=to_agent,
                assigned_by=self.name,
                status="pending",
                parent_id=parent_id,
                dependencies=dependencies or []
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            
            task_id = str(task.id)
            await self.bus.emit("agent.task.delegated", {
                "task_id": task_id,
                "name": name,
                "assigned_to": to_agent,
                "assigned_by": self.name
            })
            return task_id

    async def request_meeting(self, topic: str, participants: list[str]) -> None:
        """Request a multi-agent meeting."""
        await self.bus.emit("agent.meeting.requested", {
            "topic": topic,
            "participants": participants,
            "requested_by": self.name
        })

    async def complete_task(self, task_id: str, result: dict[str, Any]) -> None:
        from uuid import UUID
        from datetime import datetime, timezone
        async with AsyncSessionLocal() as db:
            stmt = select(AgentTask).where(AgentTask.id == UUID(task_id))
            res = await db.execute(stmt)
            task = res.scalar_one_or_none()
            if task:
                task.status = "completed"
                task.result = result
                task.completed_at = datetime.now(timezone.utc)
                await db.commit()
                await self.bus.emit("agent.task.completed", {
                    "task_id": str(task.id),
                    "assigned_to": task.assigned_to,
                    "assigned_by": task.assigned_by
                })
