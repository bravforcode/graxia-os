"""Grid backtest smoke test — with unrealized mark-to-market tracking."""
import sys; sys.path.insert(0, '.')
sys.path.insert(0, 'strategies')
from scripts.edge_search_all import load_asset_data
from grid_strategy import GridConfig
from grid_backtest import run_grid_backtest

df = load_asset_data('XAUUSD')
ohlcv = {k: df[k].tolist() for k in ['open','high','low','close']}
n_total = len(df['close'])

configs = [
    ("Tight_10x1",   10, 1.0, 0.01),
    ("Tight_10x2",   10, 2.0, 0.01),
    ("Medium_20x1",  20, 1.0, 0.01),
    ("Medium_20x2",  20, 2.0, 0.01),
    ("Wide_30x2",    30, 2.0, 0.01),
    ("Dense_50x1",   50, 1.0, 0.01),
]

print(f"XAUUSD Grid | {n_total} bars | ~${ohlcv['close'][-1]:.0f}")
print(f"{'='*80}")
print(f"{'Config':<16} {'Fills':>6} {'Real':>9} {'Unreal':>9} {'Total':>9} {'MaxDD%':>7} {'Lots':>6} {'Eff%':>5}")
print(f"{'-'*80}")
for label, gc, am, ov in configs:
    cfg = GridConfig(symbol='XAUUSD', range_method='atr', atr_period=20,
                     atr_multiplier=am, grid_count=gc, order_volume=ov)
    r = run_grid_backtest(cfg, ohlcv)
    print(f"{label:<16} {r['grid_fills']:>6} {r['realized_pnl']:>9.1f} {r['unrealized_pnl']:>9.1f} {r['total_pnl']:>9.1f} {r['max_drawdown']*100:>6.2f}% {r['open_lots']:>6.2f} {r['range_efficiency']:>4.1f}%")