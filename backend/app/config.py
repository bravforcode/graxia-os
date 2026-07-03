import json
import math
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


def _rewrite_hostname(url: str, host_map: dict[str, str]) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname or hostname not in host_map:
        return url

    username = parts.username or ""
    password = parts.password or ""
    auth = username
    if password:
        auth = f"{auth}:{password}"
    if auth:
        auth = f"{auth}@"

    host = host_map[hostname]
    if ":" in host and not host.startswith("[") and "." not in host:
        host = f"[{host}]"
    netloc = f"{auth}{host}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _normalize_postgres_driver(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgresql+asyncpg://"):
        normalized = url
    elif url.startswith("postgresql://"):
        normalized = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        normalized = url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        return url

    parts = urlsplit(normalized)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", "")
    if sslmode and "ssl" not in query:
        query["ssl"] = sslmode
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _database_hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _database_port(url: str) -> int | None:
    return urlsplit(url).port


def _is_supabase_database_url(url: str) -> bool:
    host = _database_hostname(url)
    return host.endswith("supabase.co") or host.endswith("pooler.supabase.com")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, case_sensitive=True, extra="ignore"
    )

    # Security
    SECRET_KEY: str | None = None
    ENCRYPTION_KEY: str | None = None
    API_KEY: str = ""
    INTERNAL_API_KEY: str = ""

    # Enterprise IP Filtering (comma-separated CIDR blocks)
    # Example: "10.0.0.0/8,192.168.0.0/16,172.16.0.0/12"
    IP_WHITELIST: str = ""  # Empty = allow all
    IP_BLACKLIST: str = ""  # Block specific IPs/networks

    # Enterprise Security Settings
    SECURITY_LOG_ALL_REQUESTS: bool = True
    SECURITY_MAX_FAILED_AUTH: int = 5  # Lockout after N failed attempts
    SECURITY_LOCKOUT_DURATION: int = 300  # Lockout duration in seconds (5 min)
    SECURITY_REQUIRE_MFA: bool = False  # Require MFA for admin users
    SECURITY_AUDIT_RETENTION_DAYS: int = 90  # Audit log retention

    # Security Headers Configuration (L-09)
    SECURITY_HEADERS_CSP: str = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    SECURITY_HEADERS_HSTS_MAX_AGE: int = 63072000  # 2 years in seconds
    SECURITY_HEADERS_FRAME_OPTIONS: str = "DENY"
    SECURITY_HEADERS_CONTENT_TYPE_OPTIONS: str = "nosniff"
    SECURITY_HEADERS_REFERRER_POLICY: str = "strict-origin-when-cross-origin"
    SECURITY_HEADERS_PERMISSIONS_POLICY: str = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    SECURITY_HEADERS_DNS_PREFETCH_CONTROL: str = "off"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_SIGNING_KEYS: str = ""
    JWT_ACTIVE_KID: str = "v1"
    JWT_ISSUER: str = "personal-os"
    JWT_AUDIENCE: str = "personal-os-api"
    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    CSRF_COOKIE_NAME: str = "csrf_token"
    COOKIE_DOMAIN: str = ""
    COOKIE_SECURE: bool = False
    SESSION_MAX_CONCURRENT: int = 5
    CSRF_SECRET: str = ""
    ALLOWED_CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://frontend:5173"
    )
    APP_HOST: str = ""
    APP_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    CADDY_EMAIL: str = ""
    FLOWER_BASIC_AUTH: str = ""
    GRAFANA_ADMIN_PASSWORD: str = ""
    N8N_PASSWORD: str = ""

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://personal_os:changeme@postgres:5432/personal_os"
    )
    DATABASE_MIGRATION_URL: str = ""
    REQUIRE_SUPABASE: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800
    POSTGRES_DB: str = "personal_os"
    POSTGRES_USER: str = "personal_os"
    POSTGRES_PASSWORD: str | None = None

    # Redis
    REDIS_PASSWORD: str = ""
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # Backup / Disaster Recovery
    BACKUP_DIR: str = "backups"
    BACKUP_BUCKET: str = ""
    BACKUP_REGION: str = ""
    BACKUP_ENDPOINT: str = ""
    BACKUP_PREFIX: str = "backups"
    BACKUP_ENCRYPTION_PUBLIC_KEY: str = ""
    BACKUP_ENCRYPTION_PRIVATE_KEY_FILE: str = ""
    REDIS_SNAPSHOT_PATH: str = "/data/dump.rdb"
    RESTORE_DRILL_POSTGRES_IMAGE: str = "postgres:16.3-alpine"

    # AI â€” OpenClaw (Claude via OpenClaw proxy)
    OPENCLAW_API_KEY: str = ""
    OPENCLAW_BASE_URL: str = "https://api.openclaw.ai/v1"
    OPENCLAW_DEFAULT_MODEL: str = "claude-sonnet-4-5"
    OPENCLAW_FAST_MODEL: str = "claude-haiku-4-5"
    OPENCLAW_FALLBACK_MODELS: str = ""

    # Hermes / WSL2 Gateway
    HERMES_URL: str = "http://host.docker.internal:8081"
    HERMES_API_KEY: str = ""
    HERMES_TIMEOUT_SECONDS: int = 15

    # AI â€” Gemini (fallback)
    GEMINI_API_KEY: str = ""
    DEFAULT_MODEL: str = "claude-sonnet-4-5"
    FAST_MODEL: str = "claude-haiku-4-5"
    GEMINI_DAILY_REQUEST_LIMIT: int = 1400
    MODEL_ROUTING_ENABLED: bool = True
    CHEAP_MODEL: str = "gemini-2.0-flash-lite"
    MID_MODEL: str = "gemini-2.0-flash"
    HIGH_QUALITY_MODEL: str = "gemini-2.0-flash"
    CHEAP_MODEL_MAX_TOKENS: int = 500
    MID_MODEL_MAX_TOKENS: int = 1200
    HIGH_QUALITY_MODEL_MAX_TOKENS: int = 2000
    CHEAP_MODEL_INPUT_COST_PER_1M: float = 0.0
    CHEAP_MODEL_OUTPUT_COST_PER_1M: float = 0.0
    MID_MODEL_INPUT_COST_PER_1M: float = 0.0
    MID_MODEL_OUTPUT_COST_PER_1M: float = 0.0
    HIGH_QUALITY_MODEL_INPUT_COST_PER_1M: float = 0.0
    HIGH_QUALITY_MODEL_OUTPUT_COST_PER_1M: float = 0.0
    # Model Router Configuration
    ROUTER_SIMPLE_MAX_COMPLEXITY: int = 2
    ROUTER_MEDIUM_MAX_COMPLEXITY: int = 6
    MAX_SINGLE_LLM_CALL_COST_USD: float = 0.10

    # Model Router Task Defaults (tier, budget_tag, default_tokens)
    # Format: "task_class": "tier,budget_tag,tokens"
    ROUTER_TASK_DEFAULTS: str = (
        "classification:cheap,low,300;"
        "triage:cheap,low,400;"
        "short_summary:cheap,low,450;"
        "analysis:mid,standard,800;"
        "short_draft:mid,standard,700;"
        "meeting_summary:mid,standard,800;"
        "proposal:high,high,1600;"
        "strategy:high,high,1200"
    )

    # ML/AI
    OLLAMA_URL: str = "http://localhost:11434"
    DEFAULT_EMBEDDING_MODEL: str = "nomic-embed-text"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_POLLING_ENABLED: bool = False
    ALERTMANAGER_WEBHOOK_TOKEN: str = ""
    ALERTMANAGER_WEBHOOK_SECRET: str = ""
    # Content Engine site rebuild webhooks (Bug Fix #2)
    # Format: "site_a=https://api.vercel.com/deploy/hook/xxxx,site_b=https://..."
    SITE_REBUILD_WEBHOOKS: str = ""

    # Event Bus Configuration
    EVENT_BUS_SHUTDOWN_TIMEOUT: int = 30  # Seconds to wait for graceful shutdown
    EVENT_BUS_MAX_QUEUE_SIZE: int = 10000  # Maximum queue size for backpressure

    # CSRF Configuration
    CSRF_TOKEN_EXPIRY_HOURS: int = 1  # CSRF token expiry time in hours

    # Google Workspace
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REFRESH_TOKEN: str = ""
    GOOGLE_WORKSPACE_EMAIL: str = ""
    GOOGLE_ENABLE_WRITE_SCOPES: bool = False
    ALLOW_REAL_GOOGLE_MUTATION: bool = False

    # SerpAPI
    SERPAPI_KEY: str = ""

    # Stripe Billing
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_PRICE_STARTER_MONTHLY: str = ""
    STRIPE_PRICE_PRO_MONTHLY: str = ""
    STRIPE_PRICE_ENTERPRISE_MONTHLY: str = ""
    ALLOW_LIVE_STRIPE: bool = False

    # Email
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "Graxia <notifications@graxia.io>"
    ALLOW_REAL_EMAIL_SEND: bool = False

    # Identity
    IDENTITY_PATH: str = "/identity/profile.yaml"
    RUNNING_IN_DOCKER: bool = False

    # Obsidian Integration
    OBSIDIAN_VAULT_PATH: str = ""
    OBSIDIAN_API_URL: str = ""
    OBSIDIAN_API_KEY: str = ""
    OBSIDIAN_API_VERIFY_SSL: bool = True
    OBSIDIAN_ROOT_FOLDER: str = "Second Brain"
    OBSIDIAN_AUTO_BOOTSTRAP: bool = True
    OBSIDIAN_AUTO_SYNC_ENABLED: bool = True

    # Cost controls
    MAX_DAILY_REQUESTS: int = 1400
    MAX_DAILY_AI_COST_USD: float = 2.00
    MAX_MONTHLY_AI_COST_USD: float = 30.00
    MAX_OUTREACH_PER_DAY: int = 5
    MAX_PENDING_APPROVALS: int = 10

    # Autopilot / Revenue
    AUTOPILOT_ENABLED: bool = False
    AUTOPILOT_NOTIFY_EVERY_RUN: bool = False
    DAILY_REVENUE_TARGET_THB: int = 1000

    OUTREACH_AUTOSEND_ENABLED: bool = False
    OUTREACH_ALLOWED_EMAILS: str = ""
    OUTREACH_ALLOWED_DOMAINS: str = ""
    OUTREACH_MAX_PER_DAY: int = 5
    OUTREACH_MIN_DAYS_BETWEEN_CONTACT: int = 14
    OUTREACH_FROM_EMAIL: str = ""
    OUTREACH_CAMPAIGN_NAME: str = "revenue-first"

    EMAIL_TRACKING_ENABLED: bool = True
    TRACKING_BASE_URL: str = ""
    TRACKING_SIGNING_SECRET: str = ""

    HUBSPOT_PRIVATE_APP_TOKEN: str = ""
    SALESFORCE_INSTANCE_URL: str = ""
    SALESFORCE_ACCESS_TOKEN: str = ""

    LEADGEN_ENABLED: bool = False
    LEADGEN_MAX_PER_RUN: int = 50
    LEADGEN_EXPORT_DIR: str = "data/leads"
    LEADGEN_USE_SERPAPI: bool = False
    LEADGEN_SERPAPI_MAX_QUERIES: int = 8
    LEADGEN_SERPAPI_RESULTS_PER_QUERY: int = 10

    ICP_INDUSTRIES: str = ""
    ICP_COMPANY_SIZE_RANGE: str = ""
    ICP_COUNTRIES: str = ""
    ICP_TITLES: str = ""
    ICP_KEYWORDS: str = ""

    # Admin seed
    ADMIN_DEFAULT_EMAIL: str = ""
    ADMIN_DEFAULT_PASSWORD: str = ""

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    TESTING: bool = False
    SCHEDULER_EMBEDDED: bool = True
    ALLOW_REAL_LLM_CALLS: bool = False
    ALLOW_PRODUCTION_DB: bool = False

    # Production Readiness Gate
    PRODUCTION_READY: bool = False

    # Monitoring & Error Tracking
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.1

    # Beta / Controlled External Beta (Phase 19)
    BETA_ENABLED: bool = False
    BETA_MCP_TOOLS_ENABLED: bool = False
    BETA_WORKFLOWS_ENABLED: bool = False
    BETA_PUBLIC_FUNNEL_ENABLED: bool = False
    BETA_OPERATOR_UI_ENABLED: bool = False
    KILL_SWITCH_ALL_EXTERNAL_BETA: bool = (
        True  # Locked by default until explicitly opened
    )

    # Limited Beta Pilot / No-Live-Payment (Phase 20)
    NO_LIVE_PAYMENT_MODE: bool = (
        True  # Locked by default; blocks all payment processing
    )
    LIMITED_BETA_PILOT_READY: bool = (
        False  # Set to true only after Phase 20 exit criteria met
    )

    # Enterprise Security - Rate Limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100
    RATE_LIMIT_BURST: int = 10

    @model_validator(mode="after")
    def normalize_local_service_hosts(self):
        if self.DATABASE_URL.startswith("postgresql"):
            self.DATABASE_URL = _normalize_postgres_driver(self.DATABASE_URL)
        elif self.DATABASE_URL.startswith("sqlite"):
            if not self.DATABASE_URL.startswith("sqlite+aiosqlite"):
                self.DATABASE_URL = self.DATABASE_URL.replace(
                    "sqlite://", "sqlite+aiosqlite://"
                )

        if self.DATABASE_MIGRATION_URL.startswith("postgresql"):
            self.DATABASE_MIGRATION_URL = _normalize_postgres_driver(
                self.DATABASE_MIGRATION_URL
            )

        if self.APP_ENV.lower() == "development" and not self.RUNNING_IN_DOCKER:
            self.DATABASE_URL = _rewrite_hostname(
                self.DATABASE_URL, {"postgres": "localhost"}
            )
            self.DATABASE_MIGRATION_URL = _rewrite_hostname(
                self.DATABASE_MIGRATION_URL, {"postgres": "localhost"}
            )
            self.REDIS_URL = _rewrite_hostname(self.REDIS_URL, {"redis": "localhost"})
            self.CELERY_BROKER_URL = _rewrite_hostname(
                self.CELERY_BROKER_URL, {"redis": "localhost"}
            )
            self.CELERY_RESULT_BACKEND = _rewrite_hostname(
                self.CELERY_RESULT_BACKEND, {"redis": "localhost"}
            )
        if self.RUNNING_IN_DOCKER:
            host_map = {
                "localhost": "host.docker.internal",
                "127.0.0.1": "host.docker.internal",
            }
            self.OPENCLAW_BASE_URL = _rewrite_hostname(self.OPENCLAW_BASE_URL, host_map)
            self.OBSIDIAN_API_URL = _rewrite_hostname(self.OBSIDIAN_API_URL, host_map)
        return self

    @model_validator(mode="after")
    def validate_required_secrets(self):
        """
        Validate required secrets at startup (TASK 2.1: H-01).

        Testing mode: Auto-populate with safe defaults
        All other modes: Enforce strict validation
        """
        env = self.APP_ENV.lower()

        # Testing mode allows defaults for convenience
        if env == "testing":
            if self.SECRET_KEY is None:
                self.SECRET_KEY = (
                    "test-secret-key-min-32-chars-long-for-testing-purposes"
                )
            if self.ENCRYPTION_KEY is None:
                self.ENCRYPTION_KEY = "test-encryption-key-32-chars-long"
            if self.POSTGRES_PASSWORD is None:
                self.POSTGRES_PASSWORD = "test-password-16-chars"
            if not self.STRIPE_WEBHOOK_SECRET:
                self.STRIPE_WEBHOOK_SECRET = "whsec_test"
            if not self.STRIPE_SECRET_KEY:
                self.STRIPE_SECRET_KEY = "sk_test"
            return self

        # For all non-testing environments: enforce validation
        missing_secrets = []
        weak_secrets = []

        # Check for missing or placeholder secrets
        secret_key = (self.SECRET_KEY or "").strip()
        encryption_key = (self.ENCRYPTION_KEY or "").strip()
        postgres_password = (self.POSTGRES_PASSWORD or "").strip()

        # All non-testing environments: enforce strict validation
        # including placeholder detection and strength checks
        if not secret_key or self._looks_placeholder(secret_key):
            missing_secrets.append("SECRET_KEY")
        if not encryption_key or self._looks_placeholder(encryption_key):
            missing_secrets.append("ENCRYPTION_KEY")
        if not postgres_password or self._looks_placeholder(postgres_password):
            missing_secrets.append("POSTGRES_PASSWORD")

        # If any secrets are missing or placeholders, fail immediately
        if missing_secrets:
            error_parts = [
                f"Required secrets not configured: {', '.join(missing_secrets)}",
                "",
                "These secrets must be set in your .env file with strong, non-placeholder values.",
                "",
                "Generate strong secrets using:",
                "  SECRET_KEY:        openssl rand -base64 32",
                "  ENCRYPTION_KEY:    openssl rand -hex 32",
                "  POSTGRES_PASSWORD: openssl rand -base64 24",
                "",
                "Add them to your .env file:",
                f"  SECRET_KEY={secret_key if secret_key and not self._looks_placeholder(secret_key) else '<generate-strong-secret>'}",
                f"  ENCRYPTION_KEY={encryption_key if encryption_key and not self._looks_placeholder(encryption_key) else '<generate-strong-secret>'}",
                f"  POSTGRES_PASSWORD={postgres_password if postgres_password and not self._looks_placeholder(postgres_password) else '<generate-strong-secret>'}",
            ]
            raise RuntimeError("\n".join(error_parts))

        # Check for weak secrets (length and entropy) — all non-testing modes
        if len(secret_key) < 32:
            weak_secrets.append(
                f"SECRET_KEY must be at least 32 characters (current: {len(secret_key)})"
            )
        elif self._entropy(secret_key) < 4.0:
            weak_secrets.append(
                "SECRET_KEY has insufficient entropy (too repetitive or predictable)"
            )

        if len(encryption_key) < 32:
            weak_secrets.append(
                f"ENCRYPTION_KEY must be at least 32 characters (current: {len(encryption_key)})"
            )
        elif self._entropy(encryption_key) < 3.0:
            weak_secrets.append(
                "ENCRYPTION_KEY has insufficient entropy (too repetitive or predictable)"
            )

        if len(postgres_password) < 16:
            weak_secrets.append(
                f"POSTGRES_PASSWORD must be at least 16 characters (current: {len(postgres_password)})"
            )
        elif self._entropy(postgres_password) < 2.5:
            weak_secrets.append(
                "POSTGRES_PASSWORD has insufficient entropy (too repetitive or predictable)"
            )

        # If any secrets are weak, fail with detailed error
        if weak_secrets:
            error_parts = [
                "Weak secrets detected:",
                "",
            ]
            for weakness in weak_secrets:
                error_parts.append(f"  - {weakness}")
            error_parts.extend(
                [
                    "",
                    "Generate strong secrets using:",
                    "  openssl rand -base64 32  # For SECRET_KEY",
                    "  openssl rand -hex 32     # For ENCRYPTION_KEY",
                    "  openssl rand -base64 24  # For POSTGRES_PASSWORD",
                ]
            )
            raise RuntimeError("\n".join(error_parts))

        return self

    @staticmethod
    def _looks_placeholder(value: str) -> bool:
        lowered = (value or "").strip().lower()
        return (
            not lowered
            or lowered.startswith("your_")
            or lowered.startswith("your-")
            or lowered.startswith("paste_")
            or "paste_" in lowered
            or "changeme" in lowered
            or "change-me" in lowered
            or "development-secret" in lowered
            or "replace" in lowered
            or "placeholder" in lowered
            or "your-domain" in lowered
            or "your-project-ref" in lowered
            or "example.com" in lowered
            or lowered == "example"
        )

    @property
    def STRICT_BOOTSTRAP(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def HAS_REAL_OPENCLAW_KEY(self) -> bool:
        return not self._looks_placeholder(self.OPENCLAW_API_KEY)

    @property
    def HAS_REAL_GEMINI_KEY(self) -> bool:
        return not self._looks_placeholder(self.GEMINI_API_KEY)

    @property
    def HAS_REAL_TELEGRAM_TOKEN(self) -> bool:
        token = (self.TELEGRAM_BOT_TOKEN or "").strip()
        return not self._looks_placeholder(token) and ":" in token

    @property
    def HAS_REAL_TELEGRAM_CHAT_ID(self) -> bool:
        chat_id = (self.TELEGRAM_CHAT_ID or "").strip()
        return not self._looks_placeholder(chat_id) and chat_id.lstrip("-").isdigit()

    @property
    def HAS_REAL_SERPAPI_KEY(self) -> bool:
        return not self._looks_placeholder(self.SERPAPI_KEY)

    @property
    def SITE_REBUILD_WEBHOOK_MAP(self) -> dict[str, str]:
        """Parse SITE_REBUILD_WEBHOOKS CSV into a dict.

        Usage in tasks: settings.SITE_REBUILD_WEBHOOK_MAP.get(article.site)
        .env format:    SITE_REBUILD_WEBHOOKS=site_a=https://...,site_b=https://...
        """
        result: dict[str, str] = {}
        for pair in (self.SITE_REBUILD_WEBHOOKS or "").split(","):
            pair = pair.strip()
            if "=" in pair:
                k, _, v = pair.partition("=")
                k, v = k.strip(), v.strip()
                if k and v:
                    result[k] = v
        return result

    @property
    def HAS_REAL_GOOGLE_CLIENT_ID(self) -> bool:
        return not self._looks_placeholder(self.GOOGLE_CLIENT_ID)

    @property
    def HAS_REAL_GOOGLE_CLIENT_SECRET(self) -> bool:
        return not self._looks_placeholder(self.GOOGLE_CLIENT_SECRET)

    @property
    def HAS_REAL_GOOGLE_REFRESH_TOKEN(self) -> bool:
        return not self._looks_placeholder(self.GOOGLE_REFRESH_TOKEN)

    @property
    def HAS_REAL_GOOGLE_WORKSPACE_EMAIL(self) -> bool:
        value = (self.GOOGLE_WORKSPACE_EMAIL or "").strip()
        return not self._looks_placeholder(value) and "@" in value

    @property
    def HAS_REAL_GOOGLE_WORKSPACE_CREDENTIALS(self) -> bool:
        return (
            self.HAS_REAL_GOOGLE_CLIENT_ID
            and self.HAS_REAL_GOOGLE_CLIENT_SECRET
            and self.HAS_REAL_GOOGLE_REFRESH_TOKEN
            and self.HAS_REAL_GOOGLE_WORKSPACE_EMAIL
        )

    @property
    def DATABASE_HOST(self) -> str:
        return _database_hostname(self.DATABASE_URL)

    @property
    def DATABASE_PORT(self) -> int | None:
        return _database_port(self.DATABASE_URL)

    @property
    def EFFECTIVE_MIGRATION_DATABASE_URL(self) -> str:
        return self.DATABASE_MIGRATION_URL or self.DATABASE_URL

    @property
    def MIGRATION_DATABASE_HOST(self) -> str:
        return _database_hostname(self.EFFECTIVE_MIGRATION_DATABASE_URL)

    @property
    def MIGRATION_DATABASE_PORT(self) -> int | None:
        return _database_port(self.EFFECTIVE_MIGRATION_DATABASE_URL)

    @property
    def IS_SUPABASE(self) -> bool:
        return _is_supabase_database_url(self.DATABASE_URL)

    @property
    def IS_MIGRATION_SUPABASE(self) -> bool:
        return _is_supabase_database_url(self.EFFECTIVE_MIGRATION_DATABASE_URL)

    @property
    def IS_SUPABASE_TRANSACTION_MODE(self) -> bool:
        return self.IS_SUPABASE and self.DATABASE_PORT == 6543

    @property
    def IS_MIGRATION_SUPABASE_TRANSACTION_MODE(self) -> bool:
        return self.IS_MIGRATION_SUPABASE and self.MIGRATION_DATABASE_PORT == 6543

    @property
    def IS_MIGRATION_SUPABASE_SESSION_MODE(self) -> bool:
        return (
            self.IS_MIGRATION_SUPABASE
            and self.MIGRATION_DATABASE_PORT == 5432
            and "pooler.supabase.com" in self.MIGRATION_DATABASE_HOST
        )

    @property
    def IS_SUPABASE_SESSION_MODE(self) -> bool:
        return (
            self.IS_SUPABASE
            and self.DATABASE_PORT == 5432
            and "pooler.supabase.com" in self.DATABASE_HOST
        )

    @property
    def CORS_ORIGINS(self) -> list[str]:
        raw = (self.ALLOWED_CORS_ORIGINS or "").strip()
        if not raw:
            return []
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def COOKIE_SECURE_EFFECTIVE(self) -> bool:
        return self.COOKIE_SECURE or self.APP_ENV.lower() == "production"

    @property
    def CSRF_SIGNING_SECRET(self) -> str:
        return (self.CSRF_SECRET or self.SECRET_KEY or "").strip() or ""

    @property
    def JWT_KEYSET(self) -> dict[str, str]:
        if self.JWT_SIGNING_KEYS.strip():
            try:
                parsed = json.loads(self.JWT_SIGNING_KEYS)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "JWT_SIGNING_KEYS must be valid JSON; escape literal backslashes in key values as \\\\"
                ) from exc
            if not isinstance(parsed, dict) or not parsed:
                raise RuntimeError("JWT_SIGNING_KEYS must be a non-empty JSON object")
            return {
                str(key): str(value)
                for key, value in parsed.items()
                if str(value).strip()
            }
        return {self.JWT_ACTIVE_KID: self.SECRET_KEY}

    @property
    def ACTIVE_JWT_SIGNING_KEY(self) -> str:
        key = self.JWT_KEYSET.get(self.JWT_ACTIVE_KID)
        if not key:
            raise RuntimeError(
                f"JWT active kid '{self.JWT_ACTIVE_KID}' missing from JWT_KEYSET"
            )
        return key

    @property
    def FLOWER_BASIC_AUTH_PASSWORD(self) -> str:
        _username, _sep, password = (self.FLOWER_BASIC_AUTH or "").partition(":")
        return password.strip()

    def _entropy(self, value: str) -> float:
        if not value:
            return 0.0
        counts = Counter(value)
        total = len(value)
        return -sum(
            (count / total) * math.log2(count / total) for count in counts.values()
        )

    def get_production_configuration_errors(self) -> list[str]:
        if not self.STRICT_BOOTSTRAP:
            return []

        errors: list[str] = []
        if len((self.SECRET_KEY or "").strip()) < 64:
            errors.append("SECRET_KEY must be at least 64 characters in production")
        if self._entropy(self.SECRET_KEY) < 4.0:
            errors.append("SECRET_KEY does not have enough entropy")
        if self._looks_placeholder(self.ENCRYPTION_KEY):
            errors.append("ENCRYPTION_KEY must be configured in production")
        try:
            jwt_keyset = self.JWT_KEYSET
        except RuntimeError as exc:
            errors.append(str(exc))
            jwt_keyset = {}
        else:
            if not jwt_keyset:
                errors.append("JWT signing keys must be configured in production")
        for kid, signing_key in jwt_keyset.items():
            if self._looks_placeholder(signing_key) or len(signing_key.strip()) < 64:
                errors.append(
                    f"JWT signing key '{kid}' must be a non-placeholder 64+ character secret"
                )
        if not self.HAS_REAL_TELEGRAM_TOKEN or not self.HAS_REAL_TELEGRAM_CHAT_ID:
            errors.append(
                "Telegram control-plane credentials must be configured in production"
            )
        if self._looks_placeholder(self.ALERTMANAGER_WEBHOOK_TOKEN):
            errors.append("ALERTMANAGER_WEBHOOK_TOKEN must be configured in production")
        app_host = (self.APP_HOST or "").strip()
        if (
            self._looks_placeholder(app_host)
            or "://" in app_host
            or "localhost" in app_host.lower()
            or "example.com" in app_host.lower()
            or "." not in app_host
        ):
            errors.append(
                "APP_HOST must be a real production hostname without a URL scheme"
            )
        caddy_email = (self.CADDY_EMAIL or "").strip()
        if (
            self._looks_placeholder(caddy_email)
            or "@" not in caddy_email
            or caddy_email.lower().endswith("@example.com")
            or "localhost" in caddy_email.lower()
        ):
            errors.append(
                "CADDY_EMAIL must be configured with a real email for production TLS"
            )
        if not self.CORS_ORIGINS:
            errors.append("ALLOWED_CORS_ORIGINS must not be empty in production")
        if any(
            origin == "*" or origin.lower() == "null" or "*" in origin
            for origin in self.CORS_ORIGINS
        ):
            errors.append(
                "ALLOWED_CORS_ORIGINS must contain only explicit production origins"
            )
        if self._looks_placeholder(
            self.SUPABASE_URL
        ) or not self.SUPABASE_URL.lower().startswith("https://"):
            errors.append(
                "SUPABASE_URL must be configured with the real https project URL in production"
            )
        if self._looks_placeholder(self.SUPABASE_ANON_KEY):
            errors.append("SUPABASE_ANON_KEY must be configured in production")
        if self._looks_placeholder(self.SUPABASE_SERVICE_ROLE_KEY):
            errors.append("SUPABASE_SERVICE_ROLE_KEY must be configured in production")
        if self._looks_placeholder(self.BACKUP_BUCKET):
            errors.append("BACKUP_BUCKET must be configured in production")
        if self._looks_placeholder(self.BACKUP_REGION):
            errors.append("BACKUP_REGION must be configured in production")
        if self._looks_placeholder(self.BACKUP_ENCRYPTION_PUBLIC_KEY):
            errors.append(
                "BACKUP_ENCRYPTION_PUBLIC_KEY must be configured in production"
            )
        if self._looks_placeholder(self.BACKUP_ENCRYPTION_PRIVATE_KEY_FILE):
            errors.append(
                "BACKUP_ENCRYPTION_PRIVATE_KEY_FILE must be configured in production"
            )
        if self._looks_placeholder(self.N8N_PASSWORD):
            errors.append("N8N_PASSWORD must be configured in production")
        if self._looks_placeholder(self.GRAFANA_ADMIN_PASSWORD):
            errors.append("GRAFANA_ADMIN_PASSWORD must be configured in production")
        if (
            self._looks_placeholder(self.FLOWER_BASIC_AUTH)
            or ":" not in self.FLOWER_BASIC_AUTH
            or self._looks_placeholder(self.FLOWER_BASIC_AUTH_PASSWORD)
        ):
            errors.append(
                "FLOWER_BASIC_AUTH must use username:strong-password in production"
            )
        redis_passwords = [
            urlsplit(self.REDIS_URL).password,
            urlsplit(self.CELERY_BROKER_URL).password,
            urlsplit(self.CELERY_RESULT_BACKEND).password,
        ]
        if any(self._looks_placeholder(password or "") for password in redis_passwords):
            errors.append(
                "Redis URLs must include non-placeholder passwords in production"
            )
        if (
            self._looks_placeholder(self.APP_BASE_URL)
            or "localhost" in self.APP_BASE_URL.lower()
            or "example.com" in self.APP_BASE_URL.lower()
        ):
            errors.append("APP_BASE_URL must be a real production URL")
        if urlsplit(self.APP_BASE_URL).scheme != "https":
            errors.append("APP_BASE_URL must use https in production")
        if (
            self._looks_placeholder(self.FRONTEND_URL)
            or "localhost" in self.FRONTEND_URL.lower()
            or "example.com" in self.FRONTEND_URL.lower()
        ):
            errors.append("FRONTEND_URL must be a real production URL")
        if urlsplit(self.FRONTEND_URL).scheme != "https":
            errors.append("FRONTEND_URL must use https in production")
        if any(
            self._looks_placeholder(origin)
            or "localhost" in origin.lower()
            or "example.com" in origin.lower()
            for origin in self.CORS_ORIGINS
        ):
            errors.append(
                "ALLOWED_CORS_ORIGINS must contain only real production origins"
            )
        if self.REQUIRE_SUPABASE and not self.IS_SUPABASE:
            errors.append(
                "DATABASE_URL must point to Supabase when REQUIRE_SUPABASE=true"
            )
        if (
            self.DATABASE_MIGRATION_URL
            and self.REQUIRE_SUPABASE
            and not self.IS_MIGRATION_SUPABASE
        ):
            errors.append(
                "DATABASE_MIGRATION_URL must point to Supabase when REQUIRE_SUPABASE=true"
            )

        forbidden_values = {
            "changeme",
            "secret",
            "development",
            "localhost",
            "password",
            "replace",
            "test",
            "example",
            "placeholder",
        }
        for field_name, value in self.__dict__.items():
            if isinstance(value, str) and value.strip().lower() in forbidden_values:
                errors.append(f"{field_name} uses a forbidden placeholder value")

        return sorted(set(errors))

    def validate_production_configuration(self) -> None:
        errors = self.get_production_configuration_errors()
        if errors:
            raise RuntimeError(
                "Production security configuration is invalid: " + "; ".join(errors)
            )


settings = Settings()
