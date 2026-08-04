"""Frozen dataclasses for Myfxbook account data.

All optional metrics default to None so a partially-parsed page never lies:
a missing value is "unknown", not zero.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """High-level stats block parsed from a Myfxbook account page."""

    account_id: int
    member: str
    system: str
    url: str
    name: str | None = None
    verified: bool | None = None  # None = unknown
    gain_pct: float | None = None
    abs_gain_pct: float | None = None
    daily_pct: float | None = None
    monthly_pct: float | None = None
    max_drawdown_pct: float | None = None
    balance: float | None = None
    currency: str | None = None
    profit_factor: float | None = None
    sharpe: float | None = None
    win_rate_pct: float | None = None
    total_trades: int | None = None
    tracked_months: int | None = None
    last_updated: str = ""  # ISO date of the fetch


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """One monthly equity sample. month is 'YYYY-MM'."""

    account_id: int
    month: str
    equity: float


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One closed trade from an account's trade history."""

    account_id: int
    trade_id: str
    open_time: str
    close_time: str
    symbol: str
    direction: str  # "long" | "short"
    lots: float
    entry: float
    exit: float
    pnl: float
