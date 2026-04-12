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
    if ":" in host and not host.startswith("["):
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
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _database_hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _database_port(url: str) -> int | None:
    return urlsplit(url).port


def _is_supabase_database_url(url: str) -> bool:
    host = _database_hostname(url)
    return host.endswith("supabase.co") or host.endswith("pooler.supabase.com")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, case_sensitive=True, extra="ignore")

    # Security
    SECRET_KEY: str = "development-secret-key-change-me"
    ENCRYPTION_KEY: str = ""
    API_KEY: str = ""
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
    ALLOWED_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://frontend:5173"
    APP_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://personal_os:changeme@postgres:5432/personal_os"
    DATABASE_MIGRATION_URL: str = ""
    REQUIRE_SUPABASE: bool = False
    POSTGRES_DB: str = "personal_os"
    POSTGRES_USER: str = "personal_os"
    POSTGRES_PASSWORD: str = "changeme"

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

    # AI — OpenClaw (Claude via OpenClaw proxy)
    OPENCLAW_API_KEY: str = ""
    OPENCLAW_BASE_URL: str = "https://api.openclaw.ai/v1"
    OPENCLAW_DEFAULT_MODEL: str = "claude-sonnet-4-5"
    OPENCLAW_FAST_MODEL: str = "claude-haiku-4-5"

    # AI — Gemini (fallback)
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
    ROUTER_SIMPLE_MAX_COMPLEXITY: int = 2
    ROUTER_MEDIUM_MAX_COMPLEXITY: int = 6
    MAX_SINGLE_LLM_CALL_COST_USD: float = 0.10

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_POLLING_ENABLED: bool = False
    ALERTMANAGER_WEBHOOK_TOKEN: str = ""

    # Google Workspace
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REFRESH_TOKEN: str = ""
    GOOGLE_WORKSPACE_EMAIL: str = ""

    # SerpAPI
    SERPAPI_KEY: str = ""

    # Identity
    IDENTITY_PATH: str = "/identity/profile.yaml"
    RUNNING_IN_DOCKER: bool = False

    # Obsidian Integration
    OBSIDIAN_VAULT_PATH: str = ""
    OBSIDIAN_API_URL: str = ""
    OBSIDIAN_API_KEY: str = ""
    OBSIDIAN_ROOT_FOLDER: str = "Second Brain"
    OBSIDIAN_AUTO_BOOTSTRAP: bool = True
    OBSIDIAN_AUTO_SYNC_ENABLED: bool = True

    # Cost controls
    MAX_DAILY_REQUESTS: int = 1400
    MAX_DAILY_AI_COST_USD: float = 2.00
    MAX_MONTHLY_AI_COST_USD: float = 30.00
    MAX_OUTREACH_PER_DAY: int = 5
    MAX_PENDING_APPROVALS: int = 10

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    SCHEDULER_EMBEDDED: bool = True

    @model_validator(mode="after")
    def normalize_local_service_hosts(self):
        self.DATABASE_URL = _normalize_postgres_driver(self.DATABASE_URL)
        self.DATABASE_MIGRATION_URL = _normalize_postgres_driver(self.DATABASE_MIGRATION_URL)
        if self.APP_ENV.lower() == "development" and not self.RUNNING_IN_DOCKER:
            self.DATABASE_URL = _rewrite_hostname(self.DATABASE_URL, {"postgres": "localhost"})
            self.DATABASE_MIGRATION_URL = _rewrite_hostname(
                self.DATABASE_MIGRATION_URL, {"postgres": "localhost"}
            )
            self.REDIS_URL = _rewrite_hostname(self.REDIS_URL, {"redis": "localhost"})
            self.CELERY_BROKER_URL = _rewrite_hostname(self.CELERY_BROKER_URL, {"redis": "localhost"})
            self.CELERY_RESULT_BACKEND = _rewrite_hostname(
                self.CELERY_RESULT_BACKEND, {"redis": "localhost"}
            )
        return self

    @staticmethod
    def _looks_placeholder(value: str) -> bool:
        lowered = (value or "").strip().lower()
        return (
            not lowered
            or lowered.startswith("your_")
            or lowered.startswith("paste_")
            or "paste_" in lowered
            or "changeme" in lowered
            or "change-me" in lowered
            or "development-secret" in lowered
            or "replace" in lowered
            or "placeholder" in lowered
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
    def IS_SUPABASE_SESSION_MODE(self) -> bool:
        return self.IS_SUPABASE and self.DATABASE_PORT == 5432 and "pooler.supabase.com" in self.DATABASE_HOST

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
        return (self.CSRF_SECRET or self.SECRET_KEY).strip()

    @property
    def JWT_KEYSET(self) -> dict[str, str]:
        if self.JWT_SIGNING_KEYS.strip():
            try:
                parsed = json.loads(self.JWT_SIGNING_KEYS)
            except json.JSONDecodeError as exc:
                raise RuntimeError("JWT_SIGNING_KEYS must be valid JSON") from exc
            if not isinstance(parsed, dict) or not parsed:
                raise RuntimeError("JWT_SIGNING_KEYS must be a non-empty JSON object")
            return {str(key): str(value) for key, value in parsed.items() if str(value).strip()}
        return {self.JWT_ACTIVE_KID: self.SECRET_KEY}

    @property
    def ACTIVE_JWT_SIGNING_KEY(self) -> str:
        key = self.JWT_KEYSET.get(self.JWT_ACTIVE_KID)
        if not key:
            raise RuntimeError(f"JWT active kid '{self.JWT_ACTIVE_KID}' missing from JWT_KEYSET")
        return key

    def _entropy(self, value: str) -> float:
        if not value:
            return 0.0
        counts = Counter(value)
        total = len(value)
        return -sum((count / total) * math.log2(count / total) for count in counts.values())

    def validate_production_configuration(self) -> None:
        if not self.STRICT_BOOTSTRAP:
            return

        errors: list[str] = []
        if len((self.SECRET_KEY or "").strip()) < 64:
            errors.append("SECRET_KEY must be at least 64 characters in production")
        if self._entropy(self.SECRET_KEY) < 4.0:
            errors.append("SECRET_KEY does not have enough entropy")
        if self._looks_placeholder(self.ENCRYPTION_KEY):
            errors.append("ENCRYPTION_KEY must be configured in production")
        if not self.JWT_KEYSET:
            errors.append("JWT signing keys must be configured in production")
        for kid, signing_key in self.JWT_KEYSET.items():
            if self._looks_placeholder(signing_key) or len(signing_key.strip()) < 64:
                errors.append(f"JWT signing key '{kid}' must be a non-placeholder 64+ character secret")
        if not self.HAS_REAL_TELEGRAM_TOKEN or not self.HAS_REAL_TELEGRAM_CHAT_ID:
            errors.append("Telegram control-plane credentials must be configured in production")
        if self._looks_placeholder(self.ALERTMANAGER_WEBHOOK_TOKEN):
            errors.append("ALERTMANAGER_WEBHOOK_TOKEN must be configured in production")
        if not self.CORS_ORIGINS:
            errors.append("ALLOWED_CORS_ORIGINS must not be empty in production")
        if self._looks_placeholder(self.BACKUP_BUCKET):
            errors.append("BACKUP_BUCKET must be configured in production")
        if self._looks_placeholder(self.BACKUP_ENCRYPTION_PUBLIC_KEY):
            errors.append("BACKUP_ENCRYPTION_PUBLIC_KEY must be configured in production")
        if self._looks_placeholder(self.BACKUP_ENCRYPTION_PRIVATE_KEY_FILE):
            errors.append("BACKUP_ENCRYPTION_PRIVATE_KEY_FILE must be configured in production")
        redis_passwords = [
            urlsplit(self.REDIS_URL).password,
            urlsplit(self.CELERY_BROKER_URL).password,
            urlsplit(self.CELERY_RESULT_BACKEND).password,
        ]
        if any(self._looks_placeholder(password or "") for password in redis_passwords):
            errors.append("Redis URLs must include non-placeholder passwords in production")
        if (
            self._looks_placeholder(self.APP_BASE_URL)
            or "localhost" in self.APP_BASE_URL.lower()
            or "example.com" in self.APP_BASE_URL.lower()
        ):
            errors.append("APP_BASE_URL must be a real production URL")
        if (
            self._looks_placeholder(self.FRONTEND_URL)
            or "localhost" in self.FRONTEND_URL.lower()
            or "example.com" in self.FRONTEND_URL.lower()
        ):
            errors.append("FRONTEND_URL must be a real production URL")
        if any(
            self._looks_placeholder(origin)
            or "localhost" in origin.lower()
            or "example.com" in origin.lower()
            for origin in self.CORS_ORIGINS
        ):
            errors.append("ALLOWED_CORS_ORIGINS must contain only real production origins")
        if self.REQUIRE_SUPABASE and not self.IS_SUPABASE:
            errors.append("DATABASE_URL must point to Supabase when REQUIRE_SUPABASE=true")
        if self.DATABASE_MIGRATION_URL and self.REQUIRE_SUPABASE and not self.IS_MIGRATION_SUPABASE:
            errors.append("DATABASE_MIGRATION_URL must point to Supabase when REQUIRE_SUPABASE=true")

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

        if errors:
            raise RuntimeError(
                "Production security configuration is invalid: " + "; ".join(sorted(set(errors)))
            )

settings = Settings()
