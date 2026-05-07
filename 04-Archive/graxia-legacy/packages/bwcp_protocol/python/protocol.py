from enum import Enum
from pydantic import BaseModel, ValidationError
from typing import Any, Dict, Optional
import sys
import os

# Ensure shared packages are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from python.envelope import MessageEnvelope

class MessageType(str, Enum):
    MISSION_CREATED = "MISSION_CREATED"
    MISSION_UPDATED = "MISSION_UPDATED"
    TASK_PROPOSED = "TASK_PROPOSED"
    TASK_BID = "TASK_BID"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_ACCEPTED = "TASK_ACCEPTED"
    TASK_DECLINED = "TASK_DECLINED"
    TASK_CLOSED = "TASK_CLOSED"
    TASK_FAILED = "TASK_FAILED"
    REQUEST_SKILL = "REQUEST_SKILL"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    BLOCKER_RAISED = "BLOCKER_RAISED"
    ALERT_CRITICAL = "ALERT_CRITICAL"
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"

def validate_message(data: Dict[str, Any]) -> MessageEnvelope:
    """Validates a raw dictionary against the BWCP Message Envelope."""
    try:
        return MessageEnvelope(**data)
    except ValidationError as e:
        # In v3, we log this as a protocol violation
        print(f"❌ BWCP Protocol Violation: {e.json()}")
        raise e

# Example Payload Factory for convenience
def create_bwcp_msg(
    from_agent: str, 
    to_agent: str, 
    msg_type: MessageType, 
    mission_id: str,
    payload: Dict[str, Any] = {}
) -> MessageEnvelope:
    import uuid
    from datetime import datetime, timezone
    
    return MessageEnvelope(
        message_id=f"msg_{uuid.uuid4().hex[:8]}",
        thread_id=f"thr_{uuid.uuid4().hex[:8]}",
        mission_id=mission_id,
        task_id=f"tsk_{uuid.uuid4().hex[:8]}",
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=msg_type.value,
        deadline_at=datetime.now(timezone.utc), # Placeholder
        correlation_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        payload=payload
    )
