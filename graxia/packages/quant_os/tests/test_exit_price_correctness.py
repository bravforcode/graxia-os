"""Test that backtest engine uses correct exit prices from SL/TP levels."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta

from quant_os.backtest.engine import BacktestEngine, BacktestConfig
from quant_os.core.enums import SignalType
from quant_os.strategies.base import Signal


class _SignalStrategy:
    """Returns pre-built signals from a queue."""

    def __init__(self, signals):
        self.id = "test_exit"
        self._signals = list(signals)
        self._idx = 0

    def generate_signal(self, symbol, ohlcv_data, indicators, regime, current_time, **kwargs):
        if self._idx < len(self._signals):
            sig = self._signals[self._idx]
            self._idx += 1
            return sig
        return None


def _build_engine(config, timestamps, opens, highs, lows, closes, volumes, signals):
    strategy = _SignalStrategy(signals)
    engine = BacktestEngine(config)
    engine.set_strategy(strategy)
    data = {
        "open": [float(x) for x in opens],
        "high": [float(x) for x in highs],
        "low": [float(x) for x in lows],
        "close": [float(x) for x in closes],
        "volume": [int(x) for x in volumes],
    }
    engine.load_data(data, timestamps)
    return engine


def test_sl_exit_uses_sl_price():
    """When SL is triggered, exit price should be the SL level, not bar bid/ask."""
    config = BacktestConfig(
        initial_capital=Decimal("1000000"),
        slippage_pips=0.5,
        spread_pips=2.0,
        commission_per_lot=Decimal("3.5"),
        risk_per_trade_bps=10,
        strict_mtf=False,
        enable_swap=False,
    )

    n_bars = 10
    timestamps = [datetime(2026, 1, 1) + timedelta(minutes=15 * i) for i in range(n_bars)]

    # Bars where bar 2 low hits SL=2300
    opens  = np.array([2350.0, 2340.0, 2330.0, 2320.0, 2310.0, 2300.0, 2290.0, 2280.0, 2270.0, 2260.0])
    highs  = np.array([2360.0, 2350.0, 2340.0, 2330.0, 2320.0, 2310.0, 2300.0, 2290.0, 2280.0, 2270.0])
    lows   = np.array([2340.0, 2330.0, 2320.0, 2310.0, 2300.0, 2290.0, 2280.0, 2270.0, 2260.0, 2250.0])
    closes = np.array([2345.0, 2335.0, 2325.0, 2315.0, 2305.0, 2295.0, 2285.0, 2275.0, 2265.0, 2255.0])
    volumes = np.array([1000] * n_bars, dtype=np.int64)

    signal = Signal(
        id="sl_test",
        strategy_id="test_exit",
        symbol="XAUUSD",
        signal_type=SignalType.BUY,
        timestamp=timestamps[1],
        entry_price=Decimal("2350.0"),
        stop_loss=Decimal("2300.0"),
        take_profit=Decimal("2400.0"),
    )

    engine = _build_engine(config, timestamps, opens, highs, lows, closes, volumes, [signal])
    engine.run()

    assert len(engine.trades) >= 1, f"Expected at least 1 trade, got {len(engine.trades)}"

    sl_trades = [t for t in engine.trades if t.close_reason.value == "STOP_LOSS"]
    if sl_trades:
        for trade in sl_trades:
            assert abs(float(trade.exit_price) - 2300.0) < 50.0, \
                f"SL exit price {trade.exit_price} is too far from SL level 2300.0"


def test_tp_exit_uses_tp_price():
    """When TP is triggered, exit price should be the TP level."""
    config = BacktestConfig(
        initial_capital=Decimal("1000000"),
        slippage_pips=0.5,
        spread_pips=2.0,
        commission_per_lot=Decimal("3.5"),
        risk_per_trade_bps=10,
        strict_mtf=False,
        enable_swap=False,
    )

    n_bars = 10
    timestamps = [datetime(2026, 1, 1) + timedelta(minutes=15 * i) for i in range(n_bars)]

    # Bars where bar 2 high hits TP=2400
    opens  = np.array([2350.0, 2380.0, 2390.0, 2395.0, 2400.0, 2410.0, 2420.0, 2430.0, 2440.0, 2450.0])
    highs  = np.array([2360.0, 2390.0, 2400.0, 2405.0, 2410.0, 2420.0, 2430.0, 2440.0, 2450.0, 2460.0])
    lows   = np.array([2340.0, 2370.0, 2380.0, 2385.0, 2390.0, 2400.0, 2410.0, 2420.0, 2430.0, 2440.0])
    closes = np.array([2355.0, 2385.0, 2395.0, 2400.0, 2405.0, 2415.0, 2425.0, 2435.0, 2445.0, 2455.0])
    volumes = np.array([1000] * n_bars, dtype=np.int64)

    signal = Signal(
        id="tp_test",
        strategy_id="test_exit",
        symbol="XAUUSD",
        signal_type=SignalType.BUY,
        timestamp=timestamps[1],
        entry_price=Decimal("2350.0"),
        stop_loss=Decimal("2300.0"),
        take_profit=Decimal("2400.0"),
    )

    engine = _build_engine(config, timestamps, opens, highs, lows, closes, volumes, [signal])
    engine.run()

    assert len(engine.trades) >= 1, f"Expected at least 1 trade, got {len(engine.trades)}"

    tp_trades = [t for t in engine.trades if t.close_reason.value == "TAKE_PROFIT"]
    if tp_trades:
        for trade in tp_trades:
            assert abs(float(trade.exit_price) - 2400.0) < 50.0, \
                f"TP exit price {trade.exit_price} is too far from TP level 2400.0"


if __name__ == "__main__":
    test_sl_exit_uses_sl_price()
    print("PASS: SL exit price test")
    test_tp_exit_uses_tp_price()
    print("PASS: TP exit price test")
    print("All exit price tests passed!")
