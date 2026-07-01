import os, time
from decimal import Decimal

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

data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
fmt = "%Y-%m-%d %H:%M:%S"

xau_d1 = os.path.join(data_dir, "XAUUSD_D1.csv")
if not os.path.exists(xau_d1):
    raise ImportError(f"Data file not found: {xau_d1}")

d1, ts1 = load_csv_data(xau_d1, date_column="time", date_format=fmt)

N = 100
data_base = {k: v[-N:] for k, v in d1.items()}
ts_base = ts1[-N:]

config = BacktestConfig(strict_mtf=False,
    initial_capital=Decimal("10000"), slippage_pips=0.5, commission_per_lot=Decimal("3.5"),
)

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

# NO multi-TF data — just D1
for name, cls in strategies:
    t0 = time.time()
    gold_strat = cls()
    adapter = GoldStrategyAdapter(gold_strat)
    engine = BacktestEngine(config)
    engine.set_strategy(adapter)
    engine.load_data(data_base, ts_base)
    r = engine.run()
    elapsed = time.time() - t0
    m = r["metrics"]
    print(f"{name:<20} {elapsed:>6.1f}s  trades={m.total_trades}  P&L=${m.total_pnl:+,.2f}")
