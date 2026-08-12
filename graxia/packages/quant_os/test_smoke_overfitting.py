"""Smoke test: verify auto overfitting detection fires when >= 10 trades."""

import random
from datetime import UTC, datetime, timedelta

from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.strategies.base import Signal


class TradingStrategy:
    id = "momentum_v1"
    _counter = 0

    def generate_signal(self, **kw):
        self._counter += 1
        if self._counter % 20 == 0:
            close = kw["ohlcv_data"]["close"][-1]
            sl = close * 0.98 if random.random() > 0.5 else close * 1.02
            return Signal.create(
                strategy_id="momentum_v1",
                symbol="XAUUSD",
                signal_type=SignalType.BUY if random.random() > 0.5 else SignalType.SELL,
                entry_price=close,
                stop_loss=sl,
                take_profit=close * 1.05,
            )
        return None


def test_auto_overfitting():
    n = 500
    random.seed(42)
    close = [2000.0]
    for _ in range(n - 1):
        close.append(close[-1] * (1 + random.gauss(0, 0.005)))
    data = {
        "open": close[:],
        "high": [c * 1.002 for c in close],
        "low": [c * 0.998 for c in close],
        "close": close,
        "volume": [1000.0] * n,
    }
    ts = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i) for i in range(n)]

    cfg = BacktestConfig(strict_mtf=False)
    engine = BacktestEngine(cfg)
    engine.set_strategy(TradingStrategy())
    engine.load_data(data, ts)
    results = engine.run()

    n_trades = len(results["trades"])
    assert n_trades >= 10, f"Expected >=10 trades, got {n_trades}"
    assert "overfitting" in results, "Missing overfitting key"
    of = results["overfitting"]
    assert "score" in of, "Missing score"
    assert "recommendation" in of, "Missing recommendation"
    print(f"Trades: {n_trades}")
    print(f"Overfitting score: {of['score']}")
    print(f"Recommendation: {of['recommendation']}")
    print(f"Blockers: {of.get('blockers', [])}")
    print(f"Warnings: {of.get('warnings', [])}")

    report = engine.get_overfitting_report()
    assert report is not None
    assert "overfitting" in report
    print("PASS: Auto overfitting detection works!")


if __name__ == "__main__":
    test_auto_overfitting()
