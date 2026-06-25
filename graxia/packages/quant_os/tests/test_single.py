"""Single backtest run test — OrderBlock strategy on XAUUSD."""
import os
import time
import pytest

from graxia.packages.quant_os.backtest.data_loader import load_csv_data
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.gold_bot.strategy_adapter import GoldStrategyAdapter
from graxia.packages.quant_os.gold_bot.strategies.order_block import OrderBlockStrategy

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
FMT = "%Y-%m-%d %H:%M:%S"


def test_single_backtest():
    """Run OrderBlock strategy and verify metrics."""
    path = os.path.join(DATA_DIR, "XAUUSD_D1.csv")
    assert os.path.exists(path), f"Data file not found: {path}"

    d1, ts1 = load_csv_data(path, date_column="time", date_format=FMT)
    h1, _ = load_csv_data(os.path.join(DATA_DIR, "XAUUSD_H1.csv"), date_column="time", date_format=FMT)
    m15, _ = load_csv_data(os.path.join(DATA_DIR, "XAUUSD_M15.csv"), date_column="time", date_format=FMT)

    N = 200
    data_base = {k: v[-N:] for k, v in d1.items()}
    ts_base = ts1[-N:]
    multi_tf = {
        "D1": data_base,
        "H1": {k: v[-5000:] for k, v in h1.items()},
        "M15": {k: v[-20000:] for k, v in m15.items()},
    }

    config = BacktestConfig(
        strict_mtf=False,
        initial_capital=10000,
        slippage_pips=0.5,
        commission_per_lot=3.5,
    )

    gold_strat = OrderBlockStrategy()
    adapter = GoldStrategyAdapter(gold_strat, multi_tf_data=multi_tf)
    engine = BacktestEngine(config)
    engine.set_strategy(adapter)
    engine.load_data(data_base, ts_base)

    t0 = time.time()
    r = engine.run()
    elapsed = time.time() - t0

    m = r["metrics"]
    assert elapsed < 120.0, f"Backtest too slow: {elapsed:.1f}s"
    assert m.total_trades >= 0
    print(f"Run: {elapsed:.1f}s, Trades: {m.total_trades}, P&L: ${m.total_pnl:+,.2f}")
