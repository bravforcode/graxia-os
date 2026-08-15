"""
Revenue OS Enums
All enum definitions for Revenue OS models v12
"""
from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"  # payment captured, awaiting fulfillment
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


class ActionType(StrEnum):
    PRICE_CHANGE = "price_change"
    DISCOUNT = "discount"
    REFUND = "refund"
    FULFILL = "fulfill"
    CAMPAIGN_PAUSE = "campaign_pause"
    CAMPAIGN_PUBLISH = "campaign_publish"
    EMAIL_SEND = "email_send"
    AD_BUDGET = "ad_budget"
    SUPPLIER_PURCHASE = "supplier_purchase"


class RuleType(StrEnum):
    MAX = "max"
    MIN = "min"
    ALLOW = "allow"
    DENY = "deny"


class ValueType(StrEnum):
    """How a PolicyRule's `value` should be interpreted. ABSOLUTE is always in cents
    (matches the existing price_cents/amount_cents convention). A money-moving action
    is checked against BOTH: a percent cap alone does not bound absolute exposure."""
    PERCENT = "percent"
    ABSOLUTE = "absolute"


class AutonomyMode(StrEnum):
    """Staged autonomy rollout — see Task 12. Nothing reaches FULL without a defined
    observation period in SHADOW and LIMITED first."""
    OFF = "off"        # no autonomous action of any kind
    SHADOW = "shadow"  # agents compute + log what they WOULD do; nothing is executed
    LIMITED = "limited"  # agents execute, capped at value * limited_multiplier
    FULL = "full"       # agents execute at full policy-configured caps


class SupportIntent(StrEnum):
    WISMO = "wismo"
    REFUND = "refund"
    PRODUCT_QUESTION = "product_question"
    COMPLAINT = "complaint"
    SALES = "sales"
    OTHER = "other"


class ChannelType(StrEnum):
    SHOPIFY = "shopify"
    POD_SUPPLIER = "pod_supplier"


class SupplierStatus(StrEnum):
    SUBMITTED = "submitted"
    IN_PRODUCTION = "in_production"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    FAILED = "failed"
