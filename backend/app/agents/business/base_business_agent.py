"""
Base Business Agent - Foundation for business operation agents
"""

from abc import abstractmethod
from datetime import datetime
from typing import Any

from structlog import get_logger

from app.agents.social.base_social_agent import BaseSocialAgent
from app.config import settings

logger = get_logger(__name__)


class BaseBusinessAgent(BaseSocialAgent):
    """
    Base class for business operation agents
    Extends social agent with business operation capabilities
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        agent_type: str = "business",
        bio: str = "",
        auto_reply: bool = True,
        enabled: bool = True,
    ):
        super().__init__(name, system_prompt, agent_type, bio, auto_reply, enabled)
        self.operation_log: list[dict] = []
        self.pending_approvals: list[dict] = []

    async def log_operation(
        self, operation: str, details: dict[str, Any], status: str = "success"
    ) -> None:
        """Log business operation to memory and Obsidian"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "details": details,
            "status": status,
            "agent": self.name,
        }

        self.operation_log.append(log_entry)

        # Log to message bus
        await self.broadcast_status(f"Operation: {operation} - {status}")

        # Log to Obsidian if available
        try:
            from app.integrations.obsidian import get_obsidian

            obsidian = await get_obsidian()

            today = datetime.now().strftime("%Y-%m-%d")
            content = f"""
## {operation}

**Time:** {log_entry["timestamp"]}
**Status:** {status}
**Agent:** {self.name}

### Details
```json
{details}
```
"""
            agent_ops_folder = (
                f"{settings.OBSIDIAN_ROOT_FOLDER}/01-Projects/Graxia-OS/Agent-Operations"
                if settings.OBSIDIAN_ROOT_FOLDER
                else "01-Projects/Graxia-OS/Agent-Operations"
            )
            await obsidian.append_to_note(
                filename=f"Business Operations/{today}",
                content=content,
                folder=agent_ops_folder,
            )
        except Exception as e:
            logger.warning(f"Could not log to Obsidian: {e}")

    async def request_approval(
        self, action: str, details: dict[str, Any], priority: str = "normal"
    ) -> str:
        """Request human approval for action"""
        approval_id = f"approval_{datetime.utcnow().timestamp()}"

        request = {
            "approval_id": approval_id,
            "agent": self.name,
            "action": action,
            "details": details,
            "priority": priority,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }

        self.pending_approvals.append(request)

        # Send to Telegram
        await self.notify_owner(
            title=f"🚨 Approval Required: {action}",
            message=f"Agent: {self.name}\nAction: {action}\nPriority: {priority}",
            buttons=[
                {"label": "Approve", "action": f"approve:{approval_id}"},
                {"label": "Reject", "action": f"reject:{approval_id}"},
                {"label": "Review", "action": f"review:{approval_id}"},
            ],
        )

        return approval_id

    async def broadcast_status(self, message: str) -> None:
        """Broadcast status message to message bus."""
        try:
            from app.core.message_bus import get_message_bus

            bus = get_message_bus()
            await bus.publish(
                f"agent.{self.name}.status",
                {
                    "agent": self.name,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception:
            # Message bus is optional, don't fail if not available
            pass

    async def notify_owner(
        self, title: str, message: str, buttons: list[dict] | None = None
    ) -> None:
        """Notify owner via Telegram."""
        try:
            import asyncio

            from app.telegram_bot.bot import send_message

            button_text = ""
            if buttons:
                button_lines = [f"- {b['label']} ({b['action']})" for b in buttons]
                button_text = "\n" + "\n".join(button_lines)

            full_message = f"{title}\n\n{message}{button_text}"

            # Fire and forget - don't block on telegram
            asyncio.create_task(send_message(full_message))
        except Exception:
            # Telegram not configured is OK
            pass

    @abstractmethod
    async def process_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        """Process a business operation - must be implemented by subclass"""
        pass

    async def get_operation_stats(self) -> dict[str, Any]:
        """Get operation statistics"""
        total = len(self.operation_log)
        successful = len([op for op in self.operation_log if op["status"] == "success"])
        failed = total - successful
        pending = len([a for a in self.pending_approvals if a["status"] == "pending"])

        return {
            "total_operations": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total * 100 if total > 0 else 0,
            "pending_approvals": pending,
        }
