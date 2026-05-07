from pydantic import BaseModel, Field, UUID4
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime, timezone
import uuid

class BWCPMessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assign"
    TASK_UPDATE = "task_update"
    TASK_RESULT = "task_result"
    CHECKPOINT_REACHED = "checkpoint"
    ERROR = "error"

class BWCPPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class BWCPMessage(BaseModel):
    """
    BravOS Work Contract Protocol (BWCP) Message Schema.
    Ensures strictly typed inter-agent communication.
    """
    message_id: str = Field(..., description="Unique ID for this message")
    id: Optional[str] = Field(None, description="Alias for message_id used by some agents")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    sender_agent: str = Field(..., description="Agent code of the sender")
    receiver_agent: str = Field(..., description="Agent code of the receiver")
    
    # Strict Pydantic V2 UUID validation
    mission_id: UUID4 = Field(..., description="Root mission ID this work belongs to")
    task_id: Optional[UUID4] = Field(None, description="Specific task ID if applicable")
    
    type: BWCPMessageType
    priority: BWCPPriority = BWCPPriority.NORMAL
    risk_class: RiskClass = Field(default=RiskClass.LOW, description="Risk class for the action requested")
    
    content: Optional[str] = Field(None, description="Main text content/instruction for the message")
    payload: Dict[str, Any] = Field(..., description="Payload specific to the message type")
    
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BWCPContract(BaseModel):
    """
    Represents a committed work contract between two agents.
    """
    contract_id: UUID4
    mission_id: UUID4
    employer_agent: str
    contractor_agent: str
    deliverables: List[str]
    deadline: Optional[datetime] = None
    status: str = "active"
