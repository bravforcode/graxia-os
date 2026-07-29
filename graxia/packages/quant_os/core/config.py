"""Configuration management for Quant OS"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..risk.risk_policy import RiskPolicy
from .enums import SystemState, TradingMode
from .golden_rules import HARD_LIMITS


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
    shadow_mode: bool = False  # Read-only MT5 data + PaperAdapter execution (no real orders)
    log_level: str = "INFO"
    environment: str = "development"

    # ==================== DATABASE ====================
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    duckdb_path: str = "data/market_data.duckdb"

    # ==================== MT5 BROKER ====================
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = "Pepperstone-Demo"
    mt5_path: str = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
    mt5_timeout_ms: int = 10000

    # ==================== BROKER FALLBACK ====================
    primary_broker: str = "ic_markets"
    fallback_broker_1: str = "pepperstone"
    fallback_broker_2: str = "xm"

    # ==================== ACCOUNT DATA SOURCE ====================
    # Selects which adapter feeds account state. Values: "mt5" | "myfxbook" | "binance".
    # Myfxbook is a READ-ONLY analytics source and refuses trading operations.
    account_data_source: str = "mt5"
    myfxbook_email: str = ""
    myfxbook_password: str = ""

    # ==================== SECURITY ====================
    jwt_secret_key: str = ""
    webhook_hmac_secret: str = ""
    admin_api_key: str = ""
    model_signing_key: str = ""

    # ==================== NOTIFICATIONS ====================
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    line_channel_access_token: str = ""
    line_user_id: str = ""

    # ==================== TRADING SYMBOLS ====================
    symbols: list[str] = field(
        default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]
    )

    # ==================== TIMEFRAMES ====================
    primary_timeframe: str = "M15"
    higher_timeframes: list[str] = field(default_factory=lambda: ["H1", "H4"])

    # ==================== RISK LIMITS (canonical source: RiskPolicy) ====================
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)

    # Legacy aliases — delegate to risk_policy for backward compatibility
    @property
    def max_risk_per_trade_pct(self) -> float:
        return float(self.risk_policy.max_risk_per_trade_pct)

    @property
    def max_daily_loss_pct(self) -> float:
        return float(self.risk_policy.max_daily_loss_pct)

    @property
    def max_weekly_loss_pct(self) -> float:
        return float(self.risk_policy.max_weekly_loss_pct)

    @property
    def max_drawdown_pct(self) -> float:
        return float(self.risk_policy.max_drawdown_pct)

    @property
    def max_portfolio_exposure_pct(self) -> float:
        return 50.0  # Not in RiskPolicy — kept as config-level

    @property
    def max_positions(self) -> int:
        return int(self.risk_policy.max_open_positions)

    max_correlation_threshold: float = 0.7
    max_var_pct: float = 2.0

    # ==================== STRATEGY WEIGHTS ====================
    strategy_weights: dict = field(
        default_factory=lambda: {
            "mtm": 0.40,  # Multi-Timeframe Momentum
            "mrb": 0.25,  # Mean Reversion Bollinger
            "mlb": 0.35,  # ML-Enhanced Breakout
        }
    )
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

    def __post_init__(self) -> None:
        """Validate config against golden rules and hard limits"""
        self._validate_from_env()
        self._enforce_hard_limits()
        self._validate_mode_consistency()

    def _load_dotenv(self) -> None:
        """Load .env file if present. Existing env vars take precedence."""
        env_path = Path(".env")
        if not env_path.exists():
            return
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # Only set if not already in environment (env vars take precedence)
                    if key not in os.environ:
                        os.environ[key] = value
        except Exception:
            pass  # Silently ignore .env parse errors

    def _validate_from_env(self) -> None:
        """Load from environment variables and .env file"""
        # Load .env file if present (env vars already set take precedence)
        self._load_dotenv()

        # Trading mode — fail-closed: unrecognized modes raise, not silently paper
        mode_str = os.getenv("TRADING_MODE", "PAPER").upper()
        valid_modes = [m.value for m in TradingMode]
        if mode_str in valid_modes:
            self.trading_mode = TradingMode(mode_str)
        else:
            raise ValueError(f"TRADING_MODE='{mode_str}' is not recognized. " f"Valid modes: {valid_modes}")

        self.live_trading_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
        self.shadow_mode = os.getenv("SHADOW_MODE", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.environment = os.getenv("ENVIRONMENT", self.environment)

        # Database
        self.database_url = os.getenv("DATABASE_URL", self.database_url)
        self.redis_url = os.getenv("REDIS_URL", self.redis_url)
        self.duckdb_path = os.getenv("DUCKDB_PATH", self.duckdb_path)

        # MT5
        self.mt5_login = int(os.getenv("MT5_LOGIN", self.mt5_login))
        self.mt5_password = os.getenv("MT5_PASSWORD", self.mt5_password)
        self.mt5_server = os.getenv("MT5_SERVER", self.mt5_server)
        self.mt5_path = os.getenv("MT5_PATH", self.mt5_path)
        self.mt5_timeout_ms = int(os.getenv("MT5_TIMEOUT_MS", self.mt5_timeout_ms))

        # Account data source + Myfxbook credentials (read from env; never hard-coded)
        self.account_data_source = os.getenv("ACCOUNT_DATA_SOURCE", self.account_data_source).lower()
        self.myfxbook_email = os.getenv("MYFXBOOK_EMAIL", self.myfxbook_email)
        self.myfxbook_password = os.getenv("MYFXBOOK_PASSWORD", self.myfxbook_password)

        # Security
        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", self.jwt_secret_key)
        self.webhook_hmac_secret = os.getenv("WEBHOOK_HMAC_SECRET", self.webhook_hmac_secret)
        self.admin_api_key = os.getenv("ADMIN_API_KEY", self.admin_api_key)
        self.model_signing_key = os.getenv("MODEL_SIGNING_KEY", self.model_signing_key)

        # Notifications
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", self.telegram_bot_token)
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", self.telegram_chat_id)

        # Risk limits — loaded into risk_policy (env overrides the bps values)
        risk_per_trade_pct_env = os.getenv("RISK_PER_TRADE_PCT")
        if risk_per_trade_pct_env is not None:
            # Convert pct to bps: 1.0% = 100 bps
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=int(float(risk_per_trade_pct_env) * 100),
                max_daily_loss_bps=self.risk_policy.max_daily_loss_bps,
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=self.risk_policy.max_total_drawdown_bps,
                max_open_positions=self.risk_policy.max_open_positions,
            )

        max_daily_env = os.getenv("MAX_DAILY_LOSS_PCT")
        if max_daily_env is not None:
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=self.risk_policy.risk_per_trade_bps,
                max_daily_loss_bps=int(float(max_daily_env) * 100),
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=self.risk_policy.max_total_drawdown_bps,
                max_open_positions=self.risk_policy.max_open_positions,
            )

        max_dd_env = os.getenv("MAX_DRAWDOWN_PCT")
        if max_dd_env is not None:
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=self.risk_policy.risk_per_trade_bps,
                max_daily_loss_bps=self.risk_policy.max_daily_loss_bps,
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=int(float(max_dd_env) * 100),
                max_open_positions=self.risk_policy.max_open_positions,
            )

        max_pos_env = os.getenv("MAX_POSITIONS")
        if max_pos_env is not None:
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=self.risk_policy.risk_per_trade_bps,
                max_daily_loss_bps=self.risk_policy.max_daily_loss_bps,
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=self.risk_policy.max_total_drawdown_bps,
                max_open_positions=int(max_pos_env),
            )

        # Paper trading
        self.paper_initial_capital = float(os.getenv("PAPER_INITIAL_CAPITAL", self.paper_initial_capital))

        # Micro trading
        self.micro_max_position_size = float(os.getenv("MICRO_MAX_POSITION_SIZE", self.micro_max_position_size))

    def _enforce_hard_limits(self) -> None:
        """Ensure soft limits don't exceed hard limits"""
        # Enforce via RiskPolicy properties
        risk_pct = float(self.risk_policy.max_risk_per_trade_pct)
        if risk_pct > HARD_LIMITS["max_risk_per_trade_pct"]:
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=int(HARD_LIMITS["max_risk_per_trade_pct"] * 100),
                max_daily_loss_bps=self.risk_policy.max_daily_loss_bps,
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=self.risk_policy.max_total_drawdown_bps,
                max_open_positions=self.risk_policy.max_open_positions,
            )

        dd_pct = float(self.risk_policy.max_drawdown_pct)
        if dd_pct > HARD_LIMITS["max_drawdown_pct"]:
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=self.risk_policy.risk_per_trade_bps,
                max_daily_loss_bps=self.risk_policy.max_daily_loss_bps,
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=int(HARD_LIMITS["max_drawdown_pct"] * 100),
                max_open_positions=self.risk_policy.max_open_positions,
            )

        daily_pct = float(self.risk_policy.max_daily_loss_pct)
        if daily_pct > HARD_LIMITS["max_daily_loss_pct"]:
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=self.risk_policy.risk_per_trade_bps,
                max_daily_loss_bps=int(HARD_LIMITS["max_daily_loss_pct"] * 100),
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=self.risk_policy.max_total_drawdown_bps,
                max_open_positions=self.risk_policy.max_open_positions,
            )

        if self.max_positions > HARD_LIMITS["max_positions"]:
            self.risk_policy = RiskPolicy(
                risk_per_trade_bps=self.risk_policy.risk_per_trade_bps,
                max_daily_loss_bps=self.risk_policy.max_daily_loss_bps,
                max_weekly_loss_bps=self.risk_policy.max_weekly_loss_bps,
                max_total_drawdown_bps=self.risk_policy.max_total_drawdown_bps,
                max_open_positions=int(HARD_LIMITS["max_positions"]),
            )

    def _validate_mode_consistency(self) -> None:
        """Ensure trading mode and live flag are consistent"""
        if self.trading_mode == TradingMode.PAPER and self.live_trading_enabled:
            raise ValueError("Cannot enable live trading in PAPER mode")

        if self.live_trading_enabled and self.trading_mode not in [
            TradingMode.LIVE_MICRO,
            TradingMode.LIVE_LIMITED,
            TradingMode.LIVE_CONTROLLED,
        ]:
            raise ValueError("Live trading only allowed in LIVE_MICRO, LIVE_LIMITED, or LIVE_CONTROLLED mode")

        # Shadow mode: read-only MT5 data + paper execution. Incompatible with live trading.
        if self.shadow_mode and self.live_trading_enabled:
            raise ValueError("Cannot enable shadow_mode and live_trading_enabled simultaneously")

        # Validate secrets when live trading is enabled
        if self.live_trading_enabled:
            missing = []
            if not self.jwt_secret_key:
                missing.append("JWT_SECRET_KEY")
            if not self.webhook_hmac_secret:
                missing.append("WEBHOOK_HMAC_SECRET")
            if not self.admin_api_key:
                missing.append("ADMIN_API_KEY")
            if missing:
                raise ValueError(f"Live trading requires secrets: {', '.join(missing)}")

    def get_mode_risk_limits(self) -> dict:
        """Get risk limits for current trading mode"""
        rp = self.risk_policy
        limits = {
            TradingMode.PAPER: {
                "max_risk_per_trade_pct": float(rp.max_risk_per_trade_pct),
                "max_daily_loss_pct": float(rp.max_daily_loss_pct),
                "max_position_size": float("inf"),  # No limit in paper
                "requires_human_confirm": False,
            },
            TradingMode.LIVE_MICRO: {
                "max_risk_per_trade_pct": min(float(rp.max_risk_per_trade_pct), 0.5),
                "max_daily_loss_pct": min(float(rp.max_daily_loss_pct), 1.5),
                "max_position_size": self.micro_max_position_size,
                "requires_human_confirm": True,
                "order_expiry_seconds": self.micro_order_expiry_seconds,
            },
            TradingMode.LIVE_LIMITED: {
                "max_risk_per_trade_pct": float(rp.max_risk_per_trade_pct),
                "max_daily_loss_pct": float(rp.max_daily_loss_pct),
                "max_position_size": self.limited_max_position_size,
                "requires_human_confirm": False,
                "max_daily_trades": self.limited_max_daily_trades,
            },
            TradingMode.LIVE_CONTROLLED: {
                "max_risk_per_trade_pct": float(rp.max_risk_per_trade_pct),
                "max_daily_loss_pct": float(rp.max_daily_loss_pct),
                "max_position_size": float("inf"),  # Higher limits
                "requires_human_confirm": False,
            },
        }
        return limits.get(self.trading_mode, limits[TradingMode.PAPER])


# Global config instance - initialized once
_config: QuantConfig | None = None


def get_config() -> QuantConfig:
    """Get or create global config instance"""
    global _config
    if _config is None:
        _config = QuantConfig()
    return _config


def reset_config() -> None:
    """Reset config (for testing)"""
    global _config
    _config = None


# Backward-compat alias — several modules import ``get_settings`` which was
# the original name before the rename to ``get_config``.
get_settings = get_config
