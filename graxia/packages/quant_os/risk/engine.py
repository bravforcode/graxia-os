"""
4-Layer Risk Engine — pre-trade validation gate.

Layer 1 (Per-Trade):   schema valid, signal age <5s, session open,
                        conviction >= 0.6, max risk 1% equity
Layer 2 (Portfolio):   total exposure <80%, per-class <30%, per-venue <50%,
                        correlation check, max 20 positions
Layer 3 (Account):     daily loss <2%, weekly loss <5%, drawdown <15%,
                        margin check
Layer 4 (Sizing):      volatility targeting, regime multiplier, Kelly cap 0.25

Signal -> APPROVE (with approved_quantity) or REJECT (with reason)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ── Thresholds ──────────────────────────────────────────────────────────────


class _Layer1:
    MAX_SIGNAL_AGE_S: float = 5.0
    MIN_CONVICTION: float = 0.6
    MAX_RISK_PCT_EQUITY: float = 0.01


class _Layer2:
    MAX_TOTAL_EXPOSURE_PCT: float = 0.80
    MAX_PER_CLASS_PCT: float = 0.30
    MAX_PER_VENUE_PCT: float = 0.50
    MAX_CORRELATION: float = 0.85
    MAX_POSITIONS: int = 20


class _Layer3:
    MAX_DAILY_LOSS_PCT: float = 0.02
    MAX_WEEKLY_LOSS_PCT: float = 0.05
    MAX_DRAWDOWN_PCT: float = 0.15
    MIN_MARGIN_LEVEL_PCT: float = 200.0


class _Layer4:
    KELLY_CAP: float = 0.25
    MIN_POSITION_USD: float = 10.0
    VOL_TARGET: float = 0.15


# ── Data models ─────────────────────────────────────────────────────────────


class RejectReason(str, Enum):
    STALE_SIGNAL = "STALE_SIGNAL"
    LOW_CONVICTION = "LOW_CONVICTION"
    HIGH_RISK = "HIGH_RISK"
    HIGH_CORRELATION = "HIGH_CORRELATION"
    MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    WEEKLY_LOSS_LIMIT = "WEEKLY_LOSS_LIMIT"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    MARGIN_INSUFFICIENT = "MARGIN_INSUFFICIENT"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    KILL_SWITCH = "KILL_SWITCH"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    SESSION_CLOSED = "SESSION_CLOSED"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    EXCEEDS_TOTAL_EXPOSURE = "EXCEEDS_TOTAL_EXPOSURE"
    EXCEEDS_CLASS_EXPOSURE = "EXCEEDS_CLASS_EXPOSURE"
    EXCEEDS_VENUE_EXPOSURE = "EXCEEDS_VENUE_EXPOSURE"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    SIZING_REJECTED = "SIZING_REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class Signal:
    symbol: str = ""
    conviction: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    direction: str = "BUY"
    side: str = "BUY"
    timestamp: datetime = field(default_factory=lambda: datetime.now())
    timestamp_epoch: float = 0.0
    asset_class: str = "metals"
    venue: str = "paper"
    strategy_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountState:
    equity: float = 100000.0
    balance: float = 100000.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    margin_level_pct: float = 999.0
    free_margin: float = 100000.0
    peak_equity: float = 100000.0
    current_drawdown_pct: float = 0.0
    open_positions: int = 0


@dataclass
class PortfolioState:
    total_exposure_pct: float = 0.0
    class_exposure_pct: dict[str, float] = field(default_factory=dict)
    venue_exposure_pct: dict[str, float] = field(default_factory=dict)
    position_symbols: list[str] = field(default_factory=list)
    correlation_matrix: dict[str, dict[str, float]] | None = None

    @property
    def open_positions_count(self) -> int:
        return len(self.position_symbols)


@dataclass(frozen=True)
class RiskVerdict:
    approved: bool
    approved_quantity: float
    reason: str = ""
    reason_code: RejectReason | None = None
    layer_failed: int | None = None
    sizing_details: dict[str, Any] = field(default_factory=dict)


# ── Protocols ───────────────────────────────────────────────────────────────


class SessionChecker(Protocol):
    def is_session_open(self, symbol: str) -> bool: ...


class CorrelationProvider(Protocol):
    def get_correlation(self, sym_a: str, sym_b: str) -> float: ...


class SchemaValidator(Protocol):
    def validate_signal(self, signal: Signal) -> bool: ...


# ── Kill Switch / Circuit Breaker protocols ──────────────────────────────────


class KillSwitchLike(Protocol):
    @property
    def is_triggered(self) -> bool: ...
    @property
    def trigger_type(self) -> str: ...


class CircuitBreakerLike(Protocol):
    @property
    def is_triggered(self) -> bool: ...
    @property
    def reason(self) -> str: ...


# ── Risk Engine ─────────────────────────────────────────────────────────────


class RiskEngine:
    def __init__(
        self,
        kill_switch: KillSwitchLike | None = None,
        circuit_breaker: CircuitBreakerLike | None = None,
        session_checker: SessionChecker | None = None,
        correlation_provider: CorrelationProvider | None = None,
        schema_validator: SchemaValidator | None = None,
        regime_multiplier_map: dict[str, float] | None = None,
    ):
        self._kill_switch = kill_switch
        self._circuit_breaker = circuit_breaker
        self._session_checker = session_checker
        self._correlation_provider = correlation_provider
        self._schema_validator = schema_validator
        self._regime_multiplier_map = regime_multiplier_map or {}

    def _pre_checks(self, signal: Signal) -> RiskVerdict | None:
        if self._kill_switch is not None and self._kill_switch.is_active():
            return self._reject(RejectReason.KILL_SWITCH_ACTIVE, "Kill switch active", layer=0)
        if self._circuit_breaker is not None and self._circuit_breaker.is_open(signal.asset_class):
            return self._reject(RejectReason.CIRCUIT_BREAKER_OPEN, f"Circuit breaker open for {signal.asset_class}", layer=0)
        if self._schema_validator is not None and not self._schema_validator.validate_signal(signal):
            return self._reject(RejectReason.INVALID_SCHEMA, "Schema validation failed", layer=0)
        return None

    def evaluate(
        self,
        signal: Signal,
        account: AccountState,
        portfolio: PortfolioState,
        realized_vol: float = 0.15,
        regime: Any = None,
    ) -> RiskVerdict:
        # Pre-checks: kill switch, circuit breaker, schema
        pre = self._pre_checks(signal)
        if pre:
            return pre

        # Layer 1
        layer1 = self._layer1(signal)
        if layer1:
            return layer1

        # Layer 2
        layer2 = self._layer2(signal, portfolio)
        if layer2:
            return layer2

        # Layer 3
        layer3 = self._layer3(account)
        if layer3:
            return layer3

        # Layer 4
        return self._layer4(signal, account, portfolio, realized_vol, regime)

    def _layer1(self, signal: Signal) -> RiskVerdict | None:
        if signal.timestamp_epoch > 0:
            age = time.time() - signal.timestamp_epoch
        else:
            now = datetime.now(timezone.utc) if signal.timestamp.tzinfo else datetime.now()
            age = (now - signal.timestamp).total_seconds()
        if age > _Layer1.MAX_SIGNAL_AGE_S:
            return self._reject(
                RejectReason.STALE_SIGNAL, f"Signal age {age:.1f}s > {_Layer1.MAX_SIGNAL_AGE_S}s", layer=1
            )
        if self._session_checker is not None and not self._session_checker.is_session_open(signal.symbol):
            return self._reject(RejectReason.SESSION_CLOSED, f"Session closed for {signal.symbol}", layer=1)
        if signal.conviction < _Layer1.MIN_CONVICTION:
            return self._reject(
                RejectReason.LOW_CONVICTION, f"Conviction {signal.conviction:.2f} < {_Layer1.MIN_CONVICTION}", layer=1
            )
        return None

    def _layer2(self, signal: Signal, portfolio: PortfolioState) -> RiskVerdict | None:
        if portfolio.total_exposure_pct > _Layer2.MAX_TOTAL_EXPOSURE_PCT:
            return self._reject(
                RejectReason.EXCEEDS_TOTAL_EXPOSURE,
                f"Exposure {portfolio.total_exposure_pct:.0%} > {_Layer2.MAX_TOTAL_EXPOSURE_PCT:.0%}",
                layer=2,
            )

        cls = signal.asset_class
        if cls in portfolio.class_exposure_pct and portfolio.class_exposure_pct[cls] > _Layer2.MAX_PER_CLASS_PCT:
            return self._reject(
                RejectReason.EXCEEDS_CLASS_EXPOSURE,
                f"Class {cls} exposure {portfolio.class_exposure_pct[cls]:.0%} > {_Layer2.MAX_PER_CLASS_PCT:.0%}",
                layer=2,
            )

        if self._correlation_provider is not None and portfolio.correlation_matrix is not None:
            for existing_sym in portfolio.position_symbols:
                corr = self._correlation_provider.get_correlation(signal.symbol, existing_sym)
                if abs(corr) > _Layer2.MAX_CORRELATION:
                    return self._reject(
                        RejectReason.HIGH_CORRELATION,
                        f"Correlation {corr:.2f} with {existing_sym} > {_Layer2.MAX_CORRELATION}",
                        layer=2,
                    )

        venue = signal.venue
        if venue in portfolio.venue_exposure_pct and portfolio.venue_exposure_pct[venue] > _Layer2.MAX_PER_VENUE_PCT:
            return self._reject(
                RejectReason.EXCEEDS_VENUE_EXPOSURE,
                f"Venue {venue} exposure {portfolio.venue_exposure_pct[venue]:.0%} > {_Layer2.MAX_PER_VENUE_PCT:.0%}",
                layer=2,
            )

        if len(portfolio.position_symbols) >= _Layer2.MAX_POSITIONS:
            return self._reject(
                RejectReason.MAX_POSITIONS_REACHED,
                f"Open positions {portfolio.open_positions_count} >= {_Layer2.MAX_POSITIONS}",
                layer=2,
            )
        return None

    def _layer3(self, account: AccountState) -> RiskVerdict | None:
        if account.equity > 0:
            daily_loss_pct = abs(account.daily_pnl) / account.equity if account.daily_pnl < 0 else 0.0
            if daily_loss_pct >= _Layer3.MAX_DAILY_LOSS_PCT:
                return self._reject(
                    RejectReason.DAILY_LOSS_LIMIT,
                    f"Daily loss {daily_loss_pct:.2%} >= {_Layer3.MAX_DAILY_LOSS_PCT:.0%}",
                    layer=3,
                )

            weekly_loss_pct = abs(account.weekly_pnl) / account.equity if account.weekly_pnl < 0 else 0.0
            if weekly_loss_pct >= _Layer3.MAX_WEEKLY_LOSS_PCT:
                return self._reject(
                    RejectReason.WEEKLY_LOSS_LIMIT,
                    f"Weekly loss {weekly_loss_pct:.2%} >= {_Layer3.MAX_WEEKLY_LOSS_PCT:.0%}",
                    layer=3,
                )

            if account.max_drawdown_pct >= _Layer3.MAX_DRAWDOWN_PCT:
                return self._reject(
                    RejectReason.MAX_DRAWDOWN,
                    f"Drawdown {account.max_drawdown_pct:.2%} >= {_Layer3.MAX_DRAWDOWN_PCT:.0%}",
                    layer=3,
                )

            if account.current_drawdown_pct >= _Layer3.MAX_DRAWDOWN_PCT:
                return self._reject(
                    RejectReason.DRAWDOWN_LIMIT,
                    f"Current drawdown {account.current_drawdown_pct:.2%} >= {_Layer3.MAX_DRAWDOWN_PCT:.0%}",
                    layer=3,
                )

        if account.margin_level_pct > 0 and account.margin_level_pct < _Layer3.MIN_MARGIN_LEVEL_PCT:
            return self._reject(
                RejectReason.INSUFFICIENT_MARGIN,
                f"Margin level {account.margin_level_pct:.0f}% < {_Layer3.MIN_MARGIN_LEVEL_PCT:.0f}%",
                layer=3,
            )
        return None

    def _layer4(
        self,
        signal: Signal,
        account: AccountState,
        portfolio: PortfolioState,
        realized_vol: float,
        regime: Any,
    ) -> RiskVerdict:
        vol_scalar = _Layer4.VOL_TARGET / max(realized_vol, 0.01)
        vol_scalar = max(vol_scalar, 0.1)
        vol_scalar = min(vol_scalar, 2.0)

        regime_mult = 1.0
        regime_name = ""
        if regime is not None:
            regime_name = getattr(regime, "value", str(regime))
            if "CRISIS" in regime_name.upper():
                regime_mult = 0.25
            elif "TREND" in regime_name.upper():
                regime_mult = 1.1

        kelly_fraction = signal.conviction * vol_scalar * regime_mult
        kelly_fraction = min(kelly_fraction, _Layer4.KELLY_CAP)

        risk_per_unit = abs(signal.entry_price - signal.stop_loss) if signal.stop_loss else 0
        if risk_per_unit <= 0:
            return self._reject(
                RejectReason.SIZING_REJECTED, "Zero or negative stop distance", layer=4
            )

        risk_budget = account.equity * _Layer1.MAX_RISK_PCT_EQUITY
        approved_qty = round(risk_budget / risk_per_unit, 2)

        approved_qty = max(approved_qty * kelly_fraction, 0)
        dollar_value = approved_qty * signal.entry_price if signal.entry_price else 0

        if dollar_value < _Layer4.MIN_POSITION_USD:
            return self._reject(
                RejectReason.HIGH_RISK, f"Position ${dollar_value:.2f} < ${_Layer4.MIN_POSITION_USD}", layer=4
            )

        return RiskVerdict(
            approved=True,
            approved_quantity=approved_qty,
            sizing_details={
                "vol_scalar": round(vol_scalar, 4),
                "regime_multiplier": regime_mult,
                "regime": regime_name,
                "kelly_fraction": round(kelly_fraction, 4),
                "risk_per_unit": round(risk_per_unit, 2),
                "dollar_value": round(dollar_value, 2),
            },
        )

    @staticmethod
    def _reject(reason: RejectReason, msg: str, layer: int) -> RiskVerdict:
        return RiskVerdict(approved=False, approved_quantity=0, reason=msg, reason_code=reason, layer_failed=layer)
