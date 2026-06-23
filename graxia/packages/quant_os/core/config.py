"""Configuration management for Quant OS"""

import os
import hashlib
from collections.abc import Mapping
from typing import Any, List, Optional
from dataclasses import dataclass, field

from .golden_rules import GOLDEN_RULES, HARD_LIMITS
from .enums import TradingMode, SystemState

BROKER_CREDENTIAL_ENV_KEYS = ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")
BROKER_CREDENTIAL_CONFIG_KEYS = ("login", "password", "server")


def _has_nonempty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def find_forbidden_broker_config_keys(config: Mapping[str, Any], prefix: str = "") -> list[str]:
    """Return credential-shaped config keys that violate terminal-session-only policy."""
    forbidden: list[str] = []
    for key, value in config.items():
        qualified_key = f"{prefix}.{key}" if prefix else str(key)
        if key in BROKER_CREDENTIAL_CONFIG_KEYS and _has_nonempty_value(value):
            forbidden.append(qualified_key)
        if isinstance(value, Mapping):
            forbidden.extend(find_forbidden_broker_config_keys(value, qualified_key))
    return forbidden


def reject_broker_credential_config(config: Mapping[str, Any], context: str = "MT5 config") -> None:
    """Fail closed if repo-owned config includes broker credentials."""
    forbidden = find_forbidden_broker_config_keys(config)
    if forbidden:
        keys = ", ".join(sorted(forbidden))
        raise ValueError(
            f"{context} contains forbidden broker credential keys: {keys}. "
            "Use terminal-session-only MT5 authentication."
        )


def hash_terminal_session_value(value: Any) -> str:
    """Stable SHA-256 helper for redacted runtime evidence."""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


@dataclass
class QuantConfig:
    """
    Quant OS Configuration
    
    Environment variables override defaults, but cannot exceed HARD_LIMITS.
    """
    
    # ==================== SYSTEM MODE ====================
    trading_mode: TradingMode = TradingMode.PAPER
    system_state: SystemState = SystemState.PAPER_TRADING
    live_trading_enabled: bool = False
    log_level: str = "INFO"
    
    # ==================== DATABASE ====================
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    
    # ==================== MT5 TERMINAL ====================
    mt5_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    mt5_timeout_ms: int = 10000
    
    # ==================== BROKER FALLBACK ====================
    primary_broker: str = "ic_markets"
    fallback_broker_1: str = "pepperstone"
    fallback_broker_2: str = "xm"
    
    # ==================== SECURITY ====================
    jwt_secret_key: str = ""
    webhook_hmac_secret: str = ""
    admin_api_key: str = ""
    
    # ==================== NOTIFICATIONS ====================
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    line_channel_access_token: str = ""
    line_user_id: str = ""
    
    # ==================== TRADING SYMBOLS ====================
    symbols: List[str] = field(default_factory=lambda: [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", 
        "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"
    ])
    
    # ==================== TIMEFRAMES ====================
    primary_timeframe: str = "M15"
    higher_timeframes: List[str] = field(default_factory=lambda: ["H1", "H4"])
    
    # ==================== RISK LIMITS (soft limits) ====================
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 2.0
    max_weekly_loss_pct: float = 5.0
    max_drawdown_pct: float = 10.0
    max_portfolio_exposure_pct: float = 50.0
    max_positions: int = 5
    max_correlation_threshold: float = 0.7
    
    # ==================== STRATEGY WEIGHTS ====================
    strategy_weights: dict = field(default_factory=lambda: {
        "mtm": 0.40,   # Multi-Timeframe Momentum
        "mrb": 0.25,   # Mean Reversion Bollinger
        "mlb": 0.35,   # ML-Enhanced Breakout
    })
    ensemble_confidence_threshold: float = 0.60
    
    # ==================== ML SETTINGS ====================
    ml_min_confidence: float = 0.65
    ml_model_path: str = "./ml/models"
    ml_retrain_interval_days: int = 7
    ml_drift_threshold: float = 0.10
    
    # ==================== LOT SIZE ====================
    units_per_lot: float = 100000.0
    
    # ==================== PAPER TRADING ====================
    paper_initial_capital: float = 10000.0
    paper_slippage_pips: float = 0.5
    paper_commission_per_lot: float = 3.5
    
    # ==================== LIVE MICRO ====================
    micro_max_position_size: float = 1000.0
    micro_daily_order_limit: int = 5
    micro_order_expiry_seconds: int = 60
    
    # ==================== LIVE LIMITED ====================
    limited_max_position_size: float = 5000.0
    limited_max_daily_trades: int = 10
    
    # ==================== BACKTEST ====================
    backtest_start_date: str = "2020-01-01"
    backtest_end_date: str = "2024-12-31"
    backtest_slippage_pips: float = 0.5
    backtest_commission_per_lot: float = 3.5
    
    # ==================== WEBHOOK ====================
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000
    webhook_path: str = "/webhook"
    
    # ==================== MONITORING ====================
    prometheus_port: int = 9090
    sentry_dsn: str = ""
    health_check_interval_seconds: int = 30
    
    def __post_init__(self):
        """Validate config against golden rules and hard limits"""
        self._validate_from_env()
        self._enforce_hard_limits()
        self._validate_mode_consistency()
    
    def _validate_from_env(self):
        """Load from environment variables"""
        # Trading mode
        mode_str = os.getenv("TRADING_MODE", "PAPER").upper()
        self.trading_mode = TradingMode(mode_str) if mode_str in [m.value for m in TradingMode] else TradingMode.PAPER
        
        self.live_trading_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # Database
        self.database_url = os.getenv("DATABASE_URL", self.database_url)
        self.redis_url = os.getenv("REDIS_URL", self.redis_url)
        
        # MT5 terminal-session-only policy
        self._reject_broker_credentials()
        self.mt5_path = os.getenv("MT5_PATH", self.mt5_path)
        self.mt5_timeout_ms = int(os.getenv("MT5_TIMEOUT_MS", self.mt5_timeout_ms))
        
        # Security
        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", self.jwt_secret_key)
        self.webhook_hmac_secret = os.getenv("WEBHOOK_HMAC_SECRET", self.webhook_hmac_secret)
        self.admin_api_key = os.getenv("ADMIN_API_KEY", self.admin_api_key)
        
        # Notifications
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", self.telegram_bot_token)
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", self.telegram_chat_id)
        
        # Risk limits (soft - can be overridden by env but not hard limits)
        self.max_risk_per_trade_pct = float(os.getenv("RISK_PER_TRADE_PCT", self.max_risk_per_trade_pct))
        self.max_daily_loss_pct = float(os.getenv("MAX_DAILY_LOSS_PCT", self.max_daily_loss_pct))
        self.max_drawdown_pct = float(os.getenv("MAX_DRAWDOWN_PCT", self.max_drawdown_pct))
        self.max_positions = int(os.getenv("MAX_POSITIONS", self.max_positions))
        
        # Paper trading
        self.paper_initial_capital = float(os.getenv("PAPER_INITIAL_CAPITAL", self.paper_initial_capital))
        
        # Micro trading
        self.micro_max_position_size = float(os.getenv("MICRO_MAX_POSITION_SIZE", self.micro_max_position_size))

    def _reject_broker_credentials(self):
        """Fail closed if broker credentials are injected via env."""
        forbidden = [key for key in BROKER_CREDENTIAL_ENV_KEYS if os.getenv(key, "").strip()]
        if forbidden:
            keys = ", ".join(forbidden)
            raise ValueError(
                f"Broker credential env vars are forbidden: {keys}. "
                "Use terminal-session-only MT5 authentication."
            )

    def assert_terminal_session_only(self) -> None:
        """Defend against credential-shaped attributes being injected onto config objects."""
        self._reject_broker_credentials()
        forbidden = []
        for attr in ("mt5_login", "mt5_password", "mt5_server"):
            if _has_nonempty_value(getattr(self, attr, None)):
                forbidden.append(attr)
        if forbidden:
            keys = ", ".join(sorted(forbidden))
            raise ValueError(
                f"Broker credential config fields are forbidden: {keys}. "
                "Use terminal-session-only MT5 authentication."
            )
    
    def _enforce_hard_limits(self):
        """Ensure soft limits don't exceed hard limits"""
        self.max_risk_per_trade_pct = min(self.max_risk_per_trade_pct, HARD_LIMITS["max_risk_per_trade_pct"])
        self.max_drawdown_pct = min(self.max_drawdown_pct, HARD_LIMITS["max_drawdown_pct"])
        self.max_daily_loss_pct = min(self.max_daily_loss_pct, HARD_LIMITS["max_daily_loss_pct"])
        self.max_portfolio_exposure_pct = min(self.max_portfolio_exposure_pct, HARD_LIMITS["max_portfolio_exposure_pct"])
        self.max_positions = min(self.max_positions, HARD_LIMITS["max_positions"])
    
    def _validate_mode_consistency(self):
        """Ensure trading mode and live flag are consistent"""
        if self.trading_mode == TradingMode.PAPER and self.live_trading_enabled:
            raise ValueError("Cannot enable live trading in PAPER mode")
        
        if self.live_trading_enabled and self.trading_mode not in [TradingMode.LIVE_MICRO, TradingMode.LIVE_LIMITED, TradingMode.LIVE_CONTROLLED]:
            raise ValueError("Live trading only allowed in LIVE_MICRO, LIVE_LIMITED, or LIVE_CONTROLLED mode")
    
    def get_mode_risk_limits(self) -> dict:
        """Get risk limits for current trading mode"""
        limits = {
            TradingMode.PAPER: {
                "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
                "max_daily_loss_pct": self.max_daily_loss_pct,
                "max_position_size": float('inf'),  # No limit in paper
                "requires_human_confirm": False,
            },
            TradingMode.LIVE_MICRO: {
                "max_risk_per_trade_pct": min(self.max_risk_per_trade_pct, 0.5),
                "max_daily_loss_pct": min(self.max_daily_loss_pct, 1.5),
                "max_position_size": self.micro_max_position_size,
                "requires_human_confirm": True,
                "order_expiry_seconds": self.micro_order_expiry_seconds,
            },
            TradingMode.LIVE_LIMITED: {
                "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
                "max_daily_loss_pct": self.max_daily_loss_pct,
                "max_position_size": self.limited_max_position_size,
                "requires_human_confirm": False,
                "max_daily_trades": self.limited_max_daily_trades,
            },
            TradingMode.LIVE_CONTROLLED: {
                "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
                "max_daily_loss_pct": self.max_daily_loss_pct,
                "max_position_size": float('inf'),  # Higher limits
                "requires_human_confirm": False,
            },
        }
        return limits.get(self.trading_mode, limits[TradingMode.PAPER])


# Global config instance - initialized once
_config: Optional[QuantConfig] = None


def get_config() -> QuantConfig:
    """Get or create global config instance"""
    global _config
    if _config is None:
        _config = QuantConfig()
    return _config


def reset_config():
    """Reset config (for testing)"""
    global _config
    _config = None
