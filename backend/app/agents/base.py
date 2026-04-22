import logging
from typing import Any

from app.core.identity import identity
from app.core.llm import llm_client
from app.core.event_bus import event_bus
from app.database import AsyncSessionLocal
from app.models.orchestration import AgentTask

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all agents."""

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

    async def log_audit(
        self,
        action: str,
        details: dict[str, Any],
        success: bool = True,
        error: str | None = None,
        was_fallback: bool = False,
    ) -> None:
        try:
            from app.database import AsyncSessionLocal
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

    async def delegate_task(self, name: str, description: str, to_agent: str) -> None:
        """Delegate a task to another agent."""
        async with AsyncSessionLocal() as db:
            task = AgentTask(
                name=name,
                description=description,
                assigned_to=to_agent,
                assigned_by=self.name,
                status="pending"
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            
            await self.bus.emit("agent.task.delegated", {
                "task_id": str(task.id),
                "name": name,
                "assigned_to": to_agent,
                "assigned_by": self.name
            })
            logger.info(f"Agent {self.name} delegated task '{name}' to {to_agent}")

    async def request_meeting(self, topic: str, participants: list[str]) -> None:
        """Request a multi-agent meeting to discuss a complex topic."""
        await self.bus.emit("agent.meeting.requested", {
            "topic": topic,
            "participants": participants,
            "requested_by": self.name
        })
        logger.info(f"Agent {self.name} requested a meeting on '{topic}' with {participants}")

    async def complete_task(self, task_id: str, result: dict[str, Any]) -> None:
        from datetime import datetime, timezone
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            stmt = select(AgentTask).where(AgentTask.id == task_id)
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
