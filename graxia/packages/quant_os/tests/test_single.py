import sys, os, time
sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.backtest.data_loader import load_csv_data
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.gold_bot.strategy_adapter import GoldStrategyAdapter
from graxia.packages.quant_os.gold_bot.strategies.order_block import OrderBlockStrategy

data_dir = os.path.join("graxia", "packages", "quant_os", "data")
fmt = "%Y-%m-%d %H:%M:%S"

d1, ts1 = load_csv_data(os.path.join(data_dir, "XAUUSD_D1.csv"), date_column="time", date_format=fmt)
h1, tsh1 = load_csv_data(os.path.join(data_dir, "XAUUSD_H1.csv"), date_column="time", date_format=fmt)
m15, tsm15 = load_csv_data(os.path.join(data_dir, "XAUUSD_M15.csv"), date_column="time", date_format=fmt)

N = 200
data_base = {k: v[-N:] for k, v in d1.items()}
ts_base = ts1[-N:]

multi_tf = {
    "D1": data_base,
    "H1": {k: v[-5000:] for k, v in h1.items()},
    "M15": {k: v[-20000:] for k, v in m15.items()},
}

config = BacktestConfig(
    initial_capital=10000, slippage_pips=0.5, commission_per_lot=3.5,
    risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,
)

gold_strat = OrderBlockStrategy()
adapter = GoldStrategyAdapter(gold_strat, multi_tf_data=multi_tf)
engine = BacktestEngine(config)
engine.set_strategy(adapter)

t0 = time.time()
engine.load_data(data_base, ts_base)
print(f"Load data: {time.time()-t0:.1f}s")

t0 = time.time()
r = engine.run()
elapsed = time.time() - t0
m = r["metrics"]
print(f"Run: {elapsed:.1f}s, Trades: {m.total_trades}, P&L: ${m.total_pnl:+,.2f}")
