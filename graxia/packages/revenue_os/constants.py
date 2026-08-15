"""
Revenue OS Constants
Hard Rules and system constants (HR-01 to HR-26)
"""

# ══════════════════════════════════════════════════════════════════
# HARD RULES (HR-01 to HR-26)
# ══════════════════════════════════════════════════════════════════

HR_01 = "No financial action without CEO-approved budget"
HR_02 = "No email dispatch without explicit CEO approval"
HR_03 = "All orders must have idempotency keys"
HR_04 = "Ledger entries are append-only, never UPDATE"
HR_05 = "All webhook events must verify HMAC signatures"
HR_06 = "Rate limiting enforced on all public endpoints"
HR_07 = "All AI-generated content must be logged before action"
HR_08 = "Campaign budgets must not be exceeded without approval"
HR_09 = "Critical incidents must pause related campaigns"
HR_10 = "All financial mutations route through audit_service"
HR_11 = "Concurrent order creation must use savepoints"
HR_12 = "Email retry count must not exceed MAX_EMAIL_ATTEMPTS"
HR_13 = "Automation locks must have TTL and heartbeat"
HR_14 = "Incident escalation is mandatory for BWCP validation failures"
HR_15 = "All customer PII must be encrypted at rest"
HR_16 = "Refunds must create corresponding ledger entries"
HR_17 = "Product fulfillment requires published status"
HR_18 = "Attribution events must be idempotent via event_id"
HR_19 = "Campaign status changes must be audited"
HR_20 = "Delivery emails must have unique email_key"
HR_21 = "Webhook replay must be prevented via unique constraints"
HR_22 = "All API endpoints require authentication in production"
HR_23 = "CORS origins must be explicitly whitelisted"
HR_24 = "Database connections must use connection pooling"
HR_25 = "All timestamps must be timezone-aware (UTC)"
HR_26 = "No live trading without separate written CEO authorization"

HARD_RULES = [
    HR_01, HR_02, HR_03, HR_04, HR_05, HR_06, HR_07, HR_08, HR_09, HR_10,
    HR_11, HR_12, HR_13, HR_14, HR_15, HR_16, HR_17, HR_18, HR_19, HR_20,
    HR_21, HR_22, HR_23, HR_24, HR_25, HR_26
]

# ══════════════════════════════════════════════════════════════════
# SYSTEM CONSTANTS
# ══════════════════════════════════════════════════════════════════

# Email
MAX_EMAIL_ATTEMPTS = 5
EMAIL_RETRY_DELAY_SECONDS = 300  # 5 minutes

# Automation
AUTOMATION_LOCK_TTL_MINUTES = 45
AUTOMATION_LOCK_HEARTBEAT_INTERVAL_SECONDS = 60

# Rate Limiting
DEFAULT_RATE_LIMIT_REQUESTS = 120
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60

# Pagination
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200

# Currency
DEFAULT_CURRENCY = "THB"
SUPPORTED_CURRENCIES = ["THB", "USD", "EUR", "GBP"]

# Platforms
SUPPORTED_PLATFORMS = ["stripe", "gumroad", "manual"]

# Campaign
CAMPAIGN_BUDGET_WARNING_THRESHOLD = 0.8  # 80%
CAMPAIGN_BUDGET_CRITICAL_THRESHOLD = 0.95  # 95%

# Incidents
INCIDENT_AUTO_RESOLVE_DAYS = 30

# Webhooks
WEBHOOK_TIMEOUT_SECONDS = 30
WEBHOOK_MAX_RETRIES = 3

# AI/LLM
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
LLM_MAX_RETRIES = 2
LLM_TIMEOUT_SECONDS = 60

# Approval
APPROVAL_DEFAULT_EXPIRY_HOURS = 24
APPROVAL_AUTO_REJECT_AFTER_EXPIRY = True

# Content
MIN_PENDING_CONTENT_DRAFTS = 5
DAILY_CONTENT_DRAFT_COUNT = 3

# Metrics
METRICS_RETENTION_DAYS = 365
STRATEGY_LOG_RETENTION_DAYS = 730  # 2 years

# Autonomy & policy engine
AUTONOMY_STATE_ID = 1  # singleton row id for the autonomy state
CIRCUIT_BREAKER_WINDOW_MINUTES = 60   # trailing window checked for incident spikes
CIRCUIT_BREAKER_INCIDENT_THRESHOLD = 5  # MEDIUM+ incidents in the window that force mode -> OFF
SUPPORT_VERIFICATION_TTL_MINUTES = 15   # one-time code validity
SUPPORT_VERIFICATION_MAX_ATTEMPTS = 5  # wrong-code attempts before escalation
SUPPORT_VERIFICATION_SALT = "graxia-support-v1"  # replace via env SECRET_KEY-derived salt in production

# Channels / suppliers / ads (Phase 2)
CHANNEL_ORDER_IMPORT_LIMIT = 200
SUPPLIER_POLL_INTERVAL_MIN = 15
ADS_METRICS_WINDOW_DAYS = 7
PRICE_CHANGE_MIN_INTERVAL_HOURS = 24

# Phase 3
FX_REFRESH_DAYS = 1
DEFAULT_STOCK_BUFFER = 3
ATTRIBUTION_WINDOW_DAYS = 30
AFFILIATE_REVIEW_THRESHOLD_CENTS = 50_000_00
PLATFORM_FEE_RATES = {"shopee": 0.07, "lazada": 0.06, "tiktok_shop": 0.08, "amazon": 0.15}
