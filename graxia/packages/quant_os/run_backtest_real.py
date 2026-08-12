"""Run backtest on real EURUSD data"""
import sys, os
sys.path.insert(0, os.getcwd())
os.chdir(os.getcwd())

from graxia.packages.quant_os.backtest.data_loader import load_csv_data
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.strategies.mtm import MultiTimeframeMomentum
from graxia.packages.quant_os.strategies.mrb import MeanReversionBollinger
from graxia.packages.quant_os.strategies.mlb import MLBreakout

data_dir = os.path.join("graxia", "packages", "quant_os", "data")
csv_path = os.path.join(data_dir, "EURUSD_X.csv")
full_data, full_timestamps = load_csv_data(csv_path, date_column="Date", date_format="%Y-%m-%d %H:%M:%S%z")

# Use last 500 bars for faster testing
data = {k: v[-500:] for k, v in full_data.items()}
timestamps = full_timestamps[-500:]

bars = len(data["close"])
print(f"Data: {bars} bars")
print(f"Date: {timestamps[0]} to {timestamps[-1]}")
print(f"Range: {min(data['close']):.5f} - {max(data['close']):.5f}")

config = BacktestConfig(
    initial_capital=10000,
    slippage_pips=0.5,
    commission_per_lot=3.5,
    risk_per_trade_pct=1.0,
    units_per_lot=100000,
    max_positions=3,
)

strategies = [
    ("MTM", MultiTimeframeMomentum),
    ("MRB", MeanReversionBollinger),
    ("MLB", MLBreakout),
]

for name, cls in strategies:
    print(f"\n--- {name} ---")
    strategy = cls()
    engine = BacktestEngine(config)
    engine.set_strategy(strategy)
    engine.load_data(data, timestamps)
    results = engine.run()
    m = results["metrics"]
    print(f"  Trades: {m.total_trades}")
    print(f"  Win Rate: {m.win_rate:.1%}")
    print(f"  Profit Factor: {m.profit_factor:.2f}")
    print(f"  Sharpe: {m.sharpe_ratio:.2f}")
    print(f"  Max DD: {m.max_drawdown_pct:.2f}%")
    print(f"  P&L: ${m.total_pnl:+,.2f}")
    print(f"  Expectancy: ${m.expectancy:+,.2f}")
