"""Thaifxbook data models.

Frozen dataclasses with the invariant "missing != zero": every field defaults
to None and stays None when the platform did not expose it (e.g. money fields
masked as ``***`` on accounts that opted out of public balance/profit).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SentimentSnapshot:
    """One asset row from /tools/outlook (aggregated public real accounts)."""

    ts: datetime
    asset: str  # normalized pair key, e.g. "XAUUSD"
    asset_display: str | None = None  # e.g. "XAU/USD"
    long_pct_by_trader: float | None = None
    short_pct_by_trader: float | None = None
    traders: int | None = None
    lots: float | None = None
    floating_pl_usd: float | None = None  # None when platform omits


@dataclass(frozen=True)
class ProfileSnapshot:
    """One public account profile page (/p/{uuid}) at collection time."""

    account_uuid: str
    ts: datetime
    rank: int | None = None
    trader: str | None = None
    account_name: str | None = None
    broker: str | None = None
    verified: bool | None = None
    currency: str | None = None
    leverage: str | None = None
    start_date: str | None = None
    last_sync: str | None = None
    # Money fields are None when masked (***) or not shown.
    balance_usd: float | None = None
    equity_usd: float | None = None
    deposits_usd: float | None = None
    withdrawals_usd: float | None = None
    profit_usd: float | None = None
    max_balance_usd: float | None = None
    gain_pct: float | None = None
    abs_gain_pct: float | None = None
    daily_pct: float | None = None
    monthly_pct: float | None = None
    max_drawdown_pct: float | None = None
    profit_factor: float | None = None
    expected_payoff: float | None = None
    sharpe: float | None = None
    win_rate_pct: float | None = None
    total_trades: int | None = None
    ea_pct: float | None = None
    manual_pct: float | None = None
    avg_hold_minutes: float | None = None
    ai_accuracy: float | None = None
    ai_profitability: float | None = None
    ai_risk: float | None = None
    ai_consistency: float | None = None
    ai_recovery: float | None = None
    masked: bool = False


@dataclass(frozen=True)
class TradeRecord:
    """One closed trade from a public profile's embedded RSC trade objects.

    The platform embeds full trade JSON (ticket, prices, pips, SL/TP, comment)
    in the page payload. There is no ``magic`` field — EA attribution is only
    available as the aggregate ea_pct on the profile (behavioral-level only).
    """

    account_uuid: str
    ts: datetime
    seq: int
    ticket: int
    symbol: str
    side: str  # buy / sell
    lots: float
    pnl_usd: float
    close_time: str
    open_time: str | None = None
    open_price: float | None = None
    close_price: float | None = None
    pips: float | None = None
    sl: float | None = None
    tp: float | None = None
    comment: str | None = None


@dataclass(frozen=True)
class LeaderboardEntry:
    """One leaderboard row (requires login; captured when session available)."""

    mode: str
    rank: int
    account_name: str
    trader: str | None = None
    dd_pct: float | None = None
    gain_pct: float | None = None
    followers: int | None = None
    ts: datetime = None  # type: ignore[assignment]


@dataclass(frozen=True)
class BrokerUsage:
    """One broker row from /brokers (real-account user count)."""

    broker: str
    real_users: int
    ts: datetime = None  # type: ignore[assignment]
