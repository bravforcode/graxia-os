"""Smoke report — structured verification result for MT5 runtime readiness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .broker_profile import BrokerProfile
    from .runtime_capabilities import RuntimeCapabilities


@dataclass
class SmokeReport:
    profile_id: str
    timestamp_utc: datetime
    capabilities: RuntimeCapabilities
    all_checks_passed: bool
    issues: list[str] = field(default_factory=list)
    verdict: str = "FAIL"  # "PASS" | "FAIL" | "DEGRADED"

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "all_checks_passed": self.all_checks_passed,
            "issues": self.issues,
            "verdict": self.verdict,
            "capabilities": {
                "mt5_initialized": self.capabilities.mt5_initialized,
                "terminal_connected": self.capabilities.terminal_connected,
                "terminal_info": self.capabilities.terminal_info,
                "account_info_redacted": self.capabilities.account_info_redacted,
                "server_name": self.capabilities.server_name,
                "account_currency": self.capabilities.account_currency,
                "symbols_available": self.capabilities.symbols_available,
                "tick_access": self.capabilities.tick_access,
                "bar_access": self.capabilities.bar_access,
                "order_calc_profit": self.capabilities.order_calc_profit,
                "order_calc_margin": self.capabilities.order_calc_margin,
                "positions_visible": self.capabilities.positions_visible,
                "orders_visible": self.capabilities.orders_visible,
                "history_visible": self.capabilities.history_visible,
                "utc_offset_ms": self.capabilities.utc_offset_ms,
                "issues": self.capabilities.issues,
            },
        }


def generate_smoke_report(
    profile: BrokerProfile,
    capabilities: RuntimeCapabilities,
) -> SmokeReport:
    """Create a SmokeReport from a profile and its verification results."""
    issues = list(capabilities.issues)
    all_checks_passed = len(issues) == 0

    if all_checks_passed:
        verdict = "PASS"
    elif capabilities.mt5_initialized and capabilities.terminal_connected:
        verdict = "DEGRADED"
    else:
        verdict = "FAIL"

    return SmokeReport(
        profile_id=profile.profile_id,
        timestamp_utc=datetime.now(UTC),
        capabilities=capabilities,
        all_checks_passed=all_checks_passed,
        issues=issues,
        verdict=verdict,
    )


def persist_smoke_report(report: SmokeReport, directory: str | Path) -> Path:
    """Save smoke report as JSON. Returns path to the written file."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    ts = report.timestamp_utc.strftime("%Y%m%d_%H%M%S")
    filename = f"smoke_report_{report.profile_id}_{ts}.json"
    filepath = directory / filename

    data = report.to_dict()
    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return filepath


def format_smoke_report_human(report: SmokeReport) -> str:
    """Render a human-readable smoke report."""
    lines = [
        "=" * 60,
        f"  SMOKE REPORT — {report.profile_id}",
        f"  Timestamp: {report.timestamp_utc.isoformat()}",
        f"  Verdict:   {report.verdict}",
        "=" * 60,
        "",
        "  Runtime Capabilities:",
        f"    MT5 Initialized:     {report.capabilities.mt5_initialized}",
        f"    Terminal Connected:  {report.capabilities.terminal_connected}",
        f"    Account Currency:    {report.capabilities.account_currency}",
        f"    Server:              {report.capabilities.server_name or '(unknown)'}",
        f"    Tick Access:         {report.capabilities.tick_access}",
        f"    Bar Access:          {report.capabilities.bar_access}",
        f"    order_calc_profit:   {report.capabilities.order_calc_profit}",
        f"    order_calc_margin:   {report.capabilities.order_calc_margin}",
        f"    Positions Visible:   {report.capabilities.positions_visible}",
        f"    Orders Visible:      {report.capabilities.orders_visible}",
        f"    History Visible:     {report.capabilities.history_visible}",
        f"    UTC Offset (ms):     {report.capabilities.utc_offset_ms}",
        f"    Symbols Probed:      {report.capabilities.symbols_available}",
        "",
    ]

    if report.capabilities.account_info_redacted:
        ai = report.capabilities.account_info_redacted
        lines.append("  Account (redacted):")
        lines.append(f"    Login (masked):  {ai.get('login_masked', '****')}")
        lines.append(f"    Server (masked): {ai.get('server_masked', '****')}")
        lines.append(f"    Leverage:        {ai.get('leverage', 0)}")
        lines.append(f"    Balance:         {ai.get('balance', 0.0)}")
        lines.append(f"    Equity:          {ai.get('equity', 0.0)}")
        lines.append("")

    if report.issues:
        lines.append(f"  Issues ({len(report.issues)}):")
        for i, issue in enumerate(report.issues, 1):
            lines.append(f"    {i}. {issue}")
    else:
        lines.append("  No issues found.")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
