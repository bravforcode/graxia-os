"""Unified quant_os configuration — DEPRECATED.

.. deprecated::
    Use ``from core.config import get_config`` instead.
    ``QuantConfig`` (core/config.py) is the single source of truth.
    This module remains for backward compatibility only and will be removed.

Usage (deprecated):
    from config.unified_settings import settings
    print(settings.MT5_SERVER)

Usage (correct):
    from core.config import get_config
    cfg = get_config()
    print(cfg.mt5_server)
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class QuantSettings(BaseSettings):
    """Enterprise-grade trading configuration.

    All settings load from environment variables or .env file.
    Nested settings use ``__`` delimiter: ``QUANT_MT5__SERVER=xxx``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="QUANT_",
    )

    # ── MT5 / Broker ──────────────────────────────────────────────
    MT5_SERVER: str = "ICMarkets-Demo"
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_PATH: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    BROKER_NAME: str = "pepperstone"

    # ── Risk (all in basis points) ────────────────────────────────
    RISK_PER_TRADE_BPS: int = 100
    MAX_DAILY_LOSS_BPS: int = 200
    MAX_WEEKLY_LOSS_BPS: int = 500
    MAX_TOTAL_DRAWDOWN_BPS: int = 1000
    MAX_OPEN_POSITIONS: int = 5
    MAX_ORDERS_PER_DAY: int = 3
    MAX_SYMBOL_EXPOSURE_BPS: int = 100
    SLIPPAGE_TOLERANCE_BPS: int = 5

    # ── Data ──────────────────────────────────────────────────────
    WAREHOUSE_PATH: str = "data/warehouse"
    DUCKDB_PATH: str = "data_pipeline/storage/quant_os.duckdb"
    CHROMA_PATH: str = "data_pipeline/storage/chroma_db"

    # ── Execution ─────────────────────────────────────────────────
    EXECUTION_ENABLED: bool = False
    TRADING_MODE: str = Field(default="paper", pattern="^(paper|live)$")
    ACCOUNT_MODE_REQUIRED: str = "DEMO"

    # ── Telegram ──────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ── API ───────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_KEY: str = "brav-os-secret-key"
    JWT_SECRET_KEY: str = "change-me-in-production"
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Database ──────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://graxia:graxia@localhost:5432/quant_os"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Autonomous Loop ───────────────────────────────────────────
    AUTO_SYMBOLS: list[str] = Field(default=["XAUUSD", "BTCUSD", "ETHUSD"])
    AUTO_TIMEFRAMES: list[str] = Field(default=["15m", "1h", "4h"])
    AUTO_CHART_POLL_SECONDS: int = 60
    AUTO_DECISION_COOLDOWN: int = 300
    AUTO_LLM_TIMEOUT: float = 30.0
    AUTO_LLM_MIN_CONFIDENCE: float = 0.65
    AUTO_LLM_USE_SCREENSHOT: bool = True
    AUTO_MAX_POSITIONS: int = 3
    AUTO_MAX_DAILY_TRADES: int = 10
    AUTO_MAX_DAILY_LOSS_PCT: float = 3.0
    AUTO_TV_CDP_ENABLED: bool = True

    # ── LLM Rate Limits ───────────────────────────────────────────
    RATE_LIMIT_GROQ_DAILY: int = 900
    RATE_LIMIT_CEREBRAS_DAILY: int = 13000
    RATE_LIMIT_OPENROUTER_DAILY: int = 45

    # ── Monitoring ────────────────────────────────────────────────
    PROMETHEUS_PORT: int = 9090
    GRAFANA_PORT: int = 3000
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "production"

    # ── Data Pipeline ─────────────────────────────────────────────
    ALPHAVANTAGE_API_KEY: str = ""
    FRED_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"

    # ── QuantConnect Cloud ────────────────────────────────────────
    QUANTCONNECT_USER_ID: str = ""
    QUANTCONNECT_API_TOKEN: str = ""
    QUANTCONNECT_PROJECT_ID: int = 0

    # ── Oanda (Forex/CFD) ────────────────────────────────────────
    OANDA_ACCESS_TOKEN: str = ""
    OANDA_ACCOUNT_ID: str = ""
    OANDA_ENVIRONMENT: str = "Practice"

    # ── Polygon.io ───────────────────────────────────────────────
    POLYGON_API_KEY: str = ""

    # ── LLM Providers ────────────────────────────────────────────
    DEFAULT_LLM_MODEL: str = "gpt-4-turbo"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── Telegram (extended — was: TELEGRAM_BOT_TOKEN/CHAT_ID) ───
    # Existing fields kept above for backward-compat; extended below.
    TELEGRAM_ALERTS_ENABLED: bool = True
    TELEGRAM_ALERT_LEVEL: str = Field(
        default="info",
        pattern="^(info|warning|critical)$",
        description="Minimum alert level for Telegram notifications",
    )
    TELEGRAM_STANDBY_WEBHOOK_URL: str = Field(
        default="",
        description="Standby VPS takeover endpoint (overrides .env STANDBY_WEBHOOK_URL)",
    )
    TELEGRAM_TIMEOUT_SECONDS: float = Field(
        default=5.0,
        description="HTTP timeout for Telegram API calls",
    )

    # ── TradingView MCP Client ──────────────────────────────────
    TV_MCP_URL: str = "http://localhost:30001"
    TV_DEFAULT_TIMEFRAME: str = "1D"
    TV_SCREEN_EXCHANGE: str = "NASDAQ"
    TV_REQUEST_TIMEOUT: float = 30.0
    TV_MAX_RETRIES: int = 3
    TV_RETRY_BACKOFF: float = 1.0

    # ── TradingView CDP Bridge ──────────────────────────────────
    TV_CDP_URL: str = "http://localhost:9222"
    TV_CDP_TIMEOUT: int = 30
    TV_CDP_CHROME_PATH: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    TV_CDP_USER_DATA_DIR: str = r"C:\chrome-debug"
    TV_SELECTOR_SYMBOL_INPUT: str = "input[data-role='search'][class*='search']"
    TV_SELECTOR_TIMEFRAME_BTN: str = "button[data-role='timeframe']"
    TV_SELECTOR_PINE_EDITOR: str = ".pine-editor"
    TV_SELECTOR_PINE_CODE: str = ".pine-editor .view-lines"
    TV_SELECTOR_COMPILE_BTN: str = "button[data-name='compile']"
    TV_SELECTOR_WATCHLIST: str = ".watchlist"
    TV_SCREENSHOT_DIR: str = (
        r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\screenshots"
    )

    # ── PixelRAG Visual Search ──────────────────────────────────
    PIXELRAG_URL: str = "http://localhost:30002"
    PIXELRAG_HOST: str = "127.0.0.1"
    PIXELRAG_INDEX_DIR: Path = Path("data/visual_index")
    PIXELRAG_TILES_DIR: Path = Path("data/visual_tiles")
    PIXELRAG_DEFAULT_N_DOCS: int = 5
    PIXELRAG_REQUEST_TIMEOUT: float = 30.0
    PIXELRAG_MAX_RETRIES: int = 3
    PIXELRAG_RETRY_BACKOFF: float = 1.0
    PIXELSHOT_TIMEOUT: int = 120
    PIXELRAG_INDEX_TIMEOUT: int = 300
    PIXELRAG_SERVE_TIMEOUT: int = 300

    # ── Cost Calibration (data file pointer) ────────────────────
    COST_CALIBRATION_PATH: Path = Path("config/cost_calibration.json")
    COST_CALIBRATION_VERSION: str = "2.2"

    # ── Paper Trade (data file pointer) ─────────────────────────
    PAPER_TRADE_CONFIG_PATH: Path = Path("config/paper_trade_config.json")
    PAPER_TRADE_DEFAULT_PORTFOLIO_TYPE: str = "concentrated_4_asset"

    # ── Adjusted Verdicts (data file pointer) ───────────────────
    ADJUSTED_VERDICTS_PATH: Path = Path("config/adjusted_verdicts.json")

    # ── Broker Profile (data file pointers) ─────────────────────
    BROKER_PROFILE_PATH: Path = Path("config/broker_profile.yaml")
    BROKER_PROFILE_TEMPLATE_PATH: Path = Path("config/broker_profile.template.yaml")
    BROKER_PROFILE_SCHEMA_PATH: Path = Path("config/broker_profile.schema.json")

    # ── Failover ────────────────────────────────────────────────
    STANDBY_WEBHOOK_URL: str = Field(
        default="",
        description="Standby VPS failover endpoint (legacy env var name kept for .env compat)",
    )

    def model_post_init(self, __context) -> None:
        """Validate critical fields at startup. Warn on suspicious defaults."""
        import logging
        logger = logging.getLogger("quant_os.config")
        default_jwt = self.JWT_SECRET_KEY == "change-me-in-production"
        default_api = self.API_KEY == "brav-os-secret-key"
        if default_jwt:
            logger.warning("config.JWT_SECRET_KEY is default — set it in .env for security")
        if default_api:
            logger.warning("config.API_KEY is default — set it in .env for security")
        if self.TRADING_MODE == "live" and (default_jwt or default_api):
            raise ValueError(
                "Live mode requires non-default JWT_SECRET_KEY and API_KEY — "
                "set them in .env"
            )
        if self.TRADING_MODE == "live" and not self.MT5_PASSWORD:
            logger.error("config.MT5_PASSWORD is empty in live mode — broker will fail to connect")


# Singleton — import this everywhere
# DEPRECATED: Use ``from core.config import get_config`` instead.
warnings.warn(
    "config.unified_settings is deprecated. "
    "Use 'from core.config import get_config' instead. "
    "QuantConfig is the single source of truth.",
    DeprecationWarning,
    stacklevel=2,
)
settings = QuantSettings()
