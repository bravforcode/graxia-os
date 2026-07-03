"""Portfolio stress testing framework.

Runs pre-defined and custom scenarios against the current portfolio to
estimate worst-case losses under extreme market conditions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ── Scenario definition ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScenarioShock:
    """Price shock to apply to a symbol or asset class.

    ``shock_pct`` is a signed fractional move (e.g. -0.20 = -20%).
    ``vol_multiplier`` scales historical volatility during the scenario.
    ``correlation_override`` forces pairwise correlation (0-1) when set.
    """

    shock_pct: float = 0.0
    vol_multiplier: float = 1.0
    correlation_override: Optional[float] = None


@dataclass
class Scenario:
    """A named stress scenario with shocks keyed by symbol or ``"*"`` (portfolio-wide)."""

    name: str
    description: str
    shocks: dict[str, ScenarioShock] = field(default_factory=dict)
    duration_bars: int = 1

    def get_shock(self, symbol: str) -> ScenarioShock:
        """Return the shock for *symbol*, falling back to portfolio-wide ``"*"``."""
        return self.shocks.get(symbol, self.shocks.get("*", ScenarioShock()))


# ── Pre-built scenarios ─────────────────────────────────────────────────────

SCENARIOS: dict[str, Scenario] = {
    "market_crash": Scenario(
        name="market_crash",
        description="Broad market sell-off: -20% equities, -10% metals, vol 3x",
        shocks={
            "*": ScenarioShock(shock_pct=-0.10, vol_multiplier=3.0, correlation_override=0.85),
            "XAUUSD": ScenarioShock(shock_pct=-0.05, vol_multiplier=2.0),
        },
        duration_bars=5,
    ),
    "flash_crash": Scenario(
        name="flash_crash",
        description="Sudden liquidity vacuum: -8% in 1 bar, vol 5x",
        shocks={
            "*": ScenarioShock(shock_pct=-0.08, vol_multiplier=5.0, correlation_override=0.95),
        },
        duration_bars=1,
    ),
    "correlation_breakdown": Scenario(
        name="correlation_breakdown",
        description="Historical correlations break: assets diverge, vol 2x",
        shocks={
            "*": ScenarioShock(shock_pct=-0.03, vol_multiplier=2.0, correlation_override=0.0),
        },
        duration_bars=3,
    ),
    "liquidity_crisis": Scenario(
        name="liquidity_crisis",
        description="Severe liquidity withdrawal: spreads blow out, vol 4x, -12%",
        shocks={
            "*": ScenarioShock(shock_pct=-0.12, vol_multiplier=4.0, correlation_override=0.90),
        },
        duration_bars=2,
    ),
}


# ── Result models ────────────────────────────────────────────────────────────


@dataclass
class PositionStressResult:
    """Stress impact on a single position."""

    symbol: str
    pre_shock_value: float
    post_shock_value: float
    loss: float
    loss_pct: float
    max_loss_with_vol: float


@dataclass
class ScenarioResult:
    """Aggregate result of running one scenario."""

    scenario_name: str
    description: str
    timestamp: float
    portfolio_pre_value: float
    portfolio_post_value: float
    total_loss: float
    total_loss_pct: float
    max_loss_with_vol: float
    position_results: list[PositionStressResult] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


@dataclass
class StressReport:
    """Full stress test report across all run scenarios."""

    equity: float
    timestamp: float
    scenarios_run: int
    worst_scenario: str
    worst_loss_pct: float
    results: list[ScenarioResult] = field(default_factory=list)


# ── Core engine ──────────────────────────────────────────────────────────────


@dataclass
class StressPosition:
    """Minimal position input for stress testing."""

    symbol: str
    direction: str  # "LONG" | "SHORT"
    quantity: float
    entry_price: float
    current_price: float
    volatility: float = 0.15  # annualised vol (default 15%)


class StressTest:
    """Portfolio stress tester.

    Usage::

        st = StressTest(equity=100_000.0)
        st.set_positions([...])
        report = st.run_historical_stress()
        single  = st.run_scenario("flash_crash")
    """

    def __init__(
        self,
        equity: float = 100_000.0,
        custom_scenarios: dict[str, Scenario] | None = None,
    ):
        self._equity = equity
        self._positions: list[StressPosition] = []
        self._scenarios = {**SCENARIOS}
        if custom_scenarios:
            self._scenarios.update(custom_scenarios)

        logger.info("stresstest.init", equity=equity, scenarios=list(self._scenarios.keys()))

    # ── Configuration ───────────────────────────────────────────────────

    def set_positions(self, positions: list[StressPosition]) -> None:
        """Set the portfolio positions to stress-test."""
        self._positions = list(positions)
        logger.debug("stresstest.positions_set", count=len(positions))

    def add_scenario(self, scenario: Scenario) -> None:
        """Register a custom scenario."""
        self._scenarios[scenario.name] = scenario
        logger.info("stresstest.scenario_added", name=scenario.name)

    @property
    def available_scenarios(self) -> list[str]:
        return list(self._scenarios.keys())

    # ── Runners ─────────────────────────────────────────────────────────

    def run_scenario(self, scenario_name: str) -> ScenarioResult:
        """Run a single named scenario against the current portfolio."""
        scenario = self._scenarios.get(scenario_name)
        if scenario is None:
            raise ValueError(f"Unknown scenario: {scenario_name!r}. Available: {self.available_scenarios}")

        logger.info("stresstest.run_scenario", scenario=scenario_name)
        return self._execute_scenario(scenario)

    def run_historical_stress(self) -> StressReport:
        """Run all registered pre-built scenarios and return a summary report."""
        results: list[ScenarioResult] = []
        for name in SCENARIOS:
            results.append(self._execute_scenario(self._scenarios[name]))

        worst = max(results, key=lambda r: abs(r.total_loss_pct)) if results else None
        report = StressReport(
            equity=self._equity,
            timestamp=time.time(),
            scenarios_run=len(results),
            worst_scenario=worst.scenario_name if worst else "",
            worst_loss_pct=worst.total_loss_pct if worst else 0.0,
            results=results,
        )

        logger.info(
            "stresstest.historical_stress_complete",
            scenarios=report.scenarios_run,
            worst=report.worst_scenario,
            worst_loss=f"{report.worst_loss_pct:.4f}",
        )
        return report

    def get_stress_results(self, results: list[ScenarioResult]) -> dict[str, object]:
        """Format scenario results into a serialisable dict for reporting."""
        return {
            "equity": self._equity,
            "timestamp": time.time(),
            "scenarios": [
                {
                    "name": r.scenario_name,
                    "description": r.description,
                    "total_loss": r.total_loss,
                    "total_loss_pct": r.total_loss_pct,
                    "max_loss_with_vol": r.max_loss_with_vol,
                    "alerts": r.alerts,
                    "positions": [
                        {
                            "symbol": pr.symbol,
                            "loss": pr.loss,
                            "loss_pct": pr.loss_pct,
                            "max_loss_with_vol": pr.max_loss_with_vol,
                        }
                        for pr in r.position_results
                    ],
                }
                for r in results
            ],
        }

    # ── Execution ───────────────────────────────────────────────────────

    def _execute_scenario(self, scenario: Scenario) -> ScenarioResult:
        """Apply scenario shocks and compute losses."""
        pos_results: list[PositionStressResult] = []
        portfolio_pre = 0.0
        portfolio_post = 0.0
        portfolio_max_loss_vol = 0.0
        alerts: list[str] = []

        for pos in self._positions:
            shock = scenario.get_shock(pos.symbol)
            pre_value = pos.current_price * abs(pos.quantity)
            portfolio_pre += pre_value

            # Apply shock
            shocked_price = pos.current_price * (1.0 + shock.shock_pct)

            # Vol-adjusted worst case: shock +/- (vol * vol_multiplier * sqrt(duration))
            vol_period = shock.vol_multiplier * pos.volatility * np.sqrt(max(scenario.duration_bars, 1))
            worst_price = shocked_price * (1.0 - vol_period)  # adverse direction

            qty = abs(pos.quantity)
            if pos.direction == "LONG":
                post_value = shocked_price * qty
                max_val = worst_price * qty
                loss = pre_value - post_value
                max_loss_vol = pre_value - max_val
            else:
                # Short: P&L = (entry - current) * qty; loss is negative of P&L
                post_value = pos.entry_price * qty  # reference value at entry
                loss = -(pos.entry_price - shocked_price) * qty
                max_loss_vol = -(pos.entry_price - worst_price) * qty

            loss_pct = loss / pre_value if pre_value else 0.0

            pos_results.append(
                PositionStressResult(
                    symbol=pos.symbol,
                    pre_shock_value=pre_value,
                    post_shock_value=post_value,
                    loss=loss,
                    loss_pct=loss_pct,
                    max_loss_with_vol=max_loss_vol,
                )
            )

            portfolio_post += post_value
            portfolio_max_loss_vol += max_loss_vol

        total_loss = portfolio_pre - portfolio_post
        total_loss_pct = total_loss / portfolio_pre if portfolio_pre else 0.0

        # Alert if loss exceeds equity
        if abs(total_loss) > self._equity * 0.10:
            alerts.append(f"Portfolio loss {total_loss_pct:.2%} exceeds 10% of equity")
        if abs(portfolio_max_loss_vol) > self._equity * 0.20:
            alerts.append(f"Vol-adjusted max loss {portfolio_max_loss_vol:.0f} exceeds 20% of equity")

        result = ScenarioResult(
            scenario_name=scenario.name,
            description=scenario.description,
            timestamp=time.time(),
            portfolio_pre_value=portfolio_pre,
            portfolio_post_value=portfolio_post,
            total_loss=total_loss,
            total_loss_pct=total_loss_pct,
            max_loss_with_vol=portfolio_max_loss_vol,
            position_results=pos_results,
            alerts=alerts,
        )

        logger.info(
            "stresstest.scenario_complete",
            scenario=scenario.name,
            loss=f"{total_loss:.0f}",
            loss_pct=f"{total_loss_pct:.4f}",
            max_vol_loss=f"{portfolio_max_loss_vol:.0f}",
        )
        return result
