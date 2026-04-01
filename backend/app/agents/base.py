import logging
from app.core.identity import identity
from app.core.llm import llm_client
from app.core.event_bus import event_bus

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

    async def log_audit(self, action: str, details: dict, success: bool = True, error: str = None, was_fallback: bool = False) -> None:
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
