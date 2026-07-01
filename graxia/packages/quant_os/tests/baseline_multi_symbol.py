"""
Multi-symbol baseline: all 13 strategies on XAUUSD, EURUSD, GBPUSD.
MT5 real data, multi-TF, 200 D1 bars each.
"""
import os, time

from quant_os.backtest.data_loader import load_csv_data
from quant_os.backtest.engine import BacktestEngine, BacktestConfig
from quant_os.gold_bot.strategy_adapter import GoldStrategyAdapter

from quant_os.gold_bot.strategies.order_block import OrderBlockStrategy
from quant_os.gold_bot.strategies.supply_demand import SupplyDemandStrategy
from quant_os.gold_bot.strategies.ema_cross import EMACrossStrategy
from quant_os.gold_bot.strategies.rsi_divergence import RSIDivergenceStrategy
from quant_os.gold_bot.strategies.london_breakout import LondonBreakoutStrategy
from quant_os.gold_bot.strategies.fibonacci import FibonacciStrategy
from quant_os.gold_bot.strategies.vwap_rejection import VWAPRejectionStrategy
from quant_os.gold_bot.strategies.news_fade import NewsFadeStrategy
from quant_os.gold_bot.strategies.multi_tf_align import MultiTFAlignStrategy
from quant_os.gold_bot.strategies.bos_choch import BOSCHoCHStrategy
from quant_os.gold_bot.strategies.liquidity_sweep import LiquiditySweepStrategy
from quant_os.gold_bot.strategies.fair_value_gap import FairValueGapStrategy
from quant_os.gold_bot.strategies.opening_range import OpeningRangeStrategy

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
N = 200
config = BacktestConfig(
    initial_capital=10000, slippage_pips=0.5, commission_per_lot=3.5,
    risk_per_trade_pct=1.0, units_per_lot=100, max_positions=3,
)

symbols = ["XAUUSD", "EURUSD", "GBPUSD"]

for symbol in symbols:
    print(f"\n{'='*90}")
    print(f"  {symbol}")
    print(f"{'='*90}")

    # Load data
    t0 = time.time()
    d1, ts1 = load_csv_data(os.path.join(data_dir, f"{symbol}_D1.csv"), date_column="time", date_format=DATE_FMT)
    h1, tsh1 = load_csv_data(os.path.join(data_dir, f"{symbol}_H1.csv"), date_column="time", date_format=DATE_FMT)
    m15, tsm15 = load_csv_data(os.path.join(data_dir, f"{symbol}_M15.csv"), date_column="time", date_format=DATE_FMT)

    data_base = {k: v[-N:] for k, v in d1.items()}
    ts_base = ts1[-N:]

    multi_tf = {
        "D1": data_base,
        "H1": {k: v[-500:] for k, v in h1.items()},
        "M15": {k: v[-2000:] for k, v in m15.items()},
    }
    # Full arrays for cursor (ponytail: cursor slices per bar)
    h1_full = {k: v[-5000:] for k, v in h1.items()}
    ts_h1_full = tsh1[-5000:]
    m15_full = {k: v[-20000:] for k, v in m15.items()}
    ts_m15_full = tsm15[-20000:]
    print(f"  Data loaded in {time.time()-t0:.1f}s ({ts_base[0]} to {ts_base[-1]})")

    # Run strategies
    print(f"\n  {'Strategy':<20} {'Trades':>7} {'WR':>7} {'PF':>7} {'Sharpe':>7} {'P&L':>12}")
    print(f"  {'-'*65}")

    for name, cls in strategies:
        try:
            gold_strat = cls()
            adapter = GoldStrategyAdapter(gold_strat, multi_tf_data=multi_tf)
            engine = BacktestEngine(config)
            engine.set_strategy(adapter)
            engine.load_data(data_base, ts_base)
            # Wire MTF cursor for point-in-time slicing (no leakage)
            engine.set_multi_timeframe(h1_full, ts_h1_full, m15_full, ts_m15_full)
            r = engine.run()
            m = r["metrics"]

            print(f"  {name:<20} {m.total_trades:>7} {m.win_rate:>6.1%} {m.profit_factor:>7.2f} "
                  f"{m.sharpe_ratio:>7.2f} ${m.total_pnl:>+10,.2f}")
        except Exception as e:
            print(f"  {name:<20} ERROR: {e}")
