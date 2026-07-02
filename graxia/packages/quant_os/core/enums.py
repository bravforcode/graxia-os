"""System enums for Quant OS"""

from enum import Enum


class SystemState(str, Enum):
    """System operating states"""

    RESEARCH_ONLY = "RESEARCH_ONLY"
    BACKTEST_ONLY = "BACKTEST_ONLY"
    SHADOW_MODE = "SHADOW_MODE"  # Signals without execution
    PAPER_TRADING = "PAPER_TRADING"  # Simulated execution
    LIVE_MICRO = "LIVE_MICRO"  # Tiny real positions (human confirm)
    LIVE_LIMITED = "LIVE_LIMITED"  # Small real positions
    LIVE_CONTROLLED = "LIVE_CONTROLLED"  # Scaled real positions


class TradingMode(str, Enum):
    """Trading mode - determines risk limits and approval flow"""

    PAPER = "PAPER"
    LIVE_MICRO = "LIVE_MICRO"
    LIVE_LIMITED = "LIVE_LIMITED"
    LIVE_CONTROLLED = "LIVE_CONTROLLED"


class OrderStatus(str, Enum):
    """Order state machine states — single source of truth."""

    # --- Core lifecycle ---
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    RISK_APPROVED = "RISK_APPROVED"
    COMPLIANCE_APPROVED = "COMPLIANCE_APPROVED"
    PENDING_HUMAN = "PENDING_HUMAN"
    SENT_TO_BROKER = "SENT_TO_BROKER"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"
    # --- Broker adapter states ---
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    # --- Execution state machine states ---
    SIGNAL_CREATED = "SIGNAL_CREATED"
    RISK_CHECKED = "RISK_CHECKED"
    ORDER_PRECHECKED = "ORDER_PRECHECKED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACKNOWLEDGED = "ORDER_ACKNOWLEDGED"
    PROTECTIVE_STOPS_PENDING = "PROTECTIVE_STOPS_PENDING"
    PROTECTIVE_STOPS_VERIFIED = "PROTECTIVE_STOPS_VERIFIED"
    POSITION_RECONCILED = "POSITION_RECONCILED"
    CLOSED = "CLOSED"
    DEAL_RECONCILED = "DEAL_RECONCILED"
    AUDITED = "AUDITED"
    CRITICAL_INCIDENT = "CRITICAL_INCIDENT"


class OrderSide(str, Enum):
    """Order side"""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type"""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    """Order time in force"""

    DAY = "DAY"
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill


class RegimeType(str, Enum):
    """Market regime classification"""

    TREND_STRONG_UP = "TREND_STRONG_UP"
    TREND_STRONG_DOWN = "TREND_STRONG_DOWN"
    TREND_WEAK = "TREND_WEAK"
    RANGE_BOUND = "RANGE_BOUND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    CRISIS = "CRISIS"
    NEWS_DRIVEN = "NEWS_DRIVEN"
    ILLIQUID = "ILLIQUID"
    ABNORMAL_SPREAD = "ABNORMAL_SPREAD"
    UNCERTAIN = "UNCERTAIN"


class KillSwitchType(str, Enum):
    """Kill switch trigger types"""

    MANUAL = "MANUAL"
    DAILY_LOSS = "DAILY_LOSS"
    DRAWDOWN = "DRAWDOWN"
    WEEKLY_LOSS = "WEEKLY_LOSS"
    DATA_QUALITY = "DATA_QUALITY"
    BROKER_EXECUTION = "BROKER_EXECUTION"
    OPERATIONAL = "OPERATIONAL"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    STALE_DATA = "STALE_DATA"
    HEARTBEAT_FAIL = "HEARTBEAT_FAIL"


class IncidentSeverity(str, Enum):
    """Incident severity levels"""

    P0 = "P0"  # Critical - wake up now
    P1 = "P1"  # High - 15 min response
    P2 = "P2"  # Medium - same day
    P3 = "P3"  # Low - next day


class StrategyStatus(str, Enum):
    """Strategy lifecycle status"""

    HYPOTHESIS = "HYPOTHESIS"
    BACKTESTED = "BACKTESTED"
    PAPER = "PAPER"
    LIVE_MICRO = "LIVE_MICRO"
    LIVE = "LIVE"
    DEPRECATED = "DEPRECATED"


class ModelStatus(str, Enum):
    """ML model lifecycle status"""

    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    LIVE_MICRO = "LIVE_MICRO"
    LIVE = "LIVE"
    DEPRECATED = "DEPRECATED"


class DataSourceTier(str, Enum):
    """Data source quality tiers"""

    TIER_1 = "TIER_1"  # Production: broker official, Bloomberg
    TIER_2 = "TIER_2"  # Research: paid historical providers
    TIER_3 = "TIER_3"  # Indicative: Yahoo, Google Finance
    TIER_0 = "TIER_0"  # FORBIDDEN: scraped, unlicensed


class SignalType(str, Enum):
    """Trading signal types"""

    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    HOLD = "HOLD"


class DecisionType(str, Enum):
    """Decision engine outputs"""

    BUY = "BUY"
    SELL = "SELL"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"
    ABSTAIN_INSUFFICIENT_EDGE = "ABSTAIN_INSUFFICIENT_EDGE"
    ABSTAIN_DATA_QUALITY = "ABSTAIN_DATA_QUALITY"
    ABSTAIN_RISK_LIMIT = "ABSTAIN_RISK_LIMIT"
    ABSTAIN_MARKET_CONDITION = "ABSTAIN_MARKET_CONDITION"


class PositionType(str, Enum):
    """Position direction"""

    LONG = "LONG"
    SHORT = "SHORT"


class CloseReason(str, Enum):
    """Position close reasons"""

    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TRAILING_STOP = "TRAILING_STOP"
    MANUAL = "MANUAL"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    KILL_SWITCH = "KILL_SWITCH"
    EXPIRED = "EXPIRED"
    REVERSE_SIGNAL = "REVERSE_SIGNAL"
    AMBIGUOUS = "AMBIGUOUS"


class ReconciliationStatus(str, Enum):
    """Reconciliation result status"""

    CLEAN = "CLEAN"
    MISMATCH = "MISMATCH"
    ERROR = "ERROR"


class TradeOutcome(str, Enum):
    """Trade outcome classification"""

    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


class RiskCheckResult(str, Enum):
    """Risk check outcomes"""

    PASS = "PASS"
    FAIL_POSITION_SIZE = "FAIL_POSITION_SIZE"
    FAIL_EXPOSURE = "FAIL_EXPOSURE"
    FAIL_DAILY_LOSS = "FAIL_DAILY_LOSS"
    FAIL_DRAWDOWN = "FAIL_DRAWDOWN"
    FAIL_CORRELATION = "FAIL_CORRELATION"
    FAIL_LIQUIDITY = "FAIL_LIQUIDITY"
    FAIL_DATA_STALE = "FAIL_DATA_STALE"
    FAIL_COOLDOWN = "FAIL_COOLDOWN"
    FAIL_MAX_POSITIONS = "FAIL_MAX_POSITIONS"


class DataQualityCheck(str, Enum):
    """Data quality validation types"""

    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    OUTLIER_PRICE = "OUTLIER_PRICE"
    NEGATIVE_PRICE = "NEGATIVE_PRICE"
    ZERO_VOLUME = "ZERO_VOLUME"
    STALE_QUOTE = "STALE_QUOTE"
    GAP_DETECTED = "GAP_DETECTED"
    SESSION_BOUNDARY = "SESSION_BOUNDARY"


class StrategyGroup(str, Enum):
    """Strategy classification"""

    MOMENTUM = "MOMENTUM"
    MEAN_REVERSION = "MEAN_REVERSION"
    BREAKOUT = "BREAKOUT"
    TREND_FOLLOWING = "TREND_FOLLOWING"
    MEAN_REVERSION_BANDS = "MEAN_REVERSION_BANDS"
    ML_ENHANCED = "ML_ENHANCED"
    ENSEMBLE = "ENSEMBLE"
