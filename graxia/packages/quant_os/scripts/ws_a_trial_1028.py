"""WS-A trial 1028 harness — replicate published edge with full MOP2012 TSM rigor.

BINDING CONDITION (reviewer sign-off): data MUST enter via
``load_provenance_checked`` -> ``engine.load_data``. Raw CSV is NEVER fed
directly. Provenance slicing hard-fails on pre-inception fabrication
(EURUSD 1971, NAS100 1938, ...) so the study cannot train on two
centuries of invented candles.

Rigor (MOP2012 TSM):
  - DK-test (deflated Sharpe / multiple-testing correction via DSR, N=1050)
  - DSR with reconciled N=1050 (validation.n_trials)
  - Jackknife (leave-one-bar-out Sharpe stability)
  - Cost stress 1.5x / 2.0x (CostStressAnalyzer)
  - PBO (CSCV) when walk-forward folds supplied

Records trial 1028 as GO / REJECT honestly. On failure: STOP, do not tune.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Make the quant_os package importable when run as a script.
# Repo mixes two import styles: `from quant_os...` (needs graxia/packages on
# path) and `from graxia.packages.quant_os...` (needs the REPO ROOT
# `C:/Users/menum/graxia os` on path so `graxia` resolves as a package, used
# by validation/__init__.py). Add both.
_REPO_PKGS = Path(__file__).resolve().parents[2]  # graxia/packages
_REPO_ROOT = Path(__file__).resolve().parents[4]   # C:/Users/menum/graxia os (repo root)
for _p in (str(_REPO_PKGS), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from decimal import Decimal  # noqa: E402

from quant_os.provenance import load_provenance_checked  # noqa: E402
from quant_os.backtest.engine import BacktestEngine, BacktestConfig  # noqa: E402
from quant_os.validation.overfitting_detector import OverfittingDetector  # noqa: E402
from quant_os.validation.n_trials import get_reconciled_n_trials  # noqa: E402
from quant_os.strategies.base import Strategy, StrategyConfig, Signal  # noqa: E402
from quant_os.core.enums import SignalType, RegimeType  # noqa: E402


def _provenance_to_engine_input(df, time_col: str) -> tuple[dict[str, list], list[datetime]]:
    """Convert a provenance-checked DataFrame into engine.load_data() inputs.

    This is the ONLY bridge between provenance slicing and the engine. Raw
    CSV never reaches load_data.
    """
    ohlcv: dict[str, list] = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
    }
    timestamps = [t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in df[time_col].tolist()]
    return ohlcv, timestamps


def _bar_returns_from_equity(equity_curve: list) -> list[float]:
    """Per-bar simple returns from the engine equity curve."""
    rets: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = float(equity_curve[i - 1].equity)
        cur = float(equity_curve[i].equity)
        if prev > 0:
            rets.append((cur - prev) / prev)
    return rets


def _jackknife_sharpe(returns: list[float]) -> tuple[float, float]:
    """Leave-one-out Sharpe stability. Returns (mean_sharpe, min_sharpe)."""
    import math

    n = len(returns)
    if n < 10:
        return (0.0, 0.0)
    sharpes: list[float] = []
    for i in range(n):
        sub = returns[:i] + returns[i + 1:]
        m = sum(sub) / len(sub)
        var = sum((x - m) ** 2 for x in sub) / max(len(sub) - 1, 1)
        sd = math.sqrt(var) if var > 0 else 0.0
        if sd > 0:
            sharpes.append((m / sd) * math.sqrt(252))
    if not sharpes:
        return (0.0, 0.0)
    return (sum(sharpes) / len(sharpes), min(sharpes))


def run_ws_a_trial_1028(
    symbol: str,
    strategy: Strategy,
    slice_start: str = "2005-01-01",
    slice_end: str | None = None,
) -> dict:
    """Run WS-A trial 1028 for one symbol/strategy. Returns the verdict dict."""
    # 1) Provenance-checked load (hard-fails on contaminated data).
    df = load_provenance_checked(symbol, slice_start=slice_start, slice_end=slice_end)
    time_col = "time" if "time" in df.columns else "date"
    ohlcv, timestamps = _provenance_to_engine_input(df, time_col)

    # 2) Feed ONLY the provenance output into the engine. Never raw CSV.
    engine = BacktestEngine(config=BacktestConfig(strict_mtf=False))
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    result = engine.run()

    # 3) Rigor — DSR (N=1050), PBO, cost-stress, jackknife.
    n_trials = get_reconciled_n_trials()  # WS-C authoritative N = 1050
    bar_rets = _bar_returns_from_equity(result["equity_curve"])
    cost_pnl = float(getattr(result["metrics"], "total_pnl", 0.0))
    # Costs live on individual trades (engine metrics has no total_costs field).
    total_costs = float(sum(getattr(t, "fees", 0.0) for t in result.get("trades", [])))

    detector = OverfittingDetector()
    # PBO needs walk-forward folds; a single backtest supplies none, so PBO is
    # reported as "insufficient data" by the detector. The WS-A study design
    # must feed real WF folds here for a valid PBO.
    report = detector.evaluate(
        strategy_id=f"ws_a_1028_{symbol}",
        returns=bar_rets,
        n_trials=n_trials,
        n_observations=len(bar_rets),
        oos_returns_per_fold=[],
        cost_pnl=cost_pnl,
        total_costs=total_costs,
        param_values=[getattr(strategy, "period", 0)],
        param_pnls=[cost_pnl],
        data_length=len(bar_rets),
    )

    # Cost stress 1.5x / 2.0x is computed inside the detector (CostStressResult).
    csr = getattr(report, "cost_stress_result", None)

    # Jackknife stability.
    mean_sharpe, min_sharpe = _jackknife_sharpe(bar_rets)

    verdict = {
        "trial": "WS-A-1028",
        "symbol": symbol,
        "n_trials_dsr": n_trials,
        "dsr_passed": report.passed if hasattr(report, "passed") else None,
        "dsr_blockers": getattr(report, "blockers", []),
        "cost_stress_1_5x_survives": bool(getattr(csr, "survives_stress_1", False)) if csr else False,
        "cost_stress_2_0x_survives": bool(getattr(csr, "survives_stress_2", False)) if csr else False,
        "jackknife_mean_sharpe": round(mean_sharpe, 3),
        "jackknife_min_sharpe": round(min_sharpe, 3),
        "go": bool(report.passed) and bool(getattr(csr, "survives_stress_1", False)) and min_sharpe > 0,
    }
    return verdict


if __name__ == "__main__":
    # Minimal Donchian breakout as a runnable default strategy for the harness.
    # Replace with the actual WS-A candidate strategy when available.
    class _DonchianWS(Strategy):
        def __init__(self, period: int = 20):
            super().__init__(StrategyConfig(name=f"ws_donchian_{period}"))
            self.period = period

        def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kw):
            c = ohlcv_data["close"]
            if len(c) < self.period + 1:
                return None
            hh = max(c[-self.period - 1 : -1])
            ll = min(c[-self.period - 1 : -1])
            price = c[-1]
            if price >= hh:
                return Signal.create(strategy_id=self.id, symbol=symbol, signal_type=SignalType.BUY,
                                     confidence=0.7, entry_price=Decimal(str(price)),
                                     stop_loss=Decimal(str(price * 0.99)),
                                     take_profit=Decimal(str(price * 1.02)))
            if price <= ll:
                return Signal.create(strategy_id=self.id, symbol=symbol, signal_type=SignalType.SELL,
                                     confidence=0.7, entry_price=Decimal(str(price)),
                                     stop_loss=Decimal(str(price * 1.01)),
                                     take_profit=Decimal(str(price * 0.98)))
            return None

        def required_features(self):
            return []

    sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    v = run_ws_a_trial_1028(sym, _DonchianWS())
    print(f"WS-A trial 1028 [{sym}]: {'GO' if v['go'] else 'REJECT'}")
    for k, val in v.items():
        print(f"  {k}: {val}")
