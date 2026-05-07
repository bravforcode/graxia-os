import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from .logger import get_logger

logger = get_logger("audit")

class AuditService:
    """
    Service for recording immutable audit logs to the database.
    Ensures compliance with the 16-plane architecture mandates.
    """
    
    def __init__(self, db_session=None):
        self.db = db_session

    async def log_event(
        self,
        actor_id: str,
        actor_type: str,
        event_type: str,
        resource_id: str,
        resource_type: str,
        action: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None
    ):
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)
        
        audit_entry = {
            "id": event_id,
            "timestamp": timestamp.isoformat(),
            "actor": {"id": actor_id, "type": actor_type},
            "event": event_type,
            "resource": {"id": resource_id, "type": resource_type},
            "action": action,
            "status": status,
            "tenant_id": tenant_id,
            "metadata": metadata or {}
        }
        
        # 1. Log to structured application logs (for RAG and monitoring)
        logger.info(f"AUDIT_EVENT: {event_type}", extra={"audit": audit_entry})
        
        # 2. Database persistence (if session provided)
        if self.db:
            try:
                # Placeholder for actual SQLAlchemy insert logic
                # In production, this would be: 
                # self.db.execute(audit_logs.insert().values(...))
                pass
            except Exception as e:
                logger.error(f"Failed to persist audit log: {str(e)}")
        
        return event_id

# Global instance for easy access
audit_service = AuditService()
