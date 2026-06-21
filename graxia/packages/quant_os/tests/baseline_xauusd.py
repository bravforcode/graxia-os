"""
Baseline backtest: All 13 gold_bot strategies on XAUUSD D1 real data.
No regime filter, no confluence — raw baseline.
"""
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

# Load D1 data
print("Loading XAUUSD D1 data...")
csv_path = os.path.join(data_dir, "XAUUSD_D1.csv")
data_d1, ts_d1 = load_csv_data(csv_path, date_column="time", date_format="%Y-%m-%d %H:%M:%S%z")
print(f"  D1: {len(data_d1['close'])} bars, {ts_d1[0]} to {ts_d1[-1]}")

# Use last 500 bars for quick verification
data = {k: v[-500:] for k, v in data_d1.items()}
timestamps = ts_d1[-500:]
print(f"  Using last {len(data['close'])} bars for backtest")

config = BacktestConfig(
    initial_capital=10000, slippage_pips=0.5, commission_per_lot=3.5,
    risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,
)

print(f"\n{'Strategy':<20} {'Trades':>7} {'WR':>7} {'PF':>7} {'Sharpe':>7} {'MaxDD':>8} {'P&L':>12}")
print("-" * 80)

results = []
sl_diagnostics = {}
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
        
        # Stop-loss distance diagnostic
        trades = r.get("trades", [])
        sl_dists = []
        for t in trades:
            entry = t["entry_price"]
            sl = t.get("stop_loss")
            if sl and sl > 0:
                sl_dists.append(abs(entry - sl))
        if sl_dists:
            sl_diagnostics[name] = {
                "count": len(sl_dists),
                "min": min(sl_dists),
                "max": max(sl_dists),
                "avg": sum(sl_dists) / len(sl_dists),
                "near_zero": sum(1 for d in sl_dists if d < 0.5),
            }
        
        trades_str = str(m.total_trades)
        wr_str = f"{m.win_rate:.1%}"
        pf_str = f"{m.profit_factor:.2f}"
        sharpe_str = f"{m.sharpe_ratio:.2f}"
        dd_str = f"{m.max_drawdown_pct:.2f}%"
        pnl_str = f"${m.total_pnl:+,.2f}"
        
        print(f"{name:<20} {trades_str:>7} {wr_str:>7} {pf_str:>7} {sharpe_str:>7} {dd_str:>8} {pnl_str:>12}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"{name:<20} ERROR: {e}")
        results.append((name, None))

# Summary
print(f"\n{'='*80}")
active = [(n, m) for n, m in results if m and m.total_trades > 0]
inactive = [(n, m) for n, m in results if m and m.total_trades == 0]
errors = [(n, m) for n, m in results if m is None]

print(f"Strategies with trades: {len(active)}/{len(results)}")
print(f"Strategies with 0 trades: {len(inactive)}")
print(f"Errors: {len(errors)}")

if active:
    print(f"\nActive strategies (sorted by P&L):")
    for n, m in sorted(active, key=lambda x: x[1].total_pnl, reverse=True):
        print(f"  {n}: {m.total_trades} trades, WR={m.win_rate:.1%}, P&L=${m.total_pnl:+,.2f}")

if inactive:
    print(f"\nInactive strategies (0 trades):")
    for n, m in inactive:
        print(f"  {n}")

# Stop-loss distance diagnostic
if sl_diagnostics:
    print(f"\n{'='*80}")
    print("STOP-LOSS DISTANCE DIAGNOSTIC (entry - stop_loss, in price units)")
    print(f"{'Strategy':<20} {'Count':>6} {'Min':>10} {'Max':>10} {'Avg':>10} {'<0.5':>7}")
    print("-" * 70)
    for name, d in sorted(sl_diagnostics.items()):
        print(f"{name:<20} {d['count']:>6} {d['min']:>10.2f} {d['max']:>10.2f} {d['avg']:>10.2f} {d['near_zero']:>7}")
