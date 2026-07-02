from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Dict, List
import hashlib
import json

from graxia.packages.quant_os.validation.locked_inputs import LockedInputs
from graxia.packages.quant_os.validation.run_config import RunConfig
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig

@dataclass
class ValidationResult:
    run_config: RunConfig
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    expectancy: float = 0.0
    cost_attribution: Dict[str, float] = field(default_factory=dict)
    metrics_hash: str = ""
    error: Optional[str] = None

    def compute_hash(self) -> str:
        data = json.dumps({
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_pnl": self.total_pnl,
            "max_drawdown_pct": self.max_drawdown_pct,
            "expectancy": self.expectancy,
        }, sort_keys=True)
        self.metrics_hash = hashlib.sha256(data.encode()).hexdigest()
        return self.metrics_hash

class NativeRunner:
    def __init__(self):
        self._results: List[ValidationResult] = []

    def run(self, config: RunConfig, strategy, data: Dict[str, List], timestamps: list) -> ValidationResult:
        """Run native quant_os backtest with given config."""
        try:
            cost_scenario = config.cost_scenario

            bt_config = BacktestConfig(
                initial_capital=Decimal("100000"),
                slippage_pips=0.5 * float(cost_scenario.slippage_multiplier),
                commission_per_lot=Decimal("3.5") * cost_scenario.commission_multiplier,
                risk_per_trade_bps=100,
                strict_mtf=False,
                cost_scenario=cost_scenario.name,
            )

            engine = BacktestEngine(bt_config)
            engine.set_strategy(strategy)
            engine.load_data(data, timestamps)
            results = engine.run()

            if not results:
                return ValidationResult(
                    run_config=config,
                    error="Engine returned empty results"
                )

            metrics = results.get("metrics", {})
            trades = results.get("trades", [])

            total_pnl = sum(t.get("pnl", 0) for t in trades)
            winning = [t for t in trades if t.get("pnl", 0) > 0]
            win_rate = len(winning) / len(trades) if trades else 0

            gross_profit = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)
            gross_loss = abs(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

            max_dd = 0.0
            equity_curve = results.get("equity_curve", [])
            if equity_curve:
                peak = max(ep.get("equity", 0) for ep in equity_curve)
                trough = min(ep.get("equity", 0) for ep in equity_curve)
                max_dd = ((peak - trough) / peak * 100) if peak > 0 else 0

            expectancy = total_pnl / len(trades) if trades else 0

            spread_cost = sum(t.get("entry_spread_cost", 0) + t.get("exit_slippage_cost", 0) for t in trades)

            result = ValidationResult(
                run_config=config,
                total_trades=len(trades),
                win_rate=win_rate,
                profit_factor=profit_factor,
                total_pnl=float(total_pnl),
                max_drawdown_pct=max_dd,
                expectancy=float(expectancy),
                cost_attribution={
                    "spread_cost": float(spread_cost),
                    "total_fees": float(sum(t.get("fees", 0) for t in trades)),
                },
            )
            result.compute_hash()
            self._results.append(result)
            return result

        except Exception as e:
            result = ValidationResult(run_config=config, error=str(e))
            self._results.append(result)
            return result

    def run_all_cost_scenarios(self, strategy, data: Dict[str, List], timestamps: list, locked_inputs: LockedInputs) -> List[ValidationResult]:
        from graxia.packages.quant_os.validation.cost_scenarios import ALL_SCENARIOS
        results = []
        for scenario in ALL_SCENARIOS:
            config = RunConfig(
                run_id=f"native_{scenario.name}",
                run_type="native",
                locked_inputs=locked_inputs,
                cost_scenario=scenario,
            )
            result = self.run(config, strategy, data, timestamps)
            results.append(result)
        return results

    def get_results(self) -> List[ValidationResult]:
        return self._results
