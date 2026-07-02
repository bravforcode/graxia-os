"""Phase BE-P9 — Demo canary runner. Orchestrates full canary flow."""
from dataclasses import dataclass
from datetime import datetime, UTC


@dataclass
class CanaryRunResult:
    run_id: str
    signals_generated: int
    orders_submitted: int
    orders_filled: int
    orders_rejected: int
    preflight_failures: int
    incidents: int
    status: str  # running, completed, failed
    verdict: str = ""


class DemoCanaryRunner:
    """Orchestrate demo canary flow."""

    def __init__(self, config, preflight, order_guard, lifecycle_cls):
        self._config = config
        self._preflight = preflight
        self._order_guard = order_guard
        self._lifecycle_cls = lifecycle_cls
        self._runs: list[CanaryRunResult] = []
        self._active: bool = False

    def run_cycle(self, tick: dict, context: dict) -> CanaryRunResult | None:
        """Execute one canary cycle."""
        if not self._active:
            return None

        result = CanaryRunResult(
            run_id=datetime.now(UTC).isoformat(),
            signals_generated=0,
            orders_submitted=0,
            orders_filled=0,
            orders_rejected=0,
            preflight_failures=0,
            incidents=0,
            status="running",
        )

        # Check preflight
        checks = self._preflight.check_all(context)
        if not self._preflight.all_passed():
            result.preflight_failures = len(self._preflight.get_failed())
            result.status = "blocked"
            result.verdict = "PREFLIGHT_FAILED"
            self._runs.append(result)
            return result

        # Generate signal (simplified)
        result.signals_generated = 1

        # Check order guard
        from graxia.packages.quant_os.canary.demo_order_guard import OrderIntent

        intent = OrderIntent(
            signal_id=f"CANARY_{result.run_id}",
            symbol=tick.get("symbol", "XAUUSD"),
            side="BUY",
            volume=0.01,
            entry_price=tick.get("bid", 0),
            stop_loss=tick.get("bid", 0) - 2.0,
            take_profit=tick.get("bid", 0) + 4.0,
        )

        ok, issues = self._order_guard.preflight(intent)
        if not ok:
            result.preflight_failures = len(issues)
            result.status = "blocked"
            result.verdict = "ORDER_GUARD_FAILED"
            self._runs.append(result)
            return result

        # Submit (hypothetical)
        self._order_guard.mark_submitted(intent)
        result.orders_submitted = 1
        result.orders_filled = 1
        result.status = "completed"
        result.verdict = "SUCCESS"

        self._runs.append(result)
        return result

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    def is_active(self) -> bool:
        return self._active

    def get_runs(self) -> list[CanaryRunResult]:
        return self._runs.copy()

    def get_summary(self) -> dict:
        total = len(self._runs)
        filled = sum(r.orders_filled for r in self._runs)
        return {
            "total_runs": total,
            "total_filled": filled,
            "status": "active" if self._active else "idle",
        }
