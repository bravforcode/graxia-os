"""
Shadow Mode Runner v2 — collect live MT5 data, run full pipeline with integrity gates, submit NO orders.

Fixes from v1:
- Reject SL/TP invalid (equal, zero-distance, wrong-side)
- Enforce spread-shock rejection
- Record signal outcome (SL/TP/time-stop/cancelled)
- Compute hypothetical realized P&L after costs
- Record tick-level evidence per signal

Usage:
    cd quant_os
    python mt5_connector/shadow_runner.py [--symbol XAUUSD] [--bars 100] [--interval 60]
"""
import sys
import os
import time
import yaml
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mt5_connector.connection import MT5Connection
from mt5_connector.terminal_session_policy import load_terminal_session_config
from shadow.pipeline import ShadowPipeline, ShadowSignal, ShadowSignalOutcome
from shadow.failure_rules import FailureRuleChecker
from shadow.telemetry import ShadowTelemetry

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ─── Signal Geometry Validation ───

class SignalOutcome(Enum):
    ACCEPTED = "accepted"
    REJECTED_SL_EQUAL_ENTRY = "rejected_sl_equal_entry"
    REJECTED_SL_ZERO_DISTANCE = "rejected_sl_zero_distance"
    REJECTED_SL_WRONG_SIDE = "rejected_sl_wrong_side"
    REJECTED_TP_WRONG_SIDE = "rejected_tp_wrong_side"
    REJECTED_SPREAD_SHOCK = "rejected_spread_shock"
    REJECTED_INSUFFICIENT_BARS = "rejected_insufficient_bars"
    REJECTED_NO_DIRECTION = "rejected_no_direction"
    REJECTED_DATA_STALE = "rejected_data_stale"
    HIT_SL = "hit_sl"
    HIT_TP = "hit_tp"
    TIME_STOP = "time_stop"
    CANCELLED = "cancelled"

class RejectionReason(Enum):
    SL_EQUAL_ENTRY = "SL equals entry price"
    SL_ZERO_DISTANCE = "SL distance is zero"
    SL_WRONG_SIDE = "SL on wrong side of entry"
    TP_WRONG_SIDE = "TP on wrong side of entry"
    SPREAD_SHOCK = "Spread exceeds threshold"
    INSUFFICIENT_BARS = "Not enough bar data"
    NO_DIRECTION = "No clear direction"


@dataclass
class TickEvidence:
    timestamp: datetime
    bid: float
    ask: float
    spread: float
    last: float = 0.0


@dataclass
class SignalRecord:
    signal_id: str
    timestamp: datetime
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    outcome: SignalOutcome
    rejection_reason: str = ""
    tick_evidence: Optional[TickEvidence] = None
    hypothetical_pnl: float = 0.0
    hypothetical_costs: float = 0.0
    exit_price: float = 0.0
    exit_reason: str = ""
    bars_held: int = 0
    volume: float = 0.01
    
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
            "tick_evidence": {
                "bid": self.tick_evidence.bid,
                "ask": self.tick_evidence.ask,
                "spread": self.tick_evidence.spread,
                "timestamp": self.tick_evidence.timestamp.isoformat(),
            } if self.tick_evidence else None,
            "hypothetical_pnl": self.hypothetical_pnl,
            "hypothetical_costs": self.hypothetical_costs,
            "net_pnl": self.hypothetical_pnl - self.hypothetical_costs,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "bars_held": self.bars_held,
            "volume": self.volume,
        }


def validate_signal_geometry(
    direction: str, entry: float, sl: float, tp: Optional[float],
    spread: float,
    max_spread: float = 0.25,
) -> tuple[SignalOutcome, str]:
    """Validate signal geometry. Returns (outcome, rejection_reason)."""
    
    # Spread shock check
    if spread > max_spread:
        return SignalOutcome.REJECTED_SPREAD_SHOCK, RejectionReason.SPREAD_SHOCK.value
    
    # SL distance check
    sl_distance = abs(sl - entry)
    if sl_distance < 0.01:
        return SignalOutcome.REJECTED_SL_ZERO_DISTANCE, RejectionReason.SL_ZERO_DISTANCE.value
    
    # SL equals entry
    if abs(sl - entry) < 0.001:
        return SignalOutcome.REJECTED_SL_EQUAL_ENTRY, RejectionReason.SL_EQUAL_ENTRY.value
    
    # SL wrong side
    if direction == "BUY" and sl >= entry:
        return SignalOutcome.REJECTED_SL_WRONG_SIDE, RejectionReason.SL_WRONG_SIDE.value
    if direction == "SELL" and sl <= entry:
        return SignalOutcome.REJECTED_SL_WRONG_SIDE, RejectionReason.SL_WRONG_SIDE.value
    
    # TP wrong side
    if tp is not None:
        if direction == "BUY" and tp <= entry:
            return SignalOutcome.REJECTED_TP_WRONG_SIDE, RejectionReason.TP_WRONG_SIDE.value
        if direction == "SELL" and tp >= entry:
            return SignalOutcome.REJECTED_TP_WRONG_SIDE, RejectionReason.TP_WRONG_SIDE.value
    
    return SignalOutcome.ACCEPTED, ""


def simulate_outcome(
    direction: str, entry: float, sl: float, tp: Optional[float],
    future_bars: list, max_bars: int = 20,
) -> tuple[SignalOutcome, float, float, int, str]:
    """Simulate SL/TP/time-stop outcome. Returns (outcome, exit_price, pnl, bars_held, reason)."""
    if not future_bars:
        return SignalOutcome.TIME_STOP, entry, 0.0, 0, "NO_DATA"
    
    for i, bar in enumerate(future_bars[:max_bars]):
        high = bar['high']
        low = bar['low']
        
        if direction == "BUY":
            if low <= sl:
                return SignalOutcome.HIT_SL, sl, (sl - entry), i + 1, "SL"
            if tp and high >= tp:
                return SignalOutcome.HIT_TP, tp, (tp - entry), i + 1, "TP"
        elif direction == "SELL":
            if high >= sl:
                return SignalOutcome.HIT_SL, sl, (entry - sl), i + 1, "SL"
            if tp and low <= tp:
                return SignalOutcome.HIT_TP, tp, (entry - tp), i + 1, "TP"
    
    # Time stop
    last_price = future_bars[min(max_bars - 1, len(future_bars) - 1)]['close']
    if direction == "BUY":
        pnl = last_price - entry
    else:
        pnl = entry - last_price
    return SignalOutcome.TIME_STOP, last_price, pnl, min(max_bars, len(future_bars)), "TIME_STOP"


class ShadowRunnerV2:
    """Collect live MT5 data with integrity gates, never submit orders."""

    def __init__(self, config_path: str = 'mt5_connector/config.yaml'):
        self._config = load_terminal_session_config(config_path)

        self._mt5 = MT5Connection()
        self._pipeline = ShadowPipeline()
        self._failure_checker = FailureRuleChecker()
        self._telemetry = ShadowTelemetry()

        self._running = False
        self._signal_count = 0
        self._session_id = f"shadow_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self._records: list[SignalRecord] = []
        self._max_spread = 0.25

    def connect(self) -> bool:
        cfg = self._config['mt5']
        ok = self._mt5.connect(path=cfg.get('path'), timeout=cfg.get('timeout', 10000))
        if ok:
            info = self._mt5.get_account_info()
            logger.info(f"Connected: terminal-session-authenticated Balance={info.balance}")
        else:
            logger.error("MT5 connection failed")
        return ok

    def disconnect(self):
        self._mt5.disconnect()
        logger.info("Disconnected")

    def _collect_tick(self, symbol: str) -> Optional[TickEvidence]:
        tick = self._mt5.get_tick(symbol)
        if tick is None:
            return None
        return TickEvidence(
            timestamp=datetime.now(timezone.utc),
            bid=tick['bid'],
            ask=tick['ask'],
            spread=tick['ask'] - tick['bid'],
        )

    def _evaluate_signal(self, symbol: str, tick: TickEvidence, bars: list) -> tuple[SignalRecord, SignalOutcome, str]:
        self._signal_count += 1
        signal_id = f"SIG-{self._signal_count:06d}"
        
        # Bars check
        if len(bars) < 2:
            return SignalRecord(
                signal_id=signal_id, timestamp=datetime.now(timezone.utc),
                symbol=symbol, direction="BUY", entry_price=tick.ask,
                stop_loss=0, take_profit=None,
                outcome=SignalOutcome.REJECTED_INSUFFICIENT_BARS,
                rejection_reason=RejectionReason.INSUFFICIENT_BARS.value,
                tick_evidence=tick,
            ), SignalOutcome.REJECTED_INSUFFICIENT_BARS, RejectionReason.INSUFFICIENT_BARS.value

        # Direction
        prev_close = bars[-2]['close']
        curr_close = bars[-1]['close']
        
        if curr_close > prev_close:
            direction = "BUY"
            entry = tick.ask
            sl = entry - tick.spread * 10
            tp = entry + tick.spread * 20
        elif curr_close < prev_close:
            direction = "SELL"
            entry = tick.bid
            sl = entry + tick.spread * 10
            tp = entry - tick.spread * 20
        else:
            return SignalRecord(
                signal_id=signal_id, timestamp=datetime.now(timezone.utc),
                symbol=symbol, direction="BUY", entry_price=tick.ask,
                stop_loss=0, take_profit=None,
                outcome=SignalOutcome.REJECTED_NO_DIRECTION,
                rejection_reason=RejectionReason.NO_DIRECTION.value,
                tick_evidence=tick,
            ), SignalOutcome.REJECTED_NO_DIRECTION, RejectionReason.NO_DIRECTION.value

        # Validate geometry
        outcome, reason = validate_signal_geometry(direction, entry, sl, tp, tick.spread, self._max_spread)
        
        record = SignalRecord(
            signal_id=signal_id, timestamp=datetime.now(timezone.utc),
            symbol=symbol, direction=direction,
            entry_price=entry, stop_loss=sl, take_profit=tp,
            outcome=outcome, rejection_reason=reason,
            tick_evidence=tick, volume=0.01,
        )
        
        return record, outcome, reason

    def _simulate_outcome(self, record: SignalRecord, future_bars: list) -> SignalRecord:
        """Simulate outcome for accepted signals."""
        if record.outcome != SignalOutcome.ACCEPTED:
            return record
        
        outcome, exit_price, pnl, bars_held, reason = simulate_outcome(
            record.direction, record.entry_price, record.stop_loss, record.take_profit,
            future_bars,
        )
        
        spread_cost = record.tick_evidence.spread if record.tick_evidence else 0
        slippage_cost = spread_cost * 0.5
        total_costs = spread_cost + slippage_cost
        
        record.outcome = outcome
        record.exit_price = exit_price
        record.hypothetical_pnl = pnl
        record.hypothetical_costs = total_costs
        record.exit_reason = reason
        record.bars_held = bars_held
        
        return record

    def run_cycle(self, symbol: str, bar_count: int = 100) -> dict:
        tick = self._collect_tick(symbol)
        if tick is None:
            return {"error": "NO_TICK"}

        bars = self._mt5.get_bars(symbol, 60, bar_count)
        
        record, outcome, reason = self._evaluate_signal(symbol, tick, bars)

        # Simulate outcome for accepted signals
        if outcome == SignalOutcome.ACCEPTED and bars and len(bars) > 2:
            future_bars = bars[2:]  # Bars after signal generation
            record = self._simulate_outcome(record, future_bars)
            outcome = record.outcome

        self._records.append(record)
        
        # Telemetry
        self._telemetry.record_signal_created(self._session_id, record.signal_id)
        if record.outcome == SignalOutcome.ACCEPTED:
            self._telemetry.record_signal_accepted(self._session_id, record.signal_id)
        else:
            self._telemetry.record_signal_rejected(
                self._session_id, record.signal_id, record.rejection_reason
            )

        return record.to_dict()

    def run(self, symbol: str = 'XAUUSD', duration_seconds: int = 300, interval_seconds: int = 60):
        if not self.connect():
            return

        self._running = True
        self._telemetry.start(self._session_id)
        self._pipeline.start_session(self._session_id)

        logger.info(f"Shadow v2 started: {self._session_id}")
        logger.info(f"Symbol: {symbol}, Duration: {duration_seconds}s, Interval: {interval_seconds}s")
        logger.info(f"Max spread: {self._max_spread}")
        logger.info("NO ORDERS WILL BE SUBMITTED")

        start = time.time()
        cycle = 0

        while self._running and (time.time() - start) < duration_seconds:
            cycle += 1
            elapsed = time.time() - start
            remaining = duration_seconds - elapsed

            logger.info(f"--- Cycle {cycle} ({elapsed:.0f}s / {duration_seconds}s) ---")

            try:
                result = self.run_cycle(symbol)
                outcome = result.get('outcome', 'ERROR')
                direction = result.get('direction', '-')
                entry = result.get('entry_price', result.get('entry', '-'))
                spread = result.get('tick_evidence', {}).get('spread', '-') if result.get('tick_evidence') else '-'
                logger.info(f"  {outcome} | {direction} | entry={entry} | spread={spread}")
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                self._telemetry.record_pipeline_error(self._session_id, str(e))

            if remaining > interval_seconds:
                time.sleep(interval_seconds)
            else:
                break

        self._pipeline.end_session()
        self._running = False

        self._print_summary()
        self._export_results()
        self.disconnect()

    def _print_summary(self):
        total = len(self._records)
        
        # Rejected by geometry validator (never passed to simulation)
        rejected = sum(1 for r in self._records 
                      if r.outcome.value.startswith("rejected_"))
        
        # Accepted then simulated
        hit_sl = sum(1 for r in self._records if r.outcome == SignalOutcome.HIT_SL)
        hit_tp = sum(1 for r in self._records if r.outcome == SignalOutcome.HIT_TP)
        time_stop = sum(1 for r in self._records if r.outcome == SignalOutcome.TIME_STOP)
        accepted_simulated = hit_sl + hit_tp + time_stop
        
        total_pnl = sum(r.hypothetical_pnl * r.volume * 100 for r in self._records)
        total_costs = sum(r.hypothetical_costs * r.volume * 100 for r in self._records)
        net_pnl = total_pnl - total_costs
        
        rejected_by_reason = {}
        for r in self._records:
            if r.outcome.value.startswith("rejected_"):
                reason = r.rejection_reason or "unknown"
                rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1

        logger.info(f"\n{'='*50}")
        logger.info(f"SHADOW SESSION v2 SUMMARY")
        logger.info(f"{'='*50}")
        logger.info(f"Total signals:    {total}")
        logger.info(f"Rejected:         {rejected}")
        logger.info(f"Accepted+Sim:     {accepted_simulated}")
        logger.info(f"  SL hit:         {hit_sl}")
        logger.info(f"  TP hit:         {hit_tp}")
        logger.info(f"  Time stop:      {time_stop}")
        logger.info(f"{'='*50}")
        logger.info(f"Hypothetical P&L: {total_pnl:.2f}")
        logger.info(f"Hypothetical cost:{total_costs:.2f}")
        logger.info(f"Net P&L:          {net_pnl:.2f}")
        logger.info(f"{'='*50}")
        if rejected_by_reason:
            logger.info("Rejection reasons:")
            for reason, count in sorted(rejected_by_reason.items(), key=lambda x: -x[1]):
                logger.info(f"  {reason}: {count}")
        logger.info(f"{'='*50}")

    def _export_results(self):
        os.makedirs('shadow_results', exist_ok=True)
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

        # Telemetry
        telemetry_path = f'shadow_results/telemetry_{ts}.json'
        with open(telemetry_path, 'w') as f:
            f.write(self._telemetry.export_json(self._session_id))
        logger.info(f"Telemetry saved: {telemetry_path}")

        # Session
        session = self._pipeline.get_session(self._session_id)
        if session:
            session_path = f'shadow_results/session_{ts}.json'
            with open(session_path, 'w') as f:
                f.write(session.export())
            logger.info(f"Session saved: {session_path}")

        # Signal records (new in v2)
        records_path = f'shadow_results/records_{ts}.json'
        with open(records_path, 'w') as f:
            records = [r.to_dict() for r in self._records]
            json.dump({
                "session_id": self._session_id,
                "total_signals": len(self._records),
                "accepted": sum(1 for r in self._records if r.outcome == SignalOutcome.ACCEPTED),
                "rejected": sum(1 for r in self._records if r.outcome != SignalOutcome.ACCEPTED),
                "records": records,
            }, f, indent=2)
        logger.info(f"Records saved: {records_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Shadow Mode Runner v2')
    parser.add_argument('--symbol', default='XAUUSD', help='Symbol to trade')
    parser.add_argument('--bars', type=int, default=100, help='Bar count for analysis')
    parser.add_argument('--interval', type=int, default=60, help='Seconds between cycles')
    parser.add_argument('--duration', type=int, default=300, help='Total duration in seconds')
    parser.add_argument('--max-spread', type=float, default=0.25, help='Max allowed spread')
    args = parser.parse_args()

    runner = ShadowRunnerV2()
    runner._max_spread = args.max_spread
    runner.run(
        symbol=args.symbol,
        duration_seconds=args.duration,
        interval_seconds=args.interval,
    )


if __name__ == '__main__':
    main()
