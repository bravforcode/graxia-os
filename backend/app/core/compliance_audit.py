"""
Enterprise Compliance Audit Logging

Implements:
- GDPR compliance logging (data access, deletion, export)
- SOC2 audit trails (who did what, when)
- Data retention policy enforcement
- PII detection and handling
- Audit log integrity (tamper-evident)
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Optional

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

from app.models.base import Base

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events for compliance."""
    # Data access
    DATA_READ = "data_read"
    DATA_CREATE = "data_create"
    DATA_UPDATE = "data_update"
    DATA_DELETE = "data_delete"
    
    # Authentication
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    PASSWORD_CHANGE = "password_change"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    
    # Authorization
    PERMISSION_DENIED = "permission_denied"
    ROLE_CHANGE = "role_change"
    
    # GDPR specific
    DATA_EXPORT_REQUESTED = "data_export_requested"
    DATA_EXPORT_COMPLETED = "data_export_completed"
    DATA_EXPORT_DELETED = "data_export_deleted"
    DATA_DELETION_REQUESTED = "data_deletion_requested"
    DATA_DELETION_COMPLETED = "data_deletion_completed"
    CONSENT_GIVEN = "consent_given"
    CONSENT_REVOKED = "consent_revoked"
    
    # System
    CONFIG_CHANGE = "config_change"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    WEBHOOK_RECEIVED = "webhook_received"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    
    # Security
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    IP_BLOCKED = "ip_blocked"
    SECURITY_ALERT = "security_alert"


class ComplianceAuditLog(Base):
    """
    Enterprise-grade compliance audit log.
    Tamper-evident with hash chaining.
    """
    __tablename__ = "compliance_audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)
    
    # Event details
    event_type = Column(String(50), nullable=False, index=True)
    event_category = Column(String(50), nullable=False, index=True)  # data_access, auth, gdpr, system, security
    
    # Actor information
    actor_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # User ID
    actor_type = Column(String(20), nullable=False, default="user")  # user, system, api_key, webhook
    actor_email = Column(String(255), nullable=True)
    session_id = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(Text, nullable=True)
    
    # Target information
    target_type = Column(String(50), nullable=True)  # user, organization, opportunity, etc.
    target_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    # Action details
    action_description = Column(Text, nullable=False)
    action_payload = Column(JSON, nullable=True)  # Sanitized request data
    action_result = Column(String(20), nullable=False, default="success")  # success, failure, partial
    error_message = Column(Text, nullable=True)
    
    # Data classification
    contains_pii = Column(Integer, default=0)  # 0 = no, 1 = yes
    data_retention_days = Column(Integer, nullable=True)  # How long to keep this log
    
    # GDPR/SOC2 specific
    gdpr_category = Column(String(50), nullable=True)  # data_access, data_portability, right_to_be_forgotten
    legal_basis = Column(String(50), nullable=True)  # consent, contract, legal_obligation, legitimate_interest
    
    # Integrity
    previous_hash = Column(String(64), nullable=True)  # SHA-256 of previous log entry
    entry_hash = Column(String(64), nullable=False)  # SHA-256 of this entry
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_audit_logs_actor_time', 'actor_id', 'created_at'),
        Index('ix_audit_logs_target_time', 'target_type', 'target_id', 'created_at'),
        Index('ix_audit_logs_event_time', 'event_type', 'created_at'),
        Index('ix_audit_logs_gdpr', 'gdpr_category', 'created_at'),
    )
    
    def calculate_hash(self) -> str:
        """Calculate hash of this entry for tamper detection."""
        data = {
            "id": str(self.id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "event_type": self.event_type,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "target_id": str(self.target_id) if self.target_id else None,
            "action_description": self.action_description,
            "previous_hash": self.previous_hash,
        }
        
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def verify_integrity(self) -> bool:
        """Verify this entry hasn't been tampered with."""
        return self.entry_hash == self.calculate_hash()


class ComplianceAuditLogger:
    """
    Enterprise-grade compliance audit logger.
    """
    
    RETENTION_POLICIES = {
        "gdpr_data_export": 365,  # 1 year
        "gdpr_data_deletion": 2555,  # 7 years (legal requirement)
        "security_events": 2555,  # 7 years
        "auth_events": 365,  # 1 year
        "data_access": 90,  # 90 days
        "system_events": 180,  # 6 months
    }
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self._last_hash: Optional[str] = None
    
    async def log_event(
        self,
        event_type: AuditEventType,
        actor_id: Optional[uuid.UUID] = None,
        actor_type: str = "user",
        actor_email: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[uuid.UUID] = None,
        action_description: str = "",
        action_payload: Optional[dict] = None,
        action_result: str = "success",
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        contains_pii: bool = False,
        gdpr_category: Optional[str] = None,
        legal_basis: Optional[str] = None,
    ) -> ComplianceAuditLog:
        """
        Log a compliance audit event.
        """
        # Determine retention period
        retention_days = self._get_retention_period(event_type)
        
        # Determine event category
        event_category = self._categorize_event(event_type)
        
        # Sanitize payload (remove sensitive data)
        sanitized_payload = self._sanitize_payload(action_payload) if action_payload else None
        
        # Get previous hash for chain integrity
        previous_hash = await self._get_last_hash()
        
        # Create audit log entry
        audit_entry = ComplianceAuditLog(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            event_type=event_type.value,
            event_category=event_category,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_email=actor_email,
            session_id=session_id,
            ip_address=self._anonymize_ip(ip_address) if ip_address else None,
            user_agent=user_agent,
            target_type=target_type,
            target_id=target_id,
            action_description=action_description,
            action_payload=sanitized_payload,
            action_result=action_result,
            error_message=error_message,
            contains_pii=1 if contains_pii else 0,
            data_retention_days=retention_days,
            gdpr_category=gdpr_category,
            legal_basis=legal_basis,
            previous_hash=previous_hash,
        )
        
        # Calculate hash
        audit_entry.entry_hash = audit_entry.calculate_hash()
        
        # Save to database
        self.db.add(audit_entry)
        await self.db.commit()
        
        # Update last hash
        self._last_hash = audit_entry.entry_hash
        
        # Also log to standard logger for real-time monitoring
        logger.info(
            f"AUDIT: {event_type.value} by {actor_type}:{actor_id} "
            f"on {target_type}:{target_id} - {action_description}"
        )
        
        return audit_entry
    
    async def log_data_access(
        self,
        actor_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        data_fields_accessed: list[str],
        legal_basis: str,
        **kwargs
    ) -> ComplianceAuditLog:
        """
        Log data access for GDPR compliance.
        """
        return await self.log_event(
            event_type=AuditEventType.DATA_READ,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            action_description=f"Accessed data fields: {', '.join(data_fields_accessed)}",
            action_payload={"fields_accessed": data_fields_accessed},
            contains_pii=True,
            gdpr_category="data_access",
            legal_basis=legal_basis,
            **kwargs
        )
    
    async def log_gdpr_export(
        self,
        actor_id: uuid.UUID,
        export_format: str,
        data_categories: list[str],
        **kwargs
    ) -> ComplianceAuditLog:
        """
        Log GDPR data portability (export) request.
        """
        return await self.log_event(
            event_type=AuditEventType.DATA_EXPORT_REQUESTED,
            actor_id=actor_id,
            action_description=f"Data export requested: {export_format}",
            action_payload={
                "export_format": export_format,
                "data_categories": data_categories,
            },
            contains_pii=True,
            gdpr_category="data_portability",
            legal_basis="consent",
            **kwargs
        )
    
    async def log_gdpr_deletion(
        self,
        actor_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        deletion_scope: str,
        **kwargs
    ) -> ComplianceAuditLog:
        """
        Log GDPR right to be forgotten (deletion) request.
        """
        return await self.log_event(
            event_type=AuditEventType.DATA_DELETION_REQUESTED,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            action_description=f"Data deletion requested: {deletion_scope}",
            action_payload={"deletion_scope": deletion_scope},
            contains_pii=True,
            gdpr_category="right_to_be_forgotten",
            legal_basis="legal_obligation",
            **kwargs
        )
    
    async def verify_audit_chain(self) -> dict:
        """
        Verify integrity of audit log chain.
        Returns status of verification.
        """
        from sqlalchemy import select
        
        result = await self.db.execute(
            select(ComplianceAuditLog)
            .order_by(ComplianceAuditLog.created_at)
        )
        entries = result.scalars().all()
        
        verified = 0
        failed = 0
        broken_chain = []
        
        previous_hash = None
        for entry in entries:
            # Verify entry hash
            if not entry.verify_integrity():
                failed += 1
                broken_chain.append({
                    "entry_id": str(entry.id),
                    "error": "hash_mismatch",
                    "timestamp": entry.created_at.isoformat(),
                })
                continue
            
            # Verify chain continuity
            if previous_hash and entry.previous_hash != previous_hash:
                failed += 1
                broken_chain.append({
                    "entry_id": str(entry.id),
                    "error": "chain_broken",
                    "expected_previous": previous_hash,
                    "actual_previous": entry.previous_hash,
                })
                continue
            
            verified += 1
            previous_hash = entry.entry_hash
        
        return {
            "total_entries": len(entries),
            "verified": verified,
            "failed": failed,
            "chain_integrity": failed == 0,
            "broken_chain_points": broken_chain,
        }
    
    async def cleanup_expired_logs(self) -> int:
        """
        Clean up audit logs that have exceeded retention period.
        Returns number of entries deleted.
        """
        from sqlalchemy import delete
        
        cutoff_date = datetime.now(UTC) - timedelta(days=0)
        
        # Find expired entries
        result = await self.db.execute(
            delete(ComplianceAuditLog)
            .where(
                ComplianceAuditLog.created_at < cutoff_date
            )
            .where(
                ComplianceAuditLog.data_retention_days.isnot(None)
            )
            .where(
                ComplianceAuditLog.created_at < 
                (datetime.now(UTC) - 
                 (ComplianceAuditLog.data_retention_days * timedelta(days=1)))
            )
        )
        
        await self.db.commit()
        
        deleted_count = result.rowcount
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired audit log entries")
        
        return deleted_count
    
    def _get_retention_period(self, event_type: AuditEventType) -> int:
        """Get retention period for event type."""
        if "gdpr" in event_type.value:
            if "export" in event_type.value:
                return self.RETENTION_POLICIES["gdpr_data_export"]
            elif "deletion" in event_type.value:
                return self.RETENTION_POLICIES["gdpr_data_deletion"]
        elif "security" in event_type.value or "suspicious" in event_type.value:
            return self.RETENTION_POLICIES["security_events"]
        elif event_type.value.startswith("login") or event_type.value.startswith("logout"):
            return self.RETENTION_POLICIES["auth_events"]
        elif event_type.value.startswith("data_"):
            return self.RETENTION_POLICIES["data_access"]
        else:
            return self.RETENTION_POLICIES["system_events"]
    
    def _categorize_event(self, event_type: AuditEventType) -> str:
        """Categorize event for easier filtering."""
        if "data_" in event_type.value:
            return "data_access"
        elif event_type.value.startswith(("login", "logout", "token", "password", "mfa")):
            return "authentication"
        elif event_type.value in ["permission_denied", "role_change"]:
            return "authorization"
        elif "gdpr" in event_type.value or "export" in event_type.value or "deletion" in event_type.value:
            return "gdpr"
        elif event_type.value in ["suspicious_activity", "rate_limit_exceeded", "ip_blocked", "security_alert"]:
            return "security"
        else:
            return "system"
    
    def _sanitize_payload(self, payload: dict) -> dict:
        """Remove sensitive data from payload for audit logs."""
        sensitive_fields = [
            "password", "secret", "token", "api_key", "private_key",
            "credit_card", "ssn", "social_security", "authorization",
            "cookie", "session_id"
        ]
        
        def mask_value(key: str, value: Any) -> Any:
            if any(s in key.lower() for s in sensitive_fields):
                if isinstance(value, str) and len(value) > 4:
                    return value[:2] + "***" + value[-2:]
                return "***"
            elif isinstance(value, dict):
                return {k: mask_value(k, v) for k, v in value.items()}
            elif isinstance(value, list):
                return [mask_value("item", item) if isinstance(item, dict) else item for item in value]
            return value
        
        return {k: mask_value(k, v) for k, v in payload.items()}
    
    def _anonymize_ip(self, ip_address: str) -> str:
        """
        Anonymize IP address for privacy.
        Keeps first 3 octets of IPv4, first 4 groups of IPv6.
        """
        try:
            ip = ipaddress.ip_address(ip_address)
            if isinstance(ip, ipaddress.IPv4Address):
                # Keep /24 network
                return str(ipaddress.ip_network(f"{ip}/24", strict=False).network_address) + "/24"
            else:
                # Keep /64 network for IPv6
                return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address) + "/64"
        except ValueError:
            return "invalid"
    
    async def _get_last_hash(self) -> Optional[str]:
        """Get hash of last audit log entry."""
        from sqlalchemy import select
        
        if self._last_hash:
            return self._last_hash
        
        result = await self.db.execute(
            select(ComplianceAuditLog.entry_hash)
            .order_by(ComplianceAuditLog.created_at.desc())
            .limit(1)
        )
        last_entry = result.scalar()
        return last_entry


# Global audit logger instance
_audit_logger: Optional[ComplianceAuditLogger] = None


def get_audit_logger(db_session: Session) -> ComplianceAuditLogger:
    """Get or create audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = ComplianceAuditLogger(db_session)
    return _audit_logger
