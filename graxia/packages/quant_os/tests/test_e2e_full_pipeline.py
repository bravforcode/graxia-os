"""
End-to-end integration test: Signal → Risk → Execution → Ledger → Reconciliation
Tests the full pipeline with ALL gates active.
"""
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.strategies.base import Strategy, StrategyConfig, Signal
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.backtest.metrics import BacktestMetrics


class FullPipelineStrategy(Strategy):
    """Simple strategy that generates signals on every bar for testing."""

    def __init__(self):
        super().__init__(StrategyConfig(name="FullPipelineStrategy"))
        self._bar_count = 0

    def required_features(self):
        return []

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        close = ohlcv_data.get("close", [])
        if len(close) < 10:
            return None

        self._bar_count += 1
        current = close[-1]
        prev = close[-2]

        if self._bar_count % 20 == 0:
            if current > prev:
                return Signal.create(
                    strategy_id=self.id,
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    confidence=0.7,
                    entry_price=Decimal(str(current)),
                    stop_loss=Decimal(str(current * 0.995)),
                    take_profit=Decimal(str(current * 1.01)),
                )
            elif current < prev:
                return Signal.create(
                    strategy_id=self.id,
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    confidence=0.7,
                    entry_price=Decimal(str(current)),
                    stop_loss=Decimal(str(current * 1.005)),
                    take_profit=Decimal(str(current * 0.99)),
                )
        return None


class NoStopLossStrategy(Strategy):
    """Strategy that generates BUY signals without stop_loss — engine must reject."""

    def __init__(self):
        super().__init__(StrategyConfig(name="NoStopLossStrategy"))
        self._bar_count = 0

    def required_features(self):
        return []

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        close = ohlcv_data.get("close", [])
        if len(close) < 10:
            return None

        self._bar_count += 1
        if self._bar_count == 20:
            return Signal.create(
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=0.7,
                entry_price=Decimal(str(close[-1])),
            )
        return None


def generate_data(n=500):
    import random
    random.seed(42)
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    price = 2350.0
    for _ in range(n):
        change = random.gauss(0.0003, 0.001)
        o = price
        c = price * (1 + change)
        h = max(o, c) * 1.0005
        l = min(o, c) * 0.9995
        data["open"].append(round(o, 2))
        data["close"].append(round(c, 2))
        data["high"].append(round(h, 2))
        data["low"].append(round(l, 2))
        data["volume"].append(100000)
        price = c
    return data


class TestE2EFullPipeline:
    """Full pipeline: strategy → engine → execution → ledger → metrics."""

    def test_full_pipeline_runs(self):
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            slippage_pips=0.5,
            commission_per_lot=Decimal("3.5"),
            risk_per_trade_bps=100,
            strict_mtf=False,
        )
        engine = BacktestEngine(config)
        engine.set_strategy(FullPipelineStrategy())

        data = generate_data(500)
        timestamps = [datetime(2025, 1, 1) + timedelta(hours=i) for i in range(500)]
        engine.load_data(data, timestamps)
        results = engine.run()

        assert results is not None
        assert "metrics" in results
        assert "trades" in results

        trades = results.get("trades", [])
        if trades:
            for t in trades:
                assert "entry_spread_cost" in t
                assert "entry_slippage_cost" in t
                assert "exit_slippage_cost" in t
                assert "fees" in t
                assert "pnl" in t

    def test_engine_rejects_signal_without_sl(self):
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            strict_mtf=False,
        )
        engine = BacktestEngine(config)
        engine.set_strategy(NoStopLossStrategy())

        data = generate_data(500)
        timestamps = [datetime(2025, 1, 1) + timedelta(hours=i) for i in range(500)]
        engine.load_data(data, timestamps)
        results = engine.run()

        assert results is not None
        trades = results.get("trades", [])
        assert len(trades) == 0, "NoStopLossStrategy should produce zero trades (SL rejected)"

    def test_metrics_calculation(self):
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            strict_mtf=False,
        )
        engine = BacktestEngine(config)
        engine.set_strategy(FullPipelineStrategy())

        data = generate_data(500)
        timestamps = [datetime(2025, 1, 1) + timedelta(hours=i) for i in range(500)]
        engine.load_data(data, timestamps)
        results = engine.run()

        metrics = results.get("metrics")
        assert isinstance(metrics, BacktestMetrics)
        assert hasattr(metrics, 'total_trades')
        assert hasattr(metrics, 'win_rate')

    def test_same_inputs_same_results(self):
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            strict_mtf=False,
        )

        data = generate_data(500)
        timestamps = [datetime(2025, 1, 1) + timedelta(hours=i) for i in range(500)]

        engine1 = BacktestEngine(config)
        engine1.set_strategy(FullPipelineStrategy())
        engine1.load_data(data, timestamps)
        r1 = engine1.run()

        engine2 = BacktestEngine(config)
        engine2.set_strategy(FullPipelineStrategy())
        engine2.load_data(data, timestamps)
        r2 = engine2.run()

        assert r1["metrics"].total_trades == r2["metrics"].total_trades

    def test_no_mt5_imports_in_engine(self):
        """Engine must not import MT5 modules."""
        engine_path = os.path.join(os.path.dirname(__file__), '..', 'backtest', 'engine.py')
        source = open(engine_path).read()
        assert "import MetaTrader5" not in source
        assert "from MetaTrader5" not in source

    def test_no_external_repo_imports(self):
        """Engine must not import external backtesting repos."""
        engine_path = os.path.join(os.path.dirname(__file__), '..', 'backtest', 'engine.py')
        source = open(engine_path).read()
        assert "import vectorbt" not in source
        assert "import backtrader" not in source
        assert "import bt" not in source
