from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any, Dict

class DeliverableContract(BaseModel):
    type: str
    format: str
    review_required: bool = True
    acceptance_criteria: List[str]

class EscalationPolicy(BaseModel):
    if_blocked: str = "notify_chief_of_staff"
    if_overdue: str = "notify_ceo"
    if_error: str = "notify_engineer_agent"

class MessageEnvelope(BaseModel):
    message_id: str
    thread_id: str
    mission_id: str
    task_id: str
    parent_task_id: Optional[str] = None
    from_agent: str
    to_agent: str
    message_type: str  # MISSION_CREATED, TASK_BID, etc.
    priority: str = "MEDIUM"
    risk_class: str = "CLASS_1"
    budget_limit_usd: float = 0.0
    deadline_at: datetime
    sla_minutes: int = 60
    tool_scope: List[str] = []
    skill_scope: List[str] = []
    requires_approval: bool = False
    confidence: float = 1.0
    deliverable_contract: Optional[DeliverableContract] = None
    escalation: EscalationPolicy = Field(default_factory=EscalationPolicy)
    correlation_id: str
    trace_id: str
    payload: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
