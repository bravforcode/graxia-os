"""
Revenue OS Enums
All enum definitions for Revenue OS models v12
"""
from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    FULFILLED = "fulfilled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"
    FRAUD = "fraud"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProductStatus(StrEnum):
    IDEA = "idea"
    VALIDATING = "validating"
    BUILDING = "building"
    PUBLISHED = "published"
    IMPROVING = "improving"
    ARCHIVED = "archived"


class ProductType(StrEnum):
    LEAD_MAGNET = "lead_magnet"
    LOW_TICKET = "low_ticket"
    CORE = "core"
    SERVICE = "service"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATING = "negotiating"
    CONVERTED = "converted"
    LOST = "lost"


class ContentStatus(StrEnum):
    IDEA = "idea"
    DRAFTED = "drafted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    POSTED = "posted"
    REJECTED = "rejected"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EmailStatus(StrEnum):
    PENDING = "pending"
    APPROVED_PENDING_SEND = "approved_pending_send"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BOUNCED = "bounced"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RefundStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class LedgerEntryType(StrEnum):
    CHARGE = "charge"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
    PAYOUT = "payout"
    FEE = "fee"


class AgentType(StrEnum):
    VISIONARY = "VisionaryAgent"
    SALES = "SalesAgent"
    CHIEF_OF_STAFF = "ChiefOfStaffAgent"
    RESEARCH = "ResearchAgent"
    SYSTEM = "system"


class BWCPMessageType(StrEnum):
    CAMPAIGN_CREATED = "campaign_created"
    CAMPAIGN_PAUSED = "campaign_paused"
    CAMPAIGN_RESUMED = "campaign_resumed"
    CAMPAIGN_TARGET_HIT = "campaign_target_hit"
    LEAD_IDENTIFIED = "lead_identified"
    LEAD_SCORED = "lead_scored"
    LEAD_CONVERTED = "lead_converted"
    DRAFT_QUEUED = "draft_queued"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_EXPIRED = "approval_expired"
    INCIDENT_CREATED = "incident_created"
    INCIDENT_RESOLVED = "incident_resolved"
    ORDER_FULFILLED = "order_fulfilled"
    ORDER_REFUNDED = "order_refunded"
