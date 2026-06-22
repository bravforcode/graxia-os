"""Shadow pipeline — real gates, real lifecycle, no order submission.

BE-P8.1: Geometry validation, spread shock, dedup, full position lifecycle.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import hashlib
import json


class ShadowSignalOutcome(Enum):
    ACCEPTED = "accepted"
    REJECTED_EVENT_BLOCK = "rejected_event_block"
    REJECTED_MARKET_HEALTH = "rejected_market_health"
    REJECTED_RISK = "rejected_risk"
    REJECTED_DATA_STALE = "rejected_data_stale"
    REJECTED_INVALID_SL = "rejected_invalid_sl"
    REJECTED_DUPLICATE = "rejected_duplicate"
    # BE-P8.1 new rejections
    REJECTED_GEOMETRY = "rejected_geometry"
    REJECTED_SPREAD_SHOCK = "rejected_spread_shock"


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED_SL = "closed_sl"
    CLOSED_TP = "closed_tp"
    CLOSED_TIME = "closed_time"
    CLOSED_MANUAL = "closed_manual"


@dataclass
class ShadowSignal:
    signal_id: str
    timestamp: datetime
    symbol: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    outcome: ShadowSignalOutcome
    rejection_reason: str = ""
    event_risk_state: str = "CLEAR"
    market_health_state: str = "HEALTHY"
    sized_volume: float = 0.0
    hypothetical_fill_price: float = 0.0
    hypothetical_spread_cost: float = 0.0
    hypothetical_slippage_cost: float = 0.0
    # BE-P8.1: geometry validation detail
    geometry_ok: bool = False
    spread_at_signal: float = 0.0

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "outcome": self.outcome.value,
            "rejection_reason": self.rejection_reason,
            "event_risk_state": self.event_risk_state,
            "market_health_state": self.market_health_state,
            "sized_volume": self.sized_volume,
            "hypothetical_fill_price": self.hypothetical_fill_price,
            "hypothetical_spread_cost": self.hypothetical_spread_cost,
            "hypothetical_slippage_cost": self.hypothetical_slippage_cost,
            "geometry_ok": self.geometry_ok,
            "spread_at_signal": self.spread_at_signal,
        }

    def fingerprint(self) -> str:
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Position:
    """Hypothetical position tracked through its full lifecycle."""
    position_id: str
    signal: ShadowSignal
    opened_at: datetime
    fill_price: float
    volume: float
    direction: str
    stop_loss: float
    take_profit: Optional[float]
    status: PositionStatus = PositionStatus.OPEN
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl_gross: float = 0.0
    cost_total: float = 0.0
    pnl_net: float = 0.0
    close_reason: str = ""

    def close(self, status: PositionStatus, exit_price: float,
              cost_total: float, timestamp: datetime, reason: str = "") -> None:
        self.status = status
        self.exit_price = exit_price
        self.closed_at = timestamp
        self.cost_total = cost_total
        if self.direction == "BUY":
            self.pnl_gross = (exit_price - self.fill_price) * self.volume
        else:
            self.pnl_gross = (self.fill_price - exit_price) * self.volume
        self.pnl_net = self.pnl_gross - cost_total
        self.close_reason = reason

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "signal_id": self.signal.signal_id,
            "direction": self.direction,
            "fill_price": self.fill_price,
            "volume": self.volume,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status.value,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "exit_price": self.exit_price,
            "pnl_gross": self.pnl_gross,
            "cost_total": self.cost_total,
            "pnl_net": self.pnl_net,
            "close_reason": self.close_reason,
        }


@dataclass
class ShadowSession:
    session_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    signals: list[ShadowSignal] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)

    def add_signal(self, signal: ShadowSignal) -> None:
        self.signals.append(signal)

    def summary(self) -> dict:
        total = len(self.signals)
        accepted = sum(1 for s in self.signals if s.outcome == ShadowSignalOutcome.ACCEPTED)
        rejected = total - accepted
        closed = [p for p in self.positions if p.status != PositionStatus.OPEN]
        total_pnl = sum(p.pnl_net for p in closed)
        return {
            "session_id": self.session_id,
            "total_signals": total,
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": accepted / total if total > 0 else 0,
            "positions_opened": len(self.positions),
            "positions_closed": len(closed),
            "total_pnl_net": total_pnl,
        }

    def export(self) -> str:
        return json.dumps({
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "signals": [s.to_dict() for s in self.signals],
            "positions": [p.to_dict() for p in self.positions],
        }, indent=2)


# ── Geometry validation ──────────────────────────────────────────────

def validate_signal_geometry(
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: Optional[float],
    min_stop_distance: float = 0.0,
) -> tuple[bool, str]:
    """Validate order geometry. Returns (ok, reason).

    Checks:
    1. SL = entry → reject
    2. TP = entry → reject
    3. SL wrong side (BUY: SL >= entry, SELL: SL <= entry) → reject
    4. TP wrong side (BUY: TP <= entry, SELL: TP >= entry) → reject
    5. Zero/negative stop distance → reject
    6. Broker minimum-stop violation → reject
    """
    if entry_price <= 0 or stop_loss <= 0:
        return False, "ZERO_PRICE"

    if direction == "BUY":
        if stop_loss >= entry_price:
            return False, f"SL_WRONG_SIDE: BUY SL={stop_loss} >= entry={entry_price}"
        if take_profit is not None and take_profit <= entry_price:
            return False, f"TP_WRONG_SIDE: BUY TP={take_profit} <= entry={entry_price}"
    elif direction == "SELL":
        if stop_loss <= entry_price:
            return False, f"SL_WRONG_SIDE: SELL SL={stop_loss} <= entry={entry_price}"
        if take_profit is not None and take_profit >= entry_price:
            return False, f"TP_WRONG_SIDE: SELL TP={take_profit} >= entry={entry_price}"
    else:
        return False, f"INVALID_DIRECTION: {direction}"

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return False, "ZERO_STOP_DISTANCE"
    if stop_distance < min_stop_distance:
        return False, f"BELOW_MIN_STOP: {stop_distance} < {min_stop_distance}"

    if take_profit is not None:
        tp_distance = abs(take_profit - entry_price)
        if tp_distance <= 0:
            return False, "ZERO_TP_DISTANCE"

    return True, "OK"


# ── Spread shock gate ────────────────────────────────────────────────

class SpreadShockGate:
    """Reject signals when spread exceeds rolling baseline threshold.

    ponytail: simple rolling window, O(n) scan. Upgrade to circular
    buffer if spread samples > 10k.
    """

    def __init__(
        self,
        window_size: int = 60,
        shock_multiplier: float = 2.0,
        min_samples: int = 10,
    ):
        self.window_size = window_size
        self.shock_multiplier = shock_multiplier
        self.min_samples = min_samples
        self._spreads: list[float] = []

    def record(self, spread: float) -> None:
        self._spreads.append(spread)
        if len(self._spreads) > self.window_size:
            self._spreads = self._spreads[-self.window_size:]

    def is_shock(self, spread: float) -> tuple[bool, float, float]:
        """Returns (is_shock, current_spread, baseline_p50)."""
        if len(self._spreads) < self.min_samples:
            return False, spread, 0.0
        sorted_s = sorted(self._spreads)
        p50 = sorted_s[len(sorted_s) // 2]
        threshold = p50 * self.shock_multiplier
        return spread > threshold, spread, p50

    def baseline(self) -> float:
        if not self._spreads:
            return 0.0
        sorted_s = sorted(self._spreads)
        return sorted_s[len(sorted_s) // 2]


# ── Deduplication ────────────────────────────────────────────────────

class SignalDeduplicator:
    """Reject duplicate signals: same direction + same candle window.

    ponytail: timestamp-based bucketing, not feature hashing.
    """

    def __init__(self, candle_seconds: int = 60):
        self.candle_seconds = candle_seconds
        self._last_signal_key: Optional[str] = None
        self._last_signal_time: Optional[datetime] = None

    def is_duplicate(
        self, symbol: str, direction: str, entry_price: float, timestamp: datetime
    ) -> bool:
        key = f"{symbol}:{direction}"
        if self._last_signal_key == key and self._last_signal_time is not None:
            elapsed = (timestamp - self._last_signal_time).total_seconds()
            if elapsed < self.candle_seconds:
                return True
        return False

    def record(self, symbol: str, direction: str, timestamp: datetime) -> None:
        self._last_signal_key = f"{symbol}:{direction}"
        self._last_signal_time = timestamp


# ── Main pipeline ────────────────────────────────────────────────────

class ShadowPipeline:
    """Shadow trading pipeline with real gates.

    BE-P8.1: geometry validation, spread shock, dedup, full lifecycle.
    No order submission, no execution function imports.
    """

    def __init__(
        self,
        min_stop_distance: float = 0.0,
        spread_window: int = 60,
        spread_shock_mult: float = 2.0,
        spread_min_samples: int = 10,
        dedup_candle_seconds: int = 60,
    ):
        self._sessions: dict[str, ShadowSession] = {}
        self._current_session: Optional[ShadowSession] = None
        self._sequence: int = 0
        # Gates
        self._geometry_min_stop = min_stop_distance
        self._spread_gate = SpreadShockGate(
            window_size=spread_window,
            shock_multiplier=spread_shock_mult,
            min_samples=spread_min_samples,
        )
        self._dedup = SignalDeduplicator(candle_seconds=dedup_candle_seconds)

    def start_session(self, session_id: str) -> ShadowSession:
        session = ShadowSession(
            session_id=session_id,
            started_at=datetime.utcnow(),
        )
        self._sessions[session_id] = session
        self._current_session = session
        self._sequence = 0
        return session

    def end_session(self) -> None:
        if self._current_session:
            self._current_session.ended_at = datetime.utcnow()
            self._current_session = None

    def _next_id(self) -> str:
        self._sequence += 1
        return f"SIG-{self._sequence:06d}"

    def process_signal(self, signal: ShadowSignal) -> ShadowSignal:
        """Process a signal through all gates. Never submits to broker.

        Gate order:
        1. Stale data
        2. Event risk
        3. Market health
        4. Invalid SL (legacy)
        5. Geometry validation (BE-P8.1)
        6. Spread shock (BE-P8.1)
        7. Deduplication (BE-P8.1)
        """
        if self._current_session is None:
            raise ValueError("No active session")

        # Gate 1: Stale data
        if signal.outcome == ShadowSignalOutcome.REJECTED_DATA_STALE:
            self._current_session.add_signal(signal)
            return signal

        # Gate 2: Event risk
        if signal.event_risk_state != "CLEAR":
            signal.outcome = ShadowSignalOutcome.REJECTED_EVENT_BLOCK
            signal.rejection_reason = f"EVENT_BLOCK:{signal.event_risk_state}"
            self._current_session.add_signal(signal)
            return signal

        # Gate 3: Market health
        if signal.market_health_state != "HEALTHY":
            signal.outcome = ShadowSignalOutcome.REJECTED_MARKET_HEALTH
            signal.rejection_reason = f"MARKET_UNHEALTHY:{signal.market_health_state}"
            self._current_session.add_signal(signal)
            return signal

        # Gate 4: Invalid SL (legacy check)
        if signal.stop_loss <= 0:
            signal.outcome = ShadowSignalOutcome.REJECTED_INVALID_SL
            signal.rejection_reason = "INVALID_SL"
            self._current_session.add_signal(signal)
            return signal

        # Gate 5: Geometry validation (BE-P8.1)
        geo_ok, geo_reason = validate_signal_geometry(
            signal.direction, signal.entry_price, signal.stop_loss,
            signal.take_profit, self._geometry_min_stop,
        )
        signal.geometry_ok = geo_ok
        if not geo_ok:
            signal.outcome = ShadowSignalOutcome.REJECTED_GEOMETRY
            signal.rejection_reason = f"GEOMETRY:{geo_reason}"
            self._current_session.add_signal(signal)
            return signal

        # Gate 6: Spread shock (BE-P8.1)
        spread = signal.hypothetical_spread_cost
        self._spread_gate.record(spread)
        is_shock, current_spread, baseline = self._spread_gate.is_shock(spread)
        signal.spread_at_signal = spread
        if is_shock:
            signal.outcome = ShadowSignalOutcome.REJECTED_SPREAD_SHOCK
            signal.rejection_reason = (
                f"SPREAD_SHOCK: spread={current_spread:.4f} > "
                f"{self._spread_gate.shock_multiplier}x baseline={baseline:.4f}"
            )
            self._current_session.add_signal(signal)
            return signal

        # Gate 7: Deduplication (BE-P8.1)
        if self._dedup.is_duplicate(
            signal.symbol, signal.direction, signal.entry_price, signal.timestamp
        ):
            signal.outcome = ShadowSignalOutcome.REJECTED_DUPLICATE
            signal.rejection_reason = "DUPLICATE_SAME_CANDLE"
            self._current_session.add_signal(signal)
            return signal

        # Accept
        signal.outcome = ShadowSignalOutcome.ACCEPTED
        self._dedup.record(signal.symbol, signal.direction, signal.timestamp)
        self._current_session.add_signal(signal)
        return signal

    def open_position(self, signal: ShadowSignal) -> Optional[Position]:
        """Open hypothetical position from accepted signal."""
        if self._current_session is None:
            raise ValueError("No active session")
        if signal.outcome != ShadowSignalOutcome.ACCEPTED:
            return None

        pos = Position(
            position_id=f"POS-{self._sequence:06d}",
            signal=signal,
            opened_at=signal.timestamp,
            fill_price=signal.hypothetical_fill_price,
            volume=signal.sized_volume,
            direction=signal.direction,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )
        self._current_session.positions.append(pos)
        return pos

    def check_position_exit(
        self, position: Position, current_bid: float, current_ask: float,
        timestamp: datetime, max_hold_bars: int = 0,
    ) -> bool:
        """Check if position should be closed. Returns True if closed."""
        if position.status != PositionStatus.OPEN:
            return False

        sl = position.stop_loss
        tp = position.take_profit

        if position.direction == "BUY":
            # Stop loss hit
            if current_bid <= sl:
                position.close(
                    PositionStatus.CLOSED_SL, sl,
                    position.signal.hypothetical_spread_cost + position.signal.hypothetical_slippage_cost,
                    timestamp, "SL_HIT"
                )
                return True
            # Take profit hit
            if tp is not None and current_bid >= tp:
                position.close(
                    PositionStatus.CLOSED_TP, tp,
                    position.signal.hypothetical_spread_cost + position.signal.hypothetical_slippage_cost,
                    timestamp, "TP_HIT"
                )
                return True
        else:  # SELL
            # Stop loss hit
            if current_ask >= sl:
                position.close(
                    PositionStatus.CLOSED_SL, sl,
                    position.signal.hypothetical_spread_cost + position.signal.hypothetical_slippage_cost,
                    timestamp, "SL_HIT"
                )
                return True
            # Take profit hit
            if tp is not None and current_ask <= tp:
                position.close(
                    PositionStatus.CLOSED_TP, tp,
                    position.signal.hypothetical_spread_cost + position.signal.hypothetical_slippage_cost,
                    timestamp, "TP_HIT"
                )
                return True

        # Time stop
        if max_hold_bars > 0 and position.opened_at is not None:
            elapsed = (timestamp - position.opened_at).total_seconds()
            if elapsed >= max_hold_bars * 60:  # approximate
                exit_price = current_bid if position.direction == "BUY" else current_ask
                position.close(
                    PositionStatus.CLOSED_TIME, exit_price,
                    position.signal.hypothetical_spread_cost + position.signal.hypothetical_slippage_cost,
                    timestamp, "TIME_STOP"
                )
                return True

        return False

    def get_session(self, session_id: str) -> Optional[ShadowSession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[ShadowSession]:
        return list(self._sessions.values())
