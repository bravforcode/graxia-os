"""
Smoke Report for Quant OS

Generates a diagnostic report of all market data subsystems.
Read-only: no order submission, no account mutations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SmokeReportEntry:
    """Single entry in the smoke report."""

    component: str
    status: str  # "OK" | "DEGRADED" | "FAILED"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SmokeReport:
    """Complete smoke test report."""

    report_id: str
    symbol: str
    generated_at_utc: datetime
    entries: list[SmokeReportEntry]
    overall_status: str  # "PASS" | "FAIL"

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "symbol": self.symbol,
            "generated_at_utc": self.generated_at_utc.isoformat(),
            "overall_status": self.overall_status,
            "entries": [
                {
                    "component": e.component,
                    "status": e.status,
                    "message": e.message,
                    "details": e.details,
                }
                for e in self.entries
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def compute_hash(self) -> str:
        """SHA-256 hash of the serialized report for integrity checking."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SmokeReportGenerator:
    """
    Generates smoke reports for market data subsystems.

    Evaluates each component and produces a structured report.
    No MT5 dependency: works with injected state objects.
    """

    def __init__(self, symbol: str):
        self._symbol = symbol

    def generate(
        self,
        feed_health_state: Any = None,
        spread_state: Any = None,
        clock_state: Any = None,
        session_result: Any = None,
        tick_recorder_state: Any = None,
        watermark_state: Any = None,
        account_snapshot: Any = None,
    ) -> SmokeReport:
        """
        Generate a smoke report from component states.

        All arguments are optional; missing components are flagged as DEGRADED.
        """
        entries: list[SmokeReportEntry] = []

        # Feed health
        entries.append(self._eval_feed_health(feed_health_state))
        # Spread
        entries.append(self._eval_spread(spread_state))
        # Clock
        entries.append(self._eval_clock(clock_state))
        # Session
        entries.append(self._eval_session(session_result))
        # Tick recorder
        entries.append(self._eval_tick_recorder(tick_recorder_state))
        # Watermark
        entries.append(self._eval_watermark(watermark_state))
        # Account
        entries.append(self._eval_account(account_snapshot))

        overall = "PASS" if all(e.status == "OK" for e in entries) else "FAIL"

        now = datetime.now(UTC)
        report_id = f"smoke-{now.strftime('%Y%m%d%H%M%S')}-{self._symbol}"

        return SmokeReport(
            report_id=report_id,
            symbol=self._symbol,
            generated_at_utc=now,
            entries=entries,
            overall_status=overall,
        )

    def _eval_feed_health(self, state: Any) -> SmokeReportEntry:
        if state is None:
            return SmokeReportEntry("feed_health", "DEGRADED", "No state provided")
        try:
            level = getattr(state, "level", None)
            if level and hasattr(level, "value"):
                level = level.value
            if level == "HEALTHY":
                return SmokeReportEntry("feed_health", "OK", f"Level: {level}")
            return SmokeReportEntry("feed_health", "DEGRADED", f"Level: {level}")
        except Exception as e:
            return SmokeReportEntry("feed_health", "FAILED", str(e))

    def _eval_spread(self, state: Any) -> SmokeReportEntry:
        if state is None:
            return SmokeReportEntry("spread", "DEGRADED", "No state provided")
        try:
            is_wide = getattr(state, "is_wide", True)
            if is_wide:
                return SmokeReportEntry("spread", "DEGRADED", "Spread is wide")
            return SmokeReportEntry("spread", "OK", "Spread is normal")
        except Exception as e:
            return SmokeReportEntry("spread", "FAILED", str(e))

    def _eval_clock(self, state: Any) -> SmokeReportEntry:
        if state is None:
            return SmokeReportEntry("clock", "DEGRADED", "No state provided")
        try:
            is_drifted = getattr(state, "is_drifted", True)
            if is_drifted:
                drift = getattr(state, "drift_ms", "N/A")
                return SmokeReportEntry("clock", "DEGRADED", f"Drifted: {drift}ms")
            return SmokeReportEntry("clock", "OK", "Clock synchronized")
        except Exception as e:
            return SmokeReportEntry("clock", "FAILED", str(e))

    def _eval_session(self, state: Any) -> SmokeReportEntry:
        if state is None:
            return SmokeReportEntry("session", "DEGRADED", "No state provided")
        try:
            is_open = getattr(state, "is_open", False)
            if is_open:
                return SmokeReportEntry("session", "OK", "Market is open")
            s = getattr(state, "state", "UNKNOWN")
            if hasattr(s, "value"):
                s = s.value
            return SmokeReportEntry("session", "DEGRADED", f"Market closed: {s}")
        except Exception as e:
            return SmokeReportEntry("session", "FAILED", str(e))

    def _eval_tick_recorder(self, state: Any) -> SmokeReportEntry:
        if state is None:
            return SmokeReportEntry("tick_recorder", "DEGRADED", "No state provided")
        try:
            gaps = getattr(state, "gaps_detected", 0)
            ooo = getattr(state, "out_of_order_count", 0)
            total = getattr(state, "total_ticks_recorded", 0)
            if gaps > 0 or ooo > 0:
                return SmokeReportEntry(
                    "tick_recorder",
                    "DEGRADED",
                    f"gaps={gaps}, out_of_order={ooo}, total={total}",
                )
            return SmokeReportEntry("tick_recorder", "OK", f"ticks={total}, no issues")
        except Exception as e:
            return SmokeReportEntry("tick_recorder", "FAILED", str(e))

    def _eval_watermark(self, state: Any) -> SmokeReportEntry:
        if state is None:
            return SmokeReportEntry("watermark", "DEGRADED", "No state provided")
        try:
            is_fresh = getattr(state, "is_fresh", False)
            if is_fresh:
                return SmokeReportEntry("watermark", "OK", "Data is fresh")
            return SmokeReportEntry("watermark", "DEGRADED", "Data is stale")
        except Exception as e:
            return SmokeReportEntry("watermark", "FAILED", str(e))

    def _eval_account(self, state: Any) -> SmokeReportEntry:
        if state is None:
            return SmokeReportEntry("account", "DEGRADED", "No snapshot provided")
        try:
            balance = getattr(state, "balance", 0)
            equity = getattr(state, "equity", 0)
            return SmokeReportEntry(
                "account",
                "OK",
                f"balance={balance:.2f}, equity={equity:.2f}",
            )
        except Exception as e:
            return SmokeReportEntry("account", "FAILED", str(e))
