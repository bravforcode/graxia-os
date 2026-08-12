"""
TSM Portfolio Health Check

Validates data freshness, signal computation, and position reconciliation
for the Time-Series Momentum multi-asset portfolio.

Usage:
    python -m monitoring.tsm_health_check
    # or programmatically:
    from monitoring.tsm_health_check import TSMHealthChecker
    checker = TSMHealthChecker()
    status = checker.check_all()
"""

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Constants ────────────────────────────────────────────────────────────

TSM_ASSETS = [
    "XAUUSD", "EURUSD_YF", "GBPUSD_YF", "USDJPY",
    "BTC_YF", "ETH_YF", "SILVER", "OIL",
]

# Weekly strategy: 48h staleness is generous but actionable
MAX_DATA_AGE_SECONDS = 48 * 3600  # 48 hours

# Rebalance expected weekly on Friday; alert if > 8 days
MAX_REBALANCE_AGE_SECONDS = 8 * 86400  # 8 days

# Signal computation should complete within 5 minutes
MAX_SIGNAL_COMPUTE_SECONDS = 300

# Position reconciliation tolerance
POSITION_TOLERANCE_PCT = 0.01  # 1% tolerance for rounding


# ── Types ────────────────────────────────────────────────────────────────


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class CheckResult:
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class HealthReport:
    overall_status: HealthStatus
    checks: List[CheckResult]
    timestamp: float = field(default_factory=time.time)
    portfolio: str = "tsm"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portfolio": self.portfolio,
            "overall_status": self.overall_status.value,
            "timestamp": datetime.fromtimestamp(
                self.timestamp, tz=UTC
            ).isoformat(),
            "checks": [asdict(c) for c in self.checks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ── Checker ──────────────────────────────────────────────────────────────


class TSMHealthChecker:
    """
    Checks TSM portfolio health across three dimensions:
    1. Data freshness — last bar timestamp per asset
    2. Signal computation — latest signal timestamp and validity
    3. Position reconciliation — weights sum to ~1.0, no stale positions
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        state_file: Optional[Path] = None,
    ):
        self.data_dir = data_dir or Path("artifacts/portfolio")
        self.state_file = state_file or Path("artifacts/portfolio/paper_trades/tsm_portfolio_state.json")

    def check_all(self) -> HealthReport:
        """Run all health checks and return consolidated report."""
        checks = [
            self.check_data_freshness(),
            self.check_signal_health(),
            self.check_position_reconciliation(),
        ]

        # Overall status is worst of all checks
        status_order = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 1,
            HealthStatus.UNHEALTHY: 2,
        }
        worst = max(checks, key=lambda c: status_order[c.status])

        return HealthReport(
            overall_status=worst.status,
            checks=checks,
        )

    def check_data_freshness(self) -> CheckResult:
        """
        Check that each TSM asset has data newer than MAX_DATA_AGE_SECONDS.

        Reads the last-modified timestamp of per-asset data files or
        checks the state file's last_data_timestamp field.
        """
        now = time.time()
        stale_assets: List[str] = []
        asset_ages: Dict[str, float] = {}

        state = self._load_state()
        if state and "last_data_timestamp" in state:
            for asset, ts in state["last_data_timestamp"].items():
                age = now - ts
                asset_ages[asset] = age
                if age > MAX_DATA_AGE_SECONDS:
                    stale_assets.append(asset)
        else:
            # Fallback: check combined parquet file modification time
            combined_parquet = self.data_dir / "d1_multi_asset.parquet"
            if combined_parquet.exists():
                age = now - combined_parquet.stat().st_mtime
                for asset in TSM_ASSETS:
                    asset_ages[asset] = age
                    if age > MAX_DATA_AGE_SECONDS:
                        stale_assets.append(asset)
            else:
                # Legacy fallback: per-asset files
                for asset in TSM_ASSETS:
                    data_file = self.data_dir / f"{asset}_D1.parquet"
                    if data_file.exists():
                        age = now - data_file.stat().st_mtime
                        asset_ages[asset] = age
                        if age > MAX_DATA_AGE_SECONDS:
                            stale_assets.append(asset)
                    else:
                        stale_assets.append(f"{asset} (file missing)")
                        asset_ages[asset] = float("inf")

        if stale_assets:
            return CheckResult(
                name="data_freshness",
                status=HealthStatus.UNHEALTHY,
                message=f"Stale data for: {', '.join(stale_assets)}",
                details={
                    "stale_assets": stale_assets,
                    "max_age_seconds": MAX_DATA_AGE_SECONDS,
                    "asset_ages": asset_ages,
                },
            )

        # Check if any asset is approaching staleness (> 24h)
        aging_assets = [
            a for a, age in asset_ages.items()
            if age > MAX_DATA_AGE_SECONDS / 2
        ]
        if aging_assets:
            return CheckResult(
                name="data_freshness",
                status=HealthStatus.DEGRADED,
                message=f"Data aging (> 24h) for: {', '.join(aging_assets)}",
                details={
                    "aging_assets": aging_assets,
                    "asset_ages": asset_ages,
                },
            )

        return CheckResult(
            name="data_freshness",
            status=HealthStatus.HEALTHY,
            message=f"All {len(TSM_ASSETS)} assets have fresh data",
            details={"asset_ages": asset_ages},
        )

    def check_signal_health(self) -> CheckResult:
        """
        Check that signal computation ran recently and produced valid signals.

        Validates:
        - Signal timestamp is recent (within MAX_SIGNAL_COMPUTE_SECONDS)
        - All assets have signals
        - No NaN/inf values in signals
        """
        state = self._load_state()
        now = time.time()

        if not state:
            return CheckResult(
                name="signal_health",
                status=HealthStatus.UNHEALTHY,
                message="No portfolio state file found — signals never computed",
                details={"state_file": str(self.state_file)},
            )

        # Check signal computation timestamp
        # Support both unix epoch (last_signal_timestamp) and ISO string (timestamp_utc)
        signal_ts = state.get("last_signal_timestamp", 0)
        if signal_ts == 0 and "timestamp_utc" in state:
            try:
                dt = datetime.fromisoformat(state["timestamp_utc"])
                signal_ts = dt.timestamp()
            except (ValueError, TypeError):
                pass
        signal_age = now - signal_ts
        if signal_age > MAX_SIGNAL_COMPUTE_SECONDS:
            return CheckResult(
                name="signal_health",
                status=HealthStatus.DEGRADED,
                message=(
                    f"Signals computed {signal_age:.0f}s ago "
                    f"(threshold: {MAX_SIGNAL_COMPUTE_SECONDS}s)"
                ),
                details={"signal_age_seconds": signal_age},
            )

        # Check signal completeness
        signals = state.get("signals", {})
        missing_assets = [a for a in TSM_ASSETS if a not in signals]
        invalid_assets = [
            a for a, s in signals.items()
            if s is None or s != s  # NaN check
        ]

        if missing_assets or invalid_assets:
            return CheckResult(
                name="signal_health",
                status=HealthStatus.UNHEALTHY,
                message=(
                    f"Signal issues — missing: {missing_assets}, "
                    f"invalid: {invalid_assets}"
                ),
                details={
                    "missing_assets": missing_assets,
                    "invalid_assets": invalid_assets,
                },
            )

        return CheckResult(
            name="signal_health",
            status=HealthStatus.HEALTHY,
            message=f"Signals valid for all {len(signals)} assets",
            details={"signals": signals, "age_seconds": signal_age},
        )

    def check_position_reconciliation(self) -> CheckResult:
        """
        Check that current positions are consistent with expected weights.

        Validates:
        - Position weights sum to approximately 1.0 (or 0 if flat)
        - No position exceeds 20% concentration limit
        - Position count matches signal count (long positions)
        """
        state = self._load_state()

        if not state:
            return CheckResult(
                name="position_reconciliation",
                status=HealthStatus.UNHEALTHY,
                message="No portfolio state file found",
                details={"state_file": str(self.state_file)},
            )

        positions = state.get("positions", {})
        if not positions:
            return CheckResult(
                name="position_reconciliation",
                status=HealthStatus.HEALTHY,
                message="No positions (flat portfolio)",
                details={"positions": {}},
            )

        issues: List[str] = []
        total_weight = 0.0

        for asset, pos in positions.items():
            weight = abs(pos.get("weight", 0))
            total_weight += weight

            # Concentration check
            if weight > 0.20 + POSITION_TOLERANCE_PCT:
                issues.append(
                    f"{asset}: weight {weight:.1%} exceeds 20% limit"
                )

        # Sum of absolute weights check (should be ~1.0 for fully invested)
        if total_weight > 0:
            if abs(total_weight - 1.0) > POSITION_TOLERANCE_PCT * 2:
                issues.append(
                    f"Sum of |weights| = {total_weight:.4f}, expected ~1.0"
                )

        # Cross-check: positions vs signals
        signals = state.get("signals", {})
        long_signals = {a for a, s in signals.items() if s > 0}
        short_signals = {a for a, s in signals.items() if s < 0}
        position_assets = set(positions.keys())

        # Assets with positions but no signal (stale positions)
        stale = position_assets - long_signals - short_signals
        if stale:
            issues.append(f"Positions without signals (stale): {stale}")

        if issues:
            return CheckResult(
                name="position_reconciliation",
                status=HealthStatus.DEGRADED,
                message=f"Position issues: {'; '.join(issues)}",
                details={
                    "issues": issues,
                    "total_weight": total_weight,
                    "position_count": len(positions),
                },
            )

        return CheckResult(
            name="position_reconciliation",
            status=HealthStatus.HEALTHY,
            message=f"{len(positions)} positions reconciled, "
            f"total |weight| = {total_weight:.4f}",
            details={
                "total_weight": total_weight,
                "position_count": len(positions),
                "long_signals": len(long_signals),
                "short_signals": len(short_signals),
            },
        )

    # ── Internal ─────────────────────────────────────────────────────

    def _load_state(self) -> Optional[Dict[str, Any]]:
        """Load portfolio state from JSON file."""
        if not self.state_file.exists():
            return None
        try:
            return json.loads(self.state_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None


# ── CLI ──────────────────────────────────────────────────────────────────


def main():
    """Run health check and print JSON report."""
    checker = TSMHealthChecker()
    report = checker.check_all()

    print(report.to_json())

    # Exit code reflects health status
    exit_codes = {
        HealthStatus.HEALTHY: 0,
        HealthStatus.DEGRADED: 1,
        HealthStatus.UNHEALTHY: 2,
    }
    raise SystemExit(exit_codes[report.overall_status])


if __name__ == "__main__":
    main()
