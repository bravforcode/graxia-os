import sys, os
sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.backtest.data_loader import load_csv_data
from graxia.packages.quant_os.backtest.engine import BacktestEngine, BacktestConfig
from graxia.packages.quant_os.gold_bot.strategy_adapter import GoldStrategyAdapter

from graxia.packages.quant_os.gold_bot.strategies.order_block import OrderBlockStrategy
from graxia.packages.quant_os.gold_bot.strategies.supply_demand import SupplyDemandStrategy
from graxia.packages.quant_os.gold_bot.strategies.ema_cross import EMACrossStrategy
from graxia.packages.quant_os.gold_bot.strategies.rsi_divergence import RSIDivergenceStrategy
from graxia.packages.quant_os.gold_bot.strategies.london_breakout import LondonBreakoutStrategy
from graxia.packages.quant_os.gold_bot.strategies.fibonacci import FibonacciStrategy
from graxia.packages.quant_os.gold_bot.strategies.vwap_rejection import VWAPRejectionStrategy
from graxia.packages.quant_os.gold_bot.strategies.news_fade import NewsFadeStrategy
from graxia.packages.quant_os.gold_bot.strategies.multi_tf_align import MultiTFAlignStrategy
from graxia.packages.quant_os.gold_bot.strategies.bos_choch import BOSCHoCHStrategy
from graxia.packages.quant_os.gold_bot.strategies.liquidity_sweep import LiquiditySweepStrategy
from graxia.packages.quant_os.gold_bot.strategies.fair_value_gap import FairValueGapStrategy
from graxia.packages.quant_os.gold_bot.strategies.opening_range import OpeningRangeStrategy

strategies = [
    ("order_block", OrderBlockStrategy),
    ("supply_demand", SupplyDemandStrategy),
    ("ema_cross", EMACrossStrategy),
    ("rsi_divergence", RSIDivergenceStrategy),
    ("london_breakout", LondonBreakoutStrategy),
    ("fibonacci", FibonacciStrategy),
    ("vwap_rejection", VWAPRejectionStrategy),
    ("news_fade", NewsFadeStrategy),
    ("multi_tf_align", MultiTFAlignStrategy),
    ("bos_choch", BOSCHoCHStrategy),
    ("liquidity_sweep", LiquiditySweepStrategy),
    ("fair_value_gap", FairValueGapStrategy),
    ("opening_range", OpeningRangeStrategy),
]

data_dir = os.path.join("graxia", "packages", "quant_os", "data")
csv_path = os.path.join(data_dir, "EURUSD_X.csv")
full_data, full_ts = load_csv_data(csv_path, date_column="Date", date_format="%Y-%m-%d %H:%M:%S%z")
data = {k: v[-500:] for k, v in full_data.items()}
timestamps = full_ts[-500:]

print(f"Data: {len(data['close'])} bars, {timestamps[0]} to {timestamps[-1]}")

config = BacktestConfig(initial_capital=10000, slippage_pips=0.5, commission_per_lot=3.5,
                        risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3)

results = []
for name, cls in strategies:
    try:
        gold_strat = cls()
        adapter = GoldStrategyAdapter(gold_strat)
        engine = BacktestEngine(config)
        engine.set_strategy(adapter)
        engine.load_data(data, timestamps)
        r = engine.run()
        m = r["metrics"]
        results.append((name, m))
        print(f"{name:<20} Trades={m.total_trades:>3}  WR={m.win_rate:>6.1%}  PF={m.profit_factor:>6.2f}  Sharpe={m.sharpe_ratio:>6.2f}  MaxDD={m.max_drawdown_pct:>6.2f}%  P&L=${m.total_pnl:>+10,.2f}")
    except Exception as e:
        print(f"{name:<20} ERROR: {e}")
        results.append((name, None))

print(f"\n{'='*80}")
active = [(n, m) for n, m in results if m and m.total_trades > 0]
print(f"Strategies with trades: {len(active)}/{len(results)}")
for n, m in sorted(active, key=lambda x: x[1].total_pnl, reverse=True):
    print(f"  {n}: {m.total_trades} trades, P&L ${m.total_pnl:+,.2f}")
