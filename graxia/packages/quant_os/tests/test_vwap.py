import sys, os
sys.path.insert(0, os.getcwd())
from graxia.packages.quant_os.backtest.data_loader import load_csv_data
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.gold_bot.strategy_adapter import GoldStrategyAdapter
from graxia.packages.quant_os.gold_bot.strategies.vwap_rejection import VWAPRejectionStrategy

csv_path = 'graxia/packages/quant_os/data/XAUUSD_D1.csv'
data_d1, ts_d1 = load_csv_data(csv_path, date_column='time', date_format='%Y-%m-%d %H:%M:%S%z')
data = {k: v[-200:] for k, v in data_d1.items()}
timestamps = ts_d1[-200:]

gold_strat = VWAPRejectionStrategy()
adapter = GoldStrategyAdapter(gold_strat)
config = BacktestConfig(initial_capital=10000, slippage_pips=0.5, commission_per_lot=3.5, risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3)
engine = BacktestEngine(config)
engine.set_strategy(adapter)
engine.load_data(data, timestamps)
r = engine.run()
print(f"Trades: {r['metrics'].total_trades}")
print(f"P&L: {r['metrics'].total_pnl}")

# Manual test: call analyze directly
nested = {tf: data for tf in ["M1", "M5", "M15", "H1", "H4", "D1"]}
price = data["close"][-1]
print(f"\nDirect analyze() test:")
sig = gold_strat.analyze(nested, price, "XAUUSD")
print(f"Signal: {sig}")
