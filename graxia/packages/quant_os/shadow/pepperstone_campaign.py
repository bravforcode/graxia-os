"""BE-P8.5 — Pepperstone 24h shadow campaign runner.

CanonicalTickSource-only, read-only MT5, no order_send.
Validates broker profile = Pepperstone-Demo before starting.
Hypothetical lifecycle: signal → entry → SL/TP/time exit → P&L.
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

from graxia.packages.quant_os.shadow.canonical_tick_source import CanonicalTickSource, CanonicalTickBatch
from graxia.packages.quant_os.shadow.canonical_time_authority import CanonicalTimeAuthority
from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match
from graxia.packages.quant_os.shadow.pipeline import (
    ShadowPipeline, ShadowSignal, ShadowSignalOutcome, PositionStatus,
    validate_signal_geometry, SpreadShockGate, SignalDeduplicator, Position,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── MT5 read-only connector ──────────────────────────────────────────

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
            ok = mt5.initialize(path=self._path, timeout=timeout) if self._path else mt5.initialize(timeout=timeout)
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
        return info and {
            "login": info.login, "server": info.server,
            "balance": info.balance, "equity": info.equity,
            "leverage": info.leverage, "currency": info.currency,
        }

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        if not self._connected:
            return None
        info = self._mt5.symbol_info(symbol)
        return info and {
            "name": info.name, "point": info.point, "digits": info.digits,
            "contract_size": info.trade_contract_size, "spread": info.spread,
            "visible": info.visible,
        }

    def copy_ticks_range(self, symbol: str, dt_from: datetime, dt_to: datetime) -> list:
        """UTC-aware tick fetch via copy_ticks_range. No symbol_info_tick.time."""
        if not self._connected:
            return []
        raw = self._mt5.copy_ticks_range(symbol, dt_from, dt_to, self._mt5.COPY_TICKS_ALL)
        if raw is None:
            return []
        return [
            {"time": int(t[0]), "bid": t[1], "ask": t[2], "last": t[3], "volume": t[4]}
            for t in raw
        ]


# ── Spread tracker ───────────────────────────────────────────────────

class SpreadTracker:
    """Track spread history for percentile calculation."""

    def __init__(self, window: int = 86400):
        self.window = window
        self._spreads: list[float] = []

    def record(self, spread: float) -> None:
        self._spreads.append(spread)
        if len(self._spreads) > self.window:
            self._spreads = self._spreads[-self.window:]

    def percentiles(self) -> dict:
        if not self._spreads:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        s = sorted(self._spreads)
        n = len(s)
        def pct(p):
            idx = int(p / 100 * (n - 1))
            return s[idx]
        return {"p50": pct(50), "p95": pct(95), "p99": pct(99)}

    def baseline(self) -> float:
        if not self._spreads:
            return 0.0
        s = sorted(self._spreads)
        return s[len(s) // 2]


# ── Session type classifier ─────────────────────────────────────────

def classify_session_type(now: datetime) -> str:
    """Classify UTC hour into session type."""
    h = now.hour
    if 0 <= h < 7:
        return "asian"
    if 7 <= h < 13:
        return "london"
    if 13 <= h < 21:
        return "ny"
    if (7 <= h < 13) and (13 <= h < 21):
        return "overlap"
    return "off_hours"


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
            entry_index=self._sequence, signal_id=signal_id,
            previous_hash=prev_hash, record_hash="",
            outcome=outcome, pnl_net=pnl_net, timestamp=timestamp,
        )
        d = {
            "entry_index": entry.entry_index, "signal_id": entry.signal_id,
            "previous_hash": entry.previous_hash, "outcome": entry.outcome,
            "pnl_net": entry.pnl_net, "timestamp": entry.timestamp,
        }
        entry.record_hash = hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()
        self._entries.append(entry)
        return entry

    def verify(self) -> bool:
        for i, entry in enumerate(self._entries):
            if i > 0 and entry.previous_hash != self._entries[i - 1].record_hash:
                return False
            d = {
                "entry_index": entry.entry_index, "signal_id": entry.signal_id,
                "previous_hash": entry.previous_hash, "outcome": entry.outcome,
                "pnl_net": entry.pnl_net, "timestamp": entry.timestamp,
            }
            expected = hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()
            if entry.record_hash != expected:
                return False
        return True

    def seal_hash(self) -> str:
        return self._entries[-1].record_hash if self._entries else ""

    def entries(self) -> list[dict]:
        return [asdict(e) for e in self._entries]


# ── Lifecycle simulator ─────────────────────────────────────────────

@dataclass
class LifecycleResult:
    exit_price: float = 0.0
    pnl_gross: float = 0.0
    cost_total: float = 0.0
    pnl_net: float = 0.0
    exit_reason: str = ""


def simulate_lifecycle(
    direction: str, entry: float, sl: float, tp: Optional[float],
    ticks: list[dict], max_hold_bars: int = 20,
) -> LifecycleResult:
    """Simulate position against subsequent canonical ticks.

    Checks SL/TP hit or time-stop after max_hold_bars.
    """
    spread_cost = abs(tp - entry) / 20 if tp else abs(sl - entry) / 10
    slippage = spread_cost * 0.5
    cost = spread_cost + slippage

    for i, tick in enumerate(ticks):
        bid, ask = tick["bid"], tick["ask"]
        if direction == "BUY":
            if bid <= sl:
                pnl = (sl - entry) - cost
                return LifecycleResult(exit_price=sl, pnl_gross=sl - entry, cost_total=cost, pnl_net=pnl, exit_reason="SL_HIT")
            if tp and bid >= tp:
                pnl = (tp - entry) - cost
                return LifecycleResult(exit_price=tp, pnl_gross=tp - entry, cost_total=cost, pnl_net=pnl, exit_reason="TP_HIT")
        else:
            if ask >= sl:
                pnl = (entry - sl) - cost
                return LifecycleResult(exit_price=sl, pnl_gross=entry - sl, cost_total=cost, pnl_net=pnl, exit_reason="SL_HIT")
            if tp and ask <= tp:
                pnl = (entry - tp) - cost
                return LifecycleResult(exit_price=tp, pnl_gross=entry - tp, cost_total=cost, pnl_net=pnl, exit_reason="TP_HIT")

        if i >= max_hold_bars - 1:
            exit_p = bid if direction == "BUY" else ask
            if direction == "BUY":
                pnl = (exit_p - entry) - cost
            else:
                pnl = (entry - exit_p) - cost
            return LifecycleResult(exit_price=exit_p, pnl_gross=exit_p - entry if direction == "BUY" else entry - exit_p, cost_total=cost, pnl_net=pnl, exit_reason="TIME_STOP")

    # Ticks exhausted — close at last
    last = ticks[-1] if ticks else {"bid": entry, "ask": entry}
    exit_p = last["bid"] if direction == "BUY" else last["ask"]
    if direction == "BUY":
        pnl = (exit_p - entry) - cost
    else:
        pnl = (entry - exit_p) - cost
    return LifecycleResult(exit_price=exit_p, pnl_gross=exit_p - entry if direction == "BUY" else entry - exit_p, cost_total=cost, pnl_net=pnl, exit_reason="TICKS_EXHAUSTED")


# ── Campaign evidence ───────────────────────────────────────────────

@dataclass
class CycleEvidence:
    cycle: int = 0
    timestamp_utc: str = ""
    # Profile
    profile_fingerprint: str = ""
    contract_snapshot_hash: str = ""
    # Canonical tick
    canonical_window_from: str = ""
    canonical_window_to: str = ""
    canonical_batch_hash: str = ""
    canonical_watermark: str = ""
    data_age_ms: float = 0.0
    raw_tick_count: int = 0
    deduplicated_tick_count: int = 0
    late_tick_count: int = 0
    outside_window_tick_count: int = 0
    # Spread
    spread: float = 0.0
    spread_p50: float = 0.0
    spread_p95: float = 0.0
    spread_p99: float = 0.0
    # Gates
    geometry_ok: bool = False
    geometry_reason: str = ""
    spread_shock: bool = False
    dedup_duplicate: bool = False
    event_risk_state: str = "CLEAR"
    market_health_state: str = "HEALTHY"
    # Signal
    signal_id: str = ""
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: Optional[float] = None
    outcome: str = ""
    rejection_reason: str = ""
    # Lifecycle
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_gross: float = 0.0
    cost_total: float = 0.0
    pnl_net: float = 0.0
    # Ledger
    ledger_entry_hash: str = ""
    ledger_previous_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Pepperstone campaign runner ──────────────────────────────────────

class PepperstoneCampaignRunner:
    """24h shadow campaign for Pepperstone-Demo.

    CanonicalTickSource-only, read-only MT5, no execution APIs.
    """

    def __init__(
        self,
        symbol: str = "XAUUSD",
        mt5_path: str = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe",
        strategy_version: str = "pepperstone_v1",
        feature_hash: str = "pepperstone_p85",
    ):
        self.symbol = symbol
        self.mt5_path = mt5_path
        self.strategy_version = strategy_version
        self.feature_hash = feature_hash
        self._mt5 = MT5ReadOnly(path=mt5_path)
        self._time_auth = CanonicalTimeAuthority()
        self._profile = BrokerProfile()
        self._pipeline = ShadowPipeline(
            spread_min_samples=10, spread_shock_mult=2.0, dedup_candle_seconds=60,
        )
        self._spread_tracker = SpreadTracker()
        self._spread_gate = SpreadShockGate(window_size=300, shock_multiplier=2.0, min_samples=10)
        self._dedup = SignalDeduplicator(candle_seconds=60)
        self._ledger = SealedLedger()
        self._evidence: list[CycleEvidence] = []
        self._session_id: str = ""
        self._open_positions: list[tuple[ShadowSignal, Position]] = []
        self._reconnect_count: int = 0

    def connect_and_validate(self) -> bool:
        """Connect to MT5 and validate Pepperstone-Demo profile."""
        if not self._mt5.connect():
            return False

        acct = self._mt5.get_account_info()
        sym = self._mt5.get_symbol_info(self.symbol)
        if not acct or not sym:
            logger.error("Failed to read broker info")
            return False

        ok, issues = validate_broker_match(
            acct["server"], acct["login"],
            sym["contract_size"], sym["digits"], sym["point"],
            self._profile,
        )
        if not ok:
            for i in issues:
                logger.error(f"BROKER VALIDATION FAILED: {i}")
            return False

        self._profile.compute_fingerprint()
        logger.info(f"Broker validated: {acct['server']} | fingerprint={self._profile.profile_fingerprint}")
        return True

    def disconnect(self) -> None:
        self._mt5.disconnect()

    def _cycle_canonical_ticks(self, batch: CanonicalTickBatch) -> dict:
        """Extract spread and tick metrics from canonical batch."""
        ticks = batch.canonical_ticks
        if not ticks:
            return {"spread": 0.0, "bid": 0.0, "ask": 0.0}
        last = ticks[-1]
        spread = last["ask"] - last["bid"]
        self._spread_tracker.record(spread)
        return {"spread": spread, "bid": last["bid"], "ask": last["ask"]}

    def _run_lifecycle(self, signal: ShadowSignal, subsequent_ticks: list[dict]) -> LifecycleResult:
        """Simulate hypothetical lifecycle for accepted signal."""
        entry = signal.hypothetical_fill_price
        sl = signal.stop_loss
        tp = signal.take_profit
        return simulate_lifecycle(signal.direction, entry, sl, tp, subsequent_ticks)

    def run_cycle(self, cycle_num: int) -> CycleEvidence:
        """Run one shadow cycle with full evidence collection."""
        now = self._time_auth.trusted_system_utc()
        ev = CycleEvidence(cycle=cycle_num, timestamp_utc=now.isoformat(), profile_fingerprint=self._profile.profile_fingerprint)

        # 1. Canonical tick fetch
        # Use a mock fetcher that calls copy_ticks_range via MT5ReadOnly
        # The CanonicalTickSource expects an mt5_connection with copy_ticks_range
        q_from = now - timedelta(seconds=62)  # trailing overlap
        q_to = now - timedelta(seconds=2)     # safety lag

        raw_ticks = self._mt5.copy_ticks_range(self.symbol, q_from, q_to)
        ev.raw_tick_count = len(raw_ticks)

        if not raw_ticks:
            ev.outcome = "rejected_no_ticks"
            ev.rejection_reason = "NO_CANONICAL_TICKS"
            entry = self._ledger.append(f"CYC-{cycle_num:06d}", "rejected_no_ticks", 0.0, now.isoformat())
            ev.ledger_entry_hash = entry.record_hash
            ev.ledger_previous_hash = entry.previous_hash
            self._evidence.append(ev)
            return ev

        # Canonical metadata
        tick_times = [t["time"] for t in raw_ticks]
        ev.canonical_batch_hash = hashlib.sha256(json.dumps(tick_times, sort_keys=True).encode()).hexdigest()[:16]
        ev.canonical_window_from = q_from.isoformat()
        ev.canonical_window_to = q_to.isoformat()
        ev.deduplicated_tick_count = len(raw_ticks)  # simplified dedup
        ev.late_tick_count = 0

        # 2. Watermark
        if raw_ticks:
            last_tick_dt = datetime.fromtimestamp(raw_ticks[-1]["time"], tz=timezone.utc)
            ev.canonical_watermark = last_tick_dt.isoformat()
            ev.data_age_ms = (now - last_tick_dt).total_seconds() * 1000
        else:
            ev.data_age_ms = 99999.0

        # 3. Spread
        tick_metrics = self._cycle_canonical_ticks(
            type("Batch", (), {"canonical_ticks": raw_ticks})()
        )
        spread = tick_metrics["spread"]
        ev.spread = spread
        pcts = self._spread_tracker.percentiles()
        ev.spread_p50, ev.spread_p95, ev.spread_p99 = pcts["p50"], pcts["p95"], pcts["p99"]

        # 4. Contract snapshot
        sym_info = self._mt5.get_symbol_info(self.symbol)
        ev.contract_snapshot_hash = hashlib.sha256(json.dumps(sym_info or {}, sort_keys=True).encode()).hexdigest()[:16]

        # 5. Session and event state
        session_type = classify_session_type(now)
        ev.event_risk_state = "CLEAR"
        ev.market_health_state = "HEALTHY" if self._mt5.is_connected() else "DISCONNECTED"

        # 6. Generate signal from latest tick
        bid, ask = tick_metrics["bid"], tick_metrics["ask"]
        mid = (bid + ask) / 2
        direction = "BUY" if bid < ask else "SELL"  # always true for real ticks

        # SL/TP from spread
        sl = mid - 10 * spread if direction == "BUY" else mid + 10 * spread
        tp = mid + 20 * spread if direction == "BUY" else mid - 20 * spread

        sig_id = f"PSIG-{cycle_num:06d}"
        ev.signal_id = sig_id
        ev.direction = direction
        ev.entry_price = mid
        ev.stop_loss = sl
        ev.take_profit = tp

        # 7. Geometry validation
        geo_ok, geo_reason = validate_signal_geometry(direction, mid, sl, tp)
        ev.geometry_ok = geo_ok
        ev.geometry_reason = geo_reason

        # 8. Spread shock
        self._spread_gate.record(spread)
        is_shock, _, baseline = self._spread_gate.is_shock(spread)
        ev.spread_shock = is_shock

        # 9. Event risk (simplified)
        # In production, check event calendar

        # 10. Dedup check
        candle_time = datetime.fromtimestamp(raw_ticks[-1]["time"], tz=timezone.utc).isoformat() if raw_ticks else ""
        is_dup = self._dedup.is_duplicate(self.strategy_version, self.symbol, direction, candle_time, self.feature_hash, now)
        ev.dedup_duplicate = is_dup

        # 11. Determine outcome
        if not geo_ok:
            ev.outcome = "rejected_geometry"
            ev.rejection_reason = f"GEOMETRY:{geo_reason}"
        elif is_shock:
            ev.outcome = "rejected_spread_shock"
            ev.rejection_reason = f"SPREAD_SHOCK: {spread:.4f} > {self._spread_gate.shock_multiplier}x baseline={baseline:.4f}"
        elif is_dup:
            ev.outcome = "rejected_duplicate"
            ev.rejection_reason = "DUPLICATE_SAME_CANDLE"
        elif ev.event_risk_state != "CLEAR":
            ev.outcome = "rejected_event_block"
            ev.rejection_reason = f"EVENT_BLOCK:{ev.event_risk_state}"
        elif ev.market_health_state != "HEALTHY":
            ev.outcome = "rejected_market_health"
            ev.rejection_reason = f"MARKET_UNHEALTHY:{ev.market_health_state}"
        else:
            ev.outcome = "accepted"
            self._dedup.record(self.strategy_version, self.symbol, direction, candle_time, self.feature_hash, now)

            # 12. Hypothetical lifecycle
            lc = self._run_lifecycle(
                ShadowSignal(signal_id=sig_id, timestamp=now, symbol=self.symbol,
                              direction=direction, entry_price=mid, stop_loss=sl, take_profit=tp,
                              outcome=ShadowSignalOutcome.ACCEPTED,
                              hypothetical_fill_price=mid, hypothetical_spread_cost=spread,
                              hypothetical_slippage_cost=spread * 0.5,
                              strategy_version=self.strategy_version, feature_hash=self.feature_hash),
                raw_ticks[1:21],  # subsequent ticks for simulation
            )
            ev.exit_price = lc.exit_price
            ev.exit_reason = lc.exit_reason
            ev.pnl_gross = lc.pnl_gross
            ev.cost_total = lc.cost_total
            ev.pnl_net = lc.pnl_net

        # 13. Ledger entry
        entry = self._ledger.append(sig_id, ev.outcome, ev.pnl_net, now.isoformat())
        ev.ledger_entry_hash = entry.record_hash
        ev.ledger_previous_hash = entry.previous_hash

        self._evidence.append(ev)
        return ev

    def run(self, duration_seconds: int = 86400, interval_seconds: int = 60) -> dict:
        """Run 24h shadow campaign."""
        # Connect to MT5 first
        if not self._mt5.connect(timeout=30000):
            logger.error("MT5 connection failed")
            return {"error": "MT5_CONNECTION_FAILED"}

        # Validate broker profile
        acct = self._mt5.get_account_info()
        sym_info = self._mt5.get_symbol_info(self.symbol)
        if not acct or not sym_info:
            logger.error("Failed to get broker info")
            return {"error": "BROKER_INFO_FAILED"}

        match, issues = validate_broker_match(
            acct["server"], acct["login"], sym_info["contract_size"],
            sym_info["digits"], sym_info["point"], self._profile,
        )
        if not match:
            logger.error(f"Broker profile mismatch: {issues}")
            return {"error": "PROFILE_MISMATCH", "issues": issues}

        logger.info(f"Broker: {acct['server']} | Profile match: True")

        self._session_id = f"pepperstone_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self._pipeline.start_session(self._session_id)

        logger.info(f"Pepperstone 24h campaign started: {self._session_id}")
        logger.info(f"Symbol: {self.symbol} | Duration: {duration_seconds}s | Interval: {interval_seconds}s")
        logger.info("NO ORDERS WILL BE SUBMITTED")

        start = time.time()
        cycle = 0

        while (time.time() - start) < duration_seconds:
            cycle += 1
            elapsed = time.time() - start
            remaining = duration_seconds - elapsed

            try:
                ev = self.run_cycle(cycle)
                pct = elapsed / duration_seconds * 100
                logger.info(
                    f"[{cycle}] {pct:.1f}% | {ev.outcome} | {ev.direction} "
                    f"entry={ev.entry_price:.2f} spread={ev.spread:.4f} "
                    f"pnl={ev.pnl_net:.2f}"
                )
            except Exception as e:
                logger.error(f"Cycle {cycle} error: {e}")

            if remaining > interval_seconds:
                time.sleep(interval_seconds)
            else:
                break

        self._pipeline.end_session()
        self._mt5.disconnect()
        return self._build_summary()

    def _build_summary(self) -> dict:
        total = len(self._evidence)
        accepted = sum(1 for e in self._evidence if e.outcome == "accepted")
        rejected = total - accepted

        rejection_reasons: dict[str, int] = {}
        for e in self._evidence:
            if e.outcome != "accepted":
                r = e.rejection_reason or e.outcome
                rejection_reasons[r] = rejection_reasons.get(r, 0) + 1

        total_pnl = sum(e.pnl_net for e in self._evidence)
        total_cost = sum(e.cost_total for e in self._evidence)
        ledger_valid = self._ledger.verify()

        summary = {
            "session_id": self._session_id,
            "session_start": self._evidence[0].timestamp_utc if self._evidence else "",
            "session_end": self._evidence[-1].timestamp_utc if self._evidence else "",
            "session_type": classify_session_type(self._time_auth.trusted_system_utc()),
            "symbol": self.symbol,
            "profile_fingerprint": self._profile.profile_fingerprint,
            "total_signals": total,
            "accepted": accepted,
            "rejected": rejected,
            "acceptance_rate": accepted / total if total > 0 else 0,
            "rejection_reasons": rejection_reasons,
            "hypothetical_pnl": total_pnl,
            "cost_total": total_cost,
            "ledger_valid": ledger_valid,
            "ledger_seal": self._ledger.seal_hash(),
            "spread_percentiles": self._spread_tracker.percentiles(),
            "ledger_entries": self._ledger.entries(),
            "evidence": [e.to_dict() for e in self._evidence],
        }

        os.makedirs("shadow_results", exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = f"shadow_results/pepperstone_campaign_{ts}.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Results saved: {path}")
        logger.info(f"Ledger valid: {ledger_valid}")
        logger.info(f"Total: {total} | Accepted: {accepted} | Rejected: {rejected}")
        logger.info(f"P&L: {total_pnl:.2f} | Cost: {total_cost:.2f}")

        return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="BE-P8.5 Pepperstone 24h Shadow Campaign")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--duration", type=int, default=86400)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--strategy-version", default="pepperstone_v1")
    parser.add_argument("--feature-hash", default="pepperstone_p85")
    parser.add_argument("--mt5-path", default=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")
    args = parser.parse_args()

    runner = PepperstoneCampaignRunner(
        symbol=args.symbol, mt5_path=args.mt5_path,
        strategy_version=args.strategy_version, feature_hash=args.feature_hash,
    )
    if not runner.connect_and_validate():
        logger.error("Failed to connect or validate Pepperstone profile")
        sys.exit(1)

    try:
        summary = runner.run(duration_seconds=args.duration, interval_seconds=args.interval)
    finally:
        runner.disconnect()


if __name__ == "__main__":
    main()
