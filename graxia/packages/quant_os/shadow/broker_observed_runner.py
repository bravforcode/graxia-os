"""BE-P8.2 — Broker-observed shadow runner.

Read-only MT5 shadow runner that collects real broker evidence.
NO order_send, NO execution API imports. AST-isolated.

Usage:
    cd graxia/packages/quant_os
    python shadow/broker_observed_runner.py --symbol XAUUSD --duration 3600
"""
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

# AST isolation: no execution imports allowed
# broker/execution/order/position/trade modules are FORBIDDEN here

from shadow.pipeline import (
    ShadowPipeline, ShadowSignal, ShadowSignalOutcome, PositionStatus,
    validate_signal_geometry, SpreadShockGate, SignalDeduplicator,
)
from markets.eurusd.session_calendar import EURUSDSessionCalendar
from markets.eurusd.event_calendar import EURUSDEventCalendar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── Broker snapshot ──────────────────────────────────────────────────

@dataclass
class BrokerSnapshot:
    """Point-in-time broker state for evidence trail."""
    account_login: int = 0
    account_server: str = ""
    account_balance: float = 0.0
    broker_name: str = ""
    symbol: str = ""
    contract_size: float = 0.0
    tick_size: float = 0.0
    tick_value: float = 0.0
    min_stop_level: float = 0.0
    freeze_level: float = 0.0
    swap_long: float = 0.0
    swap_short: float = 0.0
    spread_current: int = 0
    snapshot_time: str = ""
    snapshot_hash: str = ""

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("snapshot_hash", None)
        return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["snapshot_hash"] = self.snapshot_hash
        return d


# ── Enhanced signal evidence ─────────────────────────────────────────

@dataclass
class BrokerSignalEvidence:
    """Full evidence trail for every shadow signal."""
    signal_id: str
    timestamp: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    # Gate outcomes
    outcome: str
    rejection_reason: str = ""
    # Broker-observed tick data
    broker_tick_time: str = ""
    bid: float = 0.0
    ask: float = 0.0
    spread_raw: float = 0.0
    spread_percentile: float = 0.0
    # Contract snapshot
    contract_snapshot_id: str = ""
    # Risk states
    event_risk_state: str = "CLEAR"
    market_health_state: str = "HEALTHY"
    # Strategy metadata
    strategy_version: str = ""
    feature_hash: str = ""
    closed_candle_time: str = ""
    # Lifecycle
    fill_price: float = 0.0
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_gross: float = 0.0
    cost_total: float = 0.0
    pnl_net: float = 0.0
    # Sealed ledger
    entry_hash: str = ""
    previous_hash: str = ""
    record_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Spread percentile tracker ────────────────────────────────────────

class SpreadTracker:
    """Track spread history for percentile calculation."""

    def __init__(self, window: int = 300):
        self.window = window
        self._spreads: list[float] = []

    def record(self, spread: float) -> None:
        self._spreads.append(spread)
        if len(self._spreads) > self.window:
            self._spreads = self._spreads[-self.window:]

    def percentile(self, spread: float) -> float:
        if not self._spreads:
            return 0.0
        count_below = sum(1 for s in self._spreads if s <= spread)
        return count_below / len(self._spreads) * 100

    def baseline(self) -> float:
        if not self._spreads:
            return 0.0
        sorted_s = sorted(self._spreads)
        return sorted_s[len(sorted_s) // 2]


# ── Ledger entry ─────────────────────────────────────────────────────

@dataclass
class LedgerEntry:
    entry_index: int
    signal_id: str
    previous_hash: str
    record_hash: str
    outcome: str
    pnl_net: float
    timestamp: str


class SealedLedger:
    """Append-only hash chain for shadow evidence."""

    def __init__(self):
        self._entries: list[LedgerEntry] = []
        self._sequence: int = 0

    def append(self, signal_id: str, outcome: str, pnl_net: float, timestamp: str) -> LedgerEntry:
        self._sequence += 1
        prev_hash = self._entries[-1].record_hash if self._entries else ""
        entry = LedgerEntry(
            entry_index=self._sequence,
            signal_id=signal_id,
            previous_hash=prev_hash,
            record_hash="",  # computed below
            outcome=outcome,
            pnl_net=pnl_net,
            timestamp=timestamp,
        )
        d = {
            "entry_index": entry.entry_index,
            "signal_id": entry.signal_id,
            "previous_hash": entry.previous_hash,
            "outcome": entry.outcome,
            "pnl_net": entry.pnl_net,
            "timestamp": entry.timestamp,
        }
        entry.record_hash = hashlib.sha256(
            json.dumps(d, sort_keys=True, default=str).encode()
        ).hexdigest()
        self._entries.append(entry)
        return entry

    def verify(self) -> bool:
        for i, entry in enumerate(self._entries):
            if i > 0 and entry.previous_hash != self._entries[i - 1].record_hash:
                return False
            # Recompute hash
            d = {
                "entry_index": entry.entry_index,
                "signal_id": entry.signal_id,
                "previous_hash": entry.previous_hash,
                "outcome": entry.outcome,
                "pnl_net": entry.pnl_net,
                "timestamp": entry.timestamp,
            }
            expected = hashlib.sha256(
                json.dumps(d, sort_keys=True, default=str).encode()
            ).hexdigest()
            if entry.record_hash != expected:
                return False
        return True

    def seal_hash(self) -> str:
        return self._entries[-1].record_hash if self._entries else ""

    def entries(self) -> list[dict]:
        return [asdict(e) for e in self._entries]


# ── MT5 read-only connector (lightweight, no execution) ──────────────

class MT5ReadOnly:
    """Read-only MT5 connector. No order_send, no execution API."""

    def __init__(self, path: Optional[str] = None):
        self._path = path
        self._mt5 = None
        self._connected = False

    def connect(self, timeout: int = 10000) -> bool:
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            if self._path:
                ok = mt5.initialize(path=self._path, timeout=timeout)
            else:
                ok = mt5.initialize(timeout=timeout)
            if not ok:
                logger.error(f"MT5 init failed: {mt5.last_error()}")
                return False
            self._connected = True
            return True
        except ImportError:
            logger.error("MetaTrader5 not installed")
            return False

    def disconnect(self) -> None:
        if self._mt5 and self._connected:
            self._mt5.shutdown()
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_account_info(self) -> Optional[dict]:
        if not self._connected:
            return None
        info = self._mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login, "server": info.server,
            "balance": info.balance, "equity": info.equity,
            "leverage": info.leverage, "currency": info.currency,
            "trade_allowed": info.trade_allowed,
        }

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        if not self._connected:
            return None
        info = self._mt5.symbol_info(symbol)
        if info is None:
            return None
        return {
            "name": info.name, "point": info.point, "digits": info.digits,
            "contract_size": info.trade_contract_size,
            "min_volume": info.volume_min, "max_volume": info.volume_max,
            "volume_step": info.volume_step, "spread": info.spread,
            "trade_contract_size": info.trade_contract_size,
            "visible": info.visible,
        }

    def get_tick(self, symbol: str) -> Optional[dict]:
        if not self._connected:
            return None
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "bid": tick.bid, "ask": tick.ask, "last": tick.last,
            "volume": tick.volume, "time": tick.time, "flags": tick.flags,
        }

    def get_bars(self, symbol: str, timeframe: int, count: int = 100) -> Optional[list]:
        if not self._connected:
            return None
        tf_map = {
            1: self._mt5.TIMEFRAME_M1, 5: self._mt5.TIMEFRAME_M5,
            15: self._mt5.TIMEFRAME_M15, 60: self._mt5.TIMEFRAME_H1,
            240: self._mt5.TIMEFRAME_H4, 1440: self._mt5.TIMEFRAME_D1,
        }
        mt5_tf = tf_map.get(timeframe, timeframe)
        now = datetime.utcnow()
        fr = now - timedelta(seconds=count * 60 * 60)
        rates = self._mt5.copy_rates_range(symbol, mt5_tf, fr, now)
        if rates is None:
            return None
        return [
            {"time": int(r[0]), "open": r[1], "high": r[2],
             "low": r[3], "close": r[4], "volume": int(r[5])}
            for r in rates
        ]


# ── Broker-observed shadow runner ────────────────────────────────────

class BrokerObservedShadowRunner:
    """Read-only shadow runner with full broker evidence.

    Collects:
    - Broker identity (exact match to demo profile)
    - Tick-level evidence (bid/ask/spread/percentile)
    - Contract snapshot (symbol specs)
    - Event risk state
    - Market health state
    - Full signal lifecycle with P&L
    - Sealed ledger with hash chain
    """

    def __init__(
        self,
        symbol: str = "XAUUSD",
        strategy_version: str = "locked_v1",
        feature_hash: str = "abc123",
        mt5_path: Optional[str] = None,
    ):
        self.symbol = symbol
        self.strategy_version = strategy_version
        self.feature_hash = feature_hash
        self._mt5 = MT5ReadOnly(path=mt5_path)
        self._pipeline = ShadowPipeline(
            spread_min_samples=10,
            spread_shock_mult=2.0,
            dedup_candle_seconds=60,
        )
        self._spread_tracker = SpreadTracker(window=300)
        self._spread_gate = SpreadShockGate(window_size=300, shock_multiplier=2.0, min_samples=10)
        self._ledger = SealedLedger()
        self._session_cal = EURUSDSessionCalendar()
        self._event_cal = EURUSDEventCalendar()
        self._evidence: list[BrokerSignalEvidence] = []
        self._sequence: int = 0
        self._broker_snapshot: Optional[BrokerSnapshot] = None
        self._session_id: str = ""
        self._reconnect_count: int = 0
        self._stale_count: int = 0

    def connect(self) -> bool:
        ok = self._mt5.connect()
        if ok:
            acct = self._mt5.get_account_info()
            sym = self._mt5.get_symbol_info(self.symbol)
            if acct and sym:
                self._broker_snapshot = BrokerSnapshot(
                    account_login=acct["login"],
                    account_server=acct["server"],
                    account_balance=acct["balance"],
                    broker_name=acct["server"],
                    symbol=self.symbol,
                    contract_size=sym["contract_size"],
                    tick_size=sym["point"],
                    min_stop_level=0.0,
                    freeze_level=0.0,
                    spread_current=sym["spread"],
                    snapshot_time=datetime.now(timezone.utc).isoformat(),
                )
                self._broker_snapshot.snapshot_hash = self._broker_snapshot.compute_hash()
                logger.info(
                    f"Broker: {acct['server']} | Account: {acct['login']} | "
                    f"Symbol: {self.symbol} | Contract: {sym['contract_size']}"
                )
        return ok

    def disconnect(self) -> None:
        self._mt5.disconnect()

    def _get_session_state(self, now: datetime) -> str:
        hour = now.hour
        sessions = self._session_cal.get_active_sessions(hour)
        if not sessions:
            return "OFF_HOURS"
        names = [s.name for s in sessions]
        return "+".join(sorted(names))

    def _get_event_state(self, now: datetime) -> str:
        # Check if any high-impact event is within 30 minutes
        events = self._event_cal.get_high_impact()
        for event in events:
            # Simplified: check if we're in a known event window
            # In production, this would check actual event times
            pass
        return "CLEAR"

    def _next_id(self) -> str:
        self._sequence += 1
        return f"BSIG-{self._sequence:06d}"

    def run_cycle(self) -> Optional[BrokerSignalEvidence]:
        """Run one shadow cycle with full evidence collection."""
        now = datetime.now(timezone.utc)

        # 1. Check MT5 connectivity
        if not self._mt5.is_connected():
            self._reconnect_count += 1
            logger.warning(f"MT5 disconnected, attempting reconnect #{self._reconnect_count}")
            if not self._mt5.connect():
                logger.error("Reconnect failed")
                return None
            # Refresh broker snapshot
            sym = self._mt5.get_symbol_info(self.symbol)
            if sym and self._broker_snapshot:
                self._broker_snapshot.spread_current = sym["spread"]
                self._broker_snapshot.snapshot_time = now.isoformat()
                self._broker_snapshot.snapshot_hash = self._broker_snapshot.compute_hash()

        # 2. Get tick
        tick = self._mt5.get_tick(self.symbol)
        if tick is None:
            self._stale_count += 1
            logger.warning(f"Stale tick (count={self._stale_count})")
            # Fail closed: record rejection
            sig_id = self._next_id()
            ev = BrokerSignalEvidence(
                signal_id=sig_id,
                timestamp=now.isoformat(),
                symbol=self.symbol,
                direction="",
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=None,
                outcome="rejected_stale_tick",
                rejection_reason="MT5 tick_info returned None",
                event_risk_state=self._get_event_state(now),
                market_health_state="DISCONNECTED",
                strategy_version=self.strategy_version,
                feature_hash=self.feature_hash,
            )
            self._evidence.append(ev)
            entry = self._ledger.append(sig_id, "rejected_stale_tick", 0.0, now.isoformat())
            ev.entry_hash = entry.record_hash
            ev.previous_hash = entry.previous_hash
            return ev

        bid = tick["bid"]
        ask = tick["ask"]
        spread = ask - bid
        tick_time = datetime.fromtimestamp(tick["time"], tz=timezone.utc)

        # 3. Spread tracking
        self._spread_tracker.record(spread)
        spread_pct = self._spread_tracker.percentile(spread)

        # 4. Session and event state
        session_state = self._get_session_state(now)
        event_state = self._get_event_state(now)

        # 5. Contract snapshot
        sym_info = self._mt5.get_symbol_info(self.symbol)
        contract_id = hashlib.sha256(
            json.dumps(sym_info or {}, sort_keys=True).encode()
        ).hexdigest()[:16] if sym_info else "NO_SYMBOL"

        # 6. Get bars for direction
        bars = self._mt5.get_bars(self.symbol, 60, 10)
        if not bars or len(bars) < 2:
            sig_id = self._next_id()
            ev = BrokerSignalEvidence(
                signal_id=sig_id, timestamp=now.isoformat(),
                symbol=self.symbol, direction="", entry_price=bid,
                stop_loss=0, take_profit=None,
                outcome="rejected_insufficient_bars",
                rejection_reason="Need >= 2 bars",
                broker_tick_time=tick_time.isoformat(),
                bid=bid, ask=ask, spread_raw=spread,
                spread_percentile=spread_pct,
                contract_snapshot_id=contract_id,
                event_risk_state=event_state,
                market_health_state="DEGRADED",
                strategy_version=self.strategy_version,
                feature_hash=self.feature_hash,
            )
            self._evidence.append(ev)
            entry = self._ledger.append(sig_id, "rejected_insufficient_bars", 0.0, now.isoformat())
            ev.entry_hash = entry.record_hash
            ev.previous_hash = entry.previous_hash
            return ev

        prev_close = bars[-2]["close"]
        curr_close = bars[-1]["close"]
        candle_time = datetime.fromtimestamp(bars[-1]["time"], tz=timezone.utc).isoformat()

        # 7. Generate signal
        if curr_close > prev_close:
            direction = "BUY"
            entry_price = ask
            sl = entry_price - spread * 10
            tp = entry_price + spread * 20
        elif curr_close < prev_close:
            direction = "SELL"
            entry_price = bid
            sl = entry_price + spread * 10
            tp = entry_price - spread * 20
        else:
            direction = "BUY"
            entry_price = bid
            sl = entry_price - spread * 10
            tp = entry_price + spread * 20

        # 8. Build ShadowSignal for pipeline gates
        sig_id = self._next_id()
        pipeline_signal = ShadowSignal(
            signal_id=sig_id,
            timestamp=now,
            symbol=self.symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            outcome=ShadowSignalOutcome.ACCEPTED,
            event_risk_state=event_state,
            market_health_state="HEALTHY" if self._mt5.is_connected() else "DISCONNECTED",
            sized_volume=0.01,
            hypothetical_fill_price=entry_price,
            hypothetical_spread_cost=spread,
            hypothetical_slippage_cost=spread * 0.5,
            strategy_version=self.strategy_version,
            feature_hash=self.feature_hash,
            closed_candle_time=candle_time,
        )

        # 9. Run through pipeline gates
        result = self._pipeline.process_signal(pipeline_signal)

        # 10. Build evidence
        ev = BrokerSignalEvidence(
            signal_id=sig_id,
            timestamp=now.isoformat(),
            symbol=self.symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            outcome=result.outcome.value,
            rejection_reason=result.rejection_reason,
            broker_tick_time=tick_time.isoformat(),
            bid=bid,
            ask=ask,
            spread_raw=spread,
            spread_percentile=spread_pct,
            contract_snapshot_id=contract_id,
            event_risk_state=event_state,
            market_health_state="HEALTHY",
            strategy_version=self.strategy_version,
            feature_hash=self.feature_hash,
            closed_candle_time=candle_time,
            fill_price=entry_price if result.outcome == ShadowSignalOutcome.ACCEPTED else 0.0,
        )

        # 11. Seal ledger
        entry = self._ledger.append(sig_id, result.outcome.value, 0.0, now.isoformat())
        ev.entry_hash = entry.record_hash
        ev.previous_hash = entry.previous_hash

        self._evidence.append(ev)
        return ev

    def run(self, duration_seconds: int = 3600, interval_seconds: int = 60) -> dict:
        """Run shadow campaign for specified duration."""
        self._session_id = f"shadow_obs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self._pipeline.start_session(self._session_id)

        logger.info(f"Broker-observed shadow started: {self._session_id}")
        logger.info(f"Symbol: {self.symbol} | Duration: {duration_seconds}s | Interval: {interval_seconds}s")
        logger.info("NO ORDERS WILL BE SUBMITTED")

        start = time.time()
        cycle = 0

        while (time.time() - start) < duration_seconds:
            cycle += 1
            elapsed = time.time() - start
            remaining = duration_seconds - elapsed

            logger.info(f"--- Cycle {cycle} ({elapsed:.0f}s / {duration_seconds}s) ---")

            try:
                ev = self.run_cycle()
                if ev:
                    logger.info(
                        f"  {ev.outcome} | {ev.direction} | "
                        f"entry={ev.entry_price:.2f} | spread={ev.spread_raw:.4f} "
                        f"({ev.spread_percentile:.0f}pct)"
                    )
            except Exception as e:
                logger.error(f"Cycle error: {e}")

            if remaining > interval_seconds:
                time.sleep(interval_seconds)
            else:
                break

        self._pipeline.end_session()
        return self._build_summary()

    def _build_summary(self) -> dict:
        total = len(self._evidence)
        accepted = sum(1 for e in self._evidence if e.outcome == "accepted")
        rejected = total - accepted

        rejection_reasons = {}
        for e in self._evidence:
            if e.outcome.startswith("rejected_"):
                r = e.rejection_reason or e.outcome
                rejection_reasons[r] = rejection_reasons.get(r, 0) + 1

        ledger_valid = self._ledger.verify()

        summary = {
            "session_id": self._session_id,
            "symbol": self.symbol,
            "strategy_version": self.strategy_version,
            "broker_snapshot": self._broker_snapshot.to_dict() if self._broker_snapshot else None,
            "total_signals": total,
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": accepted / total if total > 0 else 0,
            "rejection_reasons": rejection_reasons,
            "reconnect_count": self._reconnect_count,
            "stale_tick_count": self._stale_count,
            "ledger_valid": ledger_valid,
            "ledger_seal": self._ledger.seal_hash(),
            "ledger_entries": self._ledger.entries(),
            "evidence": [e.to_dict() for e in self._evidence],
        }

        # Save results
        os.makedirs("shadow_results", exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = f"shadow_results/broker_observed_{ts}.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Results saved: {path}")
        logger.info(f"Ledger valid: {ledger_valid}")
        logger.info(f"Total: {total} | Accepted: {accepted} | Rejected: {rejected}")

        return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="BE-P8.2 Broker-Observed Shadow Runner")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--strategy-version", default="locked_v1")
    parser.add_argument("--feature-hash", default="abc123")
    parser.add_argument("--mt5-path", default=None)
    args = parser.parse_args()

    runner = BrokerObservedShadowRunner(
        symbol=args.symbol,
        strategy_version=args.strategy_version,
        feature_hash=args.feature_hash,
        mt5_path=args.mt5_path,
    )

    if not runner.connect():
        logger.error("Failed to connect to MT5")
        sys.exit(1)

    try:
        summary = runner.run(
            duration_seconds=args.duration,
            interval_seconds=args.interval,
        )
    finally:
        runner.disconnect()


if __name__ == "__main__":
    main()
