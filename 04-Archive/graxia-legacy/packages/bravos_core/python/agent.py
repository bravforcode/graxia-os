import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import sys

# Attempt to import BWCPMessage and AuditService.
# Using defensive imports to accommodate varying PYTHONPATH setups.
try:
    from bwcp_protocol.models import BWCPMessage, RiskClass
except ImportError:
    try:
        from graxia.packages.bwcp_protocol.models import BWCPMessage, RiskClass
    except ImportError:
        pass

try:
    from logging.python.audit import audit_service
except ImportError:
    try:
        from graxia.packages.logging.python.audit import audit_service
    except ImportError:
        audit_service = None

# Setup default logger
logger = logging.getLogger("bravos_agent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

class BaseBravOSAgent(ABC):
    """
    Abstract Base Class for all BravOS Agents.
    Enforces BWCP protocol and provides enterprise audit logging out-of-the-box.
    """

    def __init__(self, agent_id: str, agent_type: str = "BravOS_Agent"):
        self.agent_id = agent_id
        self.agent_type = agent_type

    def receive_message(self, message_data: Dict[str, Any]) -> Any:
        """
        Receives raw message dict and parses/validates it into a BWCPMessage.
        Uses Pydantic V2 model_validate for strict typing.
        """
        try:
            # Assumes BWCPMessage is available in the environment
            message = BWCPMessage.model_validate(message_data)
            logger.info(f"[{self.agent_id}] Received valid BWCP message: {message.message_id}")
            return message
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to validate incoming BWCP message: {str(e)}")
            raise ValueError(f"Invalid BWCPMessage: {str(e)}")

    async def process_task(self, message_data: Dict[str, Any]) -> Any:
        """
        Wrapper to receive, validate, log start/end, and execute task.
        This ensures subclasses adhere to the audit requirements.
        """
        message = self.receive_message(message_data)
        
        task_id = str(message.task_id) if getattr(message, 'task_id', None) else "unknown_task"
        mission_id = str(message.mission_id) if getattr(message, 'mission_id', None) else "unknown_mission"
        risk_class = str(getattr(message, 'risk_class', "low"))
        
        # Log Start
        logger.info(f"[{self.agent_id}] Starting task {task_id} for mission {mission_id} (Risk: {risk_class})")
        if audit_service and hasattr(audit_service, 'log_event'):
            try:
                await audit_service.log_event(
                    actor_id=self.agent_id,
                    actor_type=self.agent_type,
                    event_type="TASK_START",
                    resource_id=task_id,
                    resource_type="BWCPTask",
                    action="execute",
                    status="in_progress",
                    metadata={"mission_id": mission_id, "risk_class": risk_class}
                )
            except Exception as e:
                logger.warning(f"Audit log failed: {e}")

        # Execute subclass-specific logic
        try:
            result = await self.execute_task(message)
            
            # Log Success
            logger.info(f"[{self.agent_id}] Completed task {task_id} successfully.")
            if audit_service and hasattr(audit_service, 'log_event'):
                try:
                    await audit_service.log_event(
                        actor_id=self.agent_id,
                        actor_type=self.agent_type,
                        event_type="TASK_COMPLETE",
                        resource_id=task_id,
                        resource_type="BWCPTask",
                        action="execute",
                        status="success",
                        metadata={"mission_id": mission_id}
                    )
                except Exception as e:
                    logger.warning(f"Audit log failed: {e}")

            return result
            
        except Exception as e:
            # Log Failure
            logger.error(f"[{self.agent_id}] Task {task_id} failed: {str(e)}")
            if audit_service and hasattr(audit_service, 'log_event'):
                try:
                    await audit_service.log_event(
                        actor_id=self.agent_id,
                        actor_type=self.agent_type,
                        event_type="TASK_FAILED",
                        resource_id=task_id,
                        resource_type="BWCPTask",
                        action="execute",
                        status="failed",
                        metadata={"mission_id": mission_id, "error": str(e)}
                    )
                except Exception as audit_e:
                    logger.warning(f"Audit log failed: {audit_e}")
            raise

    @abstractmethod
    async def execute_task(self, message: Any) -> Any:
        """
        Abstract method to be implemented by subclasses.
        Contains the specific logic for this agent type.
        """
        pass
