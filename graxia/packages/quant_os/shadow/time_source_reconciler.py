"""BE-P8.3.2 — MT5 Time Source Reconciliation.

Collects immutable per-cycle evidence from 3 MT5 APIs + system clock.
Applies temporal-consistency rules. Fails closed on inconsistency.

NO hardcode offsets. NO latency calculation. NO session/event decisions
from broker timestamps until provenance is resolved.
"""
import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional


# ── Temporal consistency rules ───────────────────────────────────────

MAX_TICK_DELAY_MS = 60000  # Rule A: tick time within ±60s of received_at
MAX_BAR_FUTURE_S = 0       # Rule C: bars must not be in the future


@dataclass
class TimeConsistencyResult:
    rule_a_tick_within_60s: bool = False
    rule_a_diff_ms: float = 0.0
    rule_b_ticks_in_window: bool = False
    rule_b_outside_count: int = 0
    rule_c_bars_not_future: bool = False
    rule_c_future_bars: int = 0
    all_passed: bool = False
    verdict: str = "PENDING"  # PASS, TIME_SOURCE_INCONSISTENT, PENDING

    def evaluate(self) -> str:
        self.all_passed = (
            self.rule_a_tick_within_60s
            and self.rule_b_ticks_in_window
            and self.rule_c_bars_not_future
        )
        if self.all_passed:
            self.verdict = "PASS"
        else:
            self.verdict = "TIME_SOURCE_INCONSISTENT"
        return self.verdict


def check_rule_a(tick_time_utc: Optional[datetime], received_at_utc: datetime) -> tuple[bool, float]:
    """Rule A: symbol_info_tick time within ±60s of received_at."""
    if tick_time_utc is None:
        return False, 0.0
    diff_ms = abs((received_at_utc - tick_time_utc).total_seconds() * 1000)
    return diff_ms <= MAX_TICK_DELAY_MS, diff_ms


def check_rule_b(ticks: list[dict], request_from: datetime, request_to: datetime) -> tuple[bool, int]:
    """Rule B: copy_ticks_range last tick within requested window."""
    if not ticks:
        return True, 0  # no ticks = no violation
    outside = 0
    for t in ticks:
        ts = t.get("time", 0)
        if ts <= 0:
            continue
        tick_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if tick_dt < request_from or tick_dt > request_to:
            outside += 1
    return outside == 0, outside


def check_rule_c(bars: list[dict], system_utc: datetime) -> tuple[bool, int]:
    """Rule C: M1/H1 bars must not be in the future relative to system UTC."""
    if not bars:
        return True, 0
    future_count = 0
    for b in bars:
        ts = b.get("time", 0)
        if ts <= 0:
            continue
        bar_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if bar_dt > system_utc + timedelta(seconds=MAX_BAR_FUTURE_S):
            future_count += 1
    return future_count == 0, future_count


# ── Per-cycle immutable evidence ─────────────────────────────────────

@dataclass
class CycleEvidence:
    """Immutable evidence collected per cycle. All fields must be set."""
    cycle_id: int
    # System clock
    system_epoch_ms: int = 0
    system_utc_iso: str = ""
    # symbol_info_tick()
    tick_raw_time: int = 0
    tick_raw_time_msc: int = 0
    tick_datetime_utc: str = ""
    tick_bid: float = 0.0
    tick_ask: float = 0.0
    tick_none: bool = False
    tick_mt5_error: str = ""
    # copy_ticks_range()
    request_from_utc: str = ""
    request_to_utc: str = ""
    request_window_hash: str = ""
    returned_tick_count: int = 0
    returned_first_epoch: int = 0
    returned_last_epoch: int = 0
    returned_first_utc: str = ""
    returned_last_utc: str = ""
    # copy_rates_from_pos() H1
    h1_bar_time: int = 0
    h1_bar_utc: str = ""
    h1_bar_close: float = 0.0
    # copy_rates_from_pos() M1
    m1_bar_time: int = 0
    m1_bar_utc: str = ""
    m1_bar_close: float = 0.0
    # Terminal/account
    terminal_build: int = 0
    terminal_connected: bool = False
    account_server: str = ""
    account_login: int = 0
    symbol_visible: bool = False
    symbol_trade_mode: str = ""
    mt5_last_error: str = ""
    # Consistency check
    received_at_utc: str = ""
    rule_a_passed: bool = False
    rule_a_diff_ms: float = 0.0
    rule_b_passed: bool = False
    rule_b_outside_count: int = 0
    rule_c_passed: bool = False
    rule_c_future_bars: int = 0
    consistency_verdict: str = "PENDING"
    # Ledger
    entry_hash: str = ""
    previous_hash: str = ""
    record_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Sealed ledger ────────────────────────────────────────────────────

class SealedLedger:
    def __init__(self):
        self._entries: list[dict] = []
        self._seq: int = 0

    def append(self, ev: CycleEvidence) -> str:
        self._seq += 1
        prev = self._entries[-1]["record_hash"] if self._entries else ""
        d = {
            "seq": self._seq,
            "cycle_id": ev.cycle_id,
            "previous_hash": prev,
            "system_epoch_ms": ev.system_epoch_ms,
            "tick_raw_time": ev.tick_raw_time,
            "consistency_verdict": ev.consistency_verdict,
            "tick_none": ev.tick_none,
        }
        h = hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()
        self._entries.append({**d, "record_hash": h})
        return h

    def verify(self) -> bool:
        for i, e in enumerate(self._entries):
            if i > 0 and e["previous_hash"] != self._entries[i-1]["record_hash"]:
                return False
            d = {k: v for k, v in e.items() if k != "record_hash"}
            expected = hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()
            if e["record_hash"] != expected:
                return False
        return True

    def seal(self) -> str:
        return self._entries[-1]["record_hash"] if self._entries else ""

    def entries(self) -> list[dict]:
        return list(self._entries)


# ── Time source reconciler ───────────────────────────────────────────

class TimeSourceReconciler:
    """Collects per-cycle evidence and applies temporal-consistency rules.

    Does NOT use broker timestamps for:
    - latency calculation
    - session classification (Asian/London/NY)
    - event-window gating
    - cost/slippage calibration
    """

    def __init__(self, mt5_connection, symbol: str = "XAUUSD"):
        self._mt5 = mt5_connection
        self._symbol = symbol
        self._ledger = SealedLedger()
        self._cycle: int = 0
        self._evidence: list[CycleEvidence] = []

    def collect_cycle(self) -> CycleEvidence:
        """Collect one cycle of immutable evidence."""
        self._cycle += 1
        received_at = datetime.now(timezone.utc)
        system_epoch_ms = int(time.time() * 1000)

        ev = CycleEvidence(
            cycle_id=self._cycle,
            system_epoch_ms=system_epoch_ms,
            system_utc_iso=received_at.isoformat(),
            received_at_utc=received_at.isoformat(),
        )

        # 1. symbol_info_tick()
        tick = self._mt5.get_tick(self._symbol)
        if tick is None:
            ev.tick_none = True
            diag = self._mt5.get_tick_diagnostics(self._symbol) if hasattr(self._mt5, 'get_tick_diagnostics') else {}
            ev.tick_mt5_error = diag.get("mt5_last_error", "no_diagnostics")
            ev.account_server = diag.get("account_server", "")
            ev.symbol_visible = diag.get("symbol_visible", False)
            ev.symbol_trade_mode = diag.get("symbol_trade_mode", "")
        else:
            ev.tick_raw_time = tick["time"]
            ev.tick_raw_time_msc = tick.get("time_msc", tick["time"] * 1000)
            ev.tick_datetime_utc = datetime.fromtimestamp(
                ev.tick_raw_time_msc / 1000, tz=timezone.utc
            ).isoformat()
            ev.tick_bid = tick["bid"]
            ev.tick_ask = tick["ask"]

        # 2. copy_ticks_range() — UTC-aware from/to
        request_from = received_at - timedelta(minutes=5)
        request_to = received_at
        ev.request_from_utc = request_from.isoformat()
        ev.request_to_utc = request_to.isoformat()
        # Hash the request window
        window_d = {"from": request_from.isoformat(), "to": request_to.isoformat()}
        ev.request_window_hash = hashlib.sha256(
            json.dumps(window_d, sort_keys=True).encode()
        ).hexdigest()[:16]

        try:
            ticks = self._mt5.copy_ticks_range(
                self._symbol, request_from, request_to,
                self._mt5._mt5.COPY_TICKS_ALL if hasattr(self._mt5, '_mt5') else 0
            )
            if ticks is not None and len(ticks) > 0:
                ev.returned_tick_count = len(ticks)
                ev.returned_first_epoch = int(ticks[0][0])
                ev.returned_last_epoch = int(ticks[-1][0])
                ev.returned_first_utc = datetime.fromtimestamp(
                    ev.returned_first_epoch, tz=timezone.utc
                ).isoformat()
                ev.returned_last_utc = datetime.fromtimestamp(
                    ev.returned_last_epoch, tz=timezone.utc
                ).isoformat()
        except Exception as e:
            ev.mt5_last_error = f"copy_ticks_range: {e}"

        # 3. copy_rates_from_pos() H1
        try:
            rates_h1 = self._mt5.get_bars(self._symbol, 60, 3) if hasattr(self._mt5, 'get_bars') else None
            if rates_h1 and len(rates_h1) > 0:
                last = rates_h1[-1]
                ev.h1_bar_time = last["time"]
                ev.h1_bar_utc = datetime.fromtimestamp(last["time"], tz=timezone.utc).isoformat()
                ev.h1_bar_close = last["close"]
        except Exception as e:
            ev.mt5_last_error = f"H1 rates: {e}"

        # 4. copy_rates_from_pos() M1
        try:
            rates_m1 = self._mt5.get_bars(self._symbol, 1, 3) if hasattr(self._mt5, 'get_bars') else None
            if rates_m1 and len(rates_m1) > 0:
                last = rates_m1[-1]
                ev.m1_bar_time = last["time"]
                ev.m1_bar_utc = datetime.fromtimestamp(last["time"], tz=timezone.utc).isoformat()
                ev.m1_bar_close = last["close"]
        except Exception as e:
            ev.mt5_last_error = f"M1 rates: {e}"

        # 5. Terminal/account info
        try:
            acct = self._mt5.get_account_info() if hasattr(self._mt5, 'get_account_info') else None
            if acct:
                ev.account_server = acct.get("server", "")
                ev.account_login = acct.get("login", 0)
        except Exception:
            pass

        # 6. Apply temporal-consistency rules
        tick_dt = None
        if not ev.tick_none and ev.tick_raw_time_msc > 0:
            tick_dt = datetime.fromtimestamp(ev.tick_raw_time_msc / 1000, tz=timezone.utc)

        ev.rule_a_passed, ev.rule_a_diff_ms = check_rule_a(tick_dt, received_at)

        tick_dicts = []
        if ev.returned_last_epoch > 0:
            tick_dicts = [{"time": ev.returned_first_epoch}, {"time": ev.returned_last_epoch}]
        ev.rule_b_passed, ev.rule_b_outside_count = check_rule_b(
            tick_dicts, request_from, request_to
        )

        bar_dicts = []
        if ev.h1_bar_time > 0:
            bar_dicts.append({"time": ev.h1_bar_time})
        if ev.m1_bar_time > 0:
            bar_dicts.append({"time": ev.m1_bar_time})
        ev.rule_c_passed, ev.rule_c_future_bars = check_rule_c(bar_dicts, received_at)

        # 7. Evaluate verdict
        result = TimeConsistencyResult(
            rule_a_tick_within_60s=ev.rule_a_passed,
            rule_a_diff_ms=ev.rule_a_diff_ms,
            rule_b_ticks_in_window=ev.rule_b_passed,
            rule_b_outside_count=ev.rule_b_outside_count,
            rule_c_bars_not_future=ev.rule_c_passed,
            rule_c_future_bars=ev.rule_c_future_bars,
        )
        ev.consistency_verdict = result.evaluate()

        # 8. Seal ledger
        ev.entry_hash = self._ledger.append(ev)

        self._evidence.append(ev)
        return ev

    def summary(self) -> dict:
        total = len(self._evidence)
        consistent = sum(1 for e in self._evidence if e.consistency_verdict == "PASS")
        inconsistent = sum(1 for e in self._evidence if e.consistency_verdict == "TIME_SOURCE_INCONSISTENT")
        tick_nones = sum(1 for e in self._evidence if e.tick_none)

        return {
            "total_cycles": total,
            "consistent": consistent,
            "inconsistent": inconsistent,
            "tick_none_count": tick_nones,
            "ledger_valid": self._ledger.verify(),
            "ledger_seal": self._ledger.seal(),
            "evidence": [e.to_dict() for e in self._evidence],
            "ledger_entries": self._ledger.entries(),
        }
