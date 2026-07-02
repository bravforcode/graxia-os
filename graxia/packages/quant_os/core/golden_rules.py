"""
GOLDEN RULES - NON-NEGOTIABLE SYSTEM CONSTRAINTS

These values are HARDCODED and cannot be overridden by config or environment.
Any change requires code review and explicit approval.

Rule #1: Live trading must be explicitly enabled
Rule #2: AI cannot directly submit live orders
Rule #3: Minimum 60 days paper trading required
Rule #4: Maximum 1% risk per trade
Rule #5: 15% hard stop drawdown
Rule #6: Micro stage orders expire in 60 seconds
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class GoldenRules:
    """Immutable golden rules - cannot be changed at runtime"""

    # Trading Mode Safety
    LIVE_TRADING_DEFAULT: bool = False  # Must explicitly set True
    PAPER_MIN_TRADING_DAYS: int = 60    # Non-negotiable minimum
    PAPER_MIN_TRADES: int = 100          # Non-negotiable minimum

    # AI Permission Boundaries
    AI_CANNOT_SUBMIT_ORDER: bool = True  # AI suggests only, never executes
    AI_CANNOT_OVERRIDE_KILL_SWITCH: bool = True
    AI_CANNOT_MODIFY_RISK_LIMITS: bool = True

    # Risk Limits (percentage-based)
    MAX_RISK_PER_TRADE_PCT: float = 1.0      # Max 1% equity risk per trade
    HARD_STOP_DRAWDOWN_PCT: float = 15.0     # Kill switch at 15% drawdown
    MAX_DAILY_LOSS_PCT: float = 2.0          # Daily circuit breaker
    MAX_WEEKLY_LOSS_PCT: float = 5.0         # Weekly circuit breaker
    MAX_PORTFOLIO_EXPOSURE_PCT: float = 80.0 # Max 80% in positions

    # Micro Stage Controls
    ORDER_EXPIRY_MICRO_SECONDS: int = 60   # Orders expire after 60s in MICRO mode
    MICRO_MAX_POSITION_SIZE_USD: float = 1000.0  # Max $1000 per position in MICRO
    MICRO_DAILY_ORDER_LIMIT: int = 5         # Max 5 orders per day in MICRO

    # Live Limited Controls
    LIMITED_MAX_POSITION_SIZE_USD: float = 5000.0  # Max $5000 per position
    LIMITED_MAX_DAILY_TRADES: int = 10       # Max 10 trades per day

    # Data Quality
    MAX_DATA_STALE_SECONDS: int = 10         # Quotes max 10s old
    MAX_OHLCV_STALE_SECONDS: int = 90        # OHLCV max 90s old
    MIN_LIQUIDITY_DAILY_VOLUME: float = 1000000.0  # Min $1M daily volume

    # Anti-Overfitting
    MIN_BACKTEST_YEARS: float = 3.0          # Minimum 3 years backtest data
    MIN_WALK_FORWARD_WINDOWS: int = 3        # Minimum 3 walk-forward windows
    MAX_PARAMETERS_PER_STRATEGY: int = 5     # Max 5 tunable parameters

    # Broker Safety
    MAX_ORDER_RETRIES: int = 3               # Max 3 retry attempts
    ORDER_TIMEOUT_SECONDS: int = 30          # Order timeout
    RECONCILIATION_INTERVAL_SECONDS: int = 60 # Reconcile every 60s

    # Compliance
    REQUIRE_STOP_LOSS: bool = True           # Every trade must have SL
    REQUIRE_RISK_CHECK: bool = True          # Every order needs risk approval
    REQUIRE_COMPLIANCE_CHECK: bool = True    # Every order needs compliance approval


# Singleton instance - use this everywhere
GOLDEN_RULES = GoldenRules()


def validate_golden_rules() -> Dict[str, Any]:
    """
    Validate that golden rules are properly loaded and haven't been tampered with.
    Called at system startup.
    """
    checks = {
        "live_trading_default_disabled": not GOLDEN_RULES.LIVE_TRADING_DEFAULT,
        "ai_cannot_submit_order": GOLDEN_RULES.AI_CANNOT_SUBMIT_ORDER,
        "min_paper_days_enforced": GOLDEN_RULES.PAPER_MIN_TRADING_DAYS >= 60,
        "min_paper_trades_enforced": GOLDEN_RULES.PAPER_MIN_TRADES >= 100,
        "max_risk_per_trade_sane": 0 < GOLDEN_RULES.MAX_RISK_PER_TRADE_PCT <= 2.0,
        "hard_stop_drawdown_sane": 5 < GOLDEN_RULES.HARD_STOP_DRAWDOWN_PCT <= 25.0,
        "order_expiry_micro_sane": 10 <= GOLDEN_RULES.ORDER_EXPIRY_MICRO_SECONDS <= 300,
        "all_checks_passed": True,
    }

    checks["all_checks_passed"] = all([
        checks["live_trading_default_disabled"],
        checks["ai_cannot_submit_order"],
        checks["min_paper_days_enforced"],
        checks["min_paper_trades_enforced"],
        checks["max_risk_per_trade_sane"],
        checks["hard_stop_drawdown_sane"],
        checks["order_expiry_micro_sane"],
    ])

    return checks


# Hard limits that can never be exceeded even by environment variables
HARD_LIMITS = {
    "max_risk_per_trade_pct": 2.0,      # Absolute max 2% per trade
    "max_drawdown_pct": 25.0,            # Absolute max 25% drawdown
    "max_daily_loss_pct": 5.0,           # Absolute max 5% daily loss
    "max_portfolio_exposure_pct": 95.0,  # Absolute max 95% exposure
    "min_order_expiry_seconds": 10,      # Minimum 10s order expiry
    "max_positions": 20,                 # Absolute max 20 positions
}
