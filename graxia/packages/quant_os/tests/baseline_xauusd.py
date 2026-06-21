"""
Baseline backtest: All 13 gold_bot strategies on XAUUSD.
MT5 real data: D1 (backtest base), H1 + M15 (available to strategies).
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
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Load all three timeframes from MT5
print("Loading MT5 data...")
csv_d1 = os.path.join(data_dir, "XAUUSD_D1.csv")
csv_h1 = os.path.join(data_dir, "XAUUSD_H1.csv")
csv_m15 = os.path.join(data_dir, "XAUUSD_M15.csv")

data_d1, ts_d1 = load_csv_data(csv_d1, date_column="time", date_format=DATE_FMT)
data_h1, ts_h1 = load_csv_data(csv_h1, date_column="time", date_format=DATE_FMT)
data_m15, ts_m15 = load_csv_data(csv_m15, date_column="time", date_format=DATE_FMT)

print(f"  D1: {len(data_d1['close'])} bars, {ts_d1[0]} to {ts_d1[-1]}")
print(f"  H1: {len(data_h1['close'])} bars, {ts_h1[0]} to {ts_h1[-1]}")
print(f"  M15: {len(data_m15['close'])} bars, {ts_m15[0]} to {ts_m15[-1]}")

# Use last 200 D1 bars for backtest
N = 200
data_base = {k: v[-N:] for k, v in data_d1.items()}
ts_base = ts_d1[-N:]
print(f"\nBacktest: last {N} D1 bars ({ts_base[0]} to {ts_base[-1]})")

# Build multi-TF dict (small enough for in-memory strategy access)
multi_tf = {
    "D1": data_base,
    "H1": {k: v[-500:] for k, v in data_h1.items()},
    "M15": {k: v[-2000:] for k, v in data_m15.items()},
}
print(f"  Multi-TF: H1={len(multi_tf['H1']['close'])} bars, M15={len(multi_tf['M15']['close'])} bars")

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
        adapter = GoldStrategyAdapter(gold_strat, multi_tf_data=multi_tf)
        engine = BacktestEngine(config)
        engine.set_strategy(adapter)
        engine.load_data(data_base, ts_base)
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
