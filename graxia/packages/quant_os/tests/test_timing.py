import sys, os, time
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

if __name__ == "__main__":
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

    config = BacktestConfig(strict_mtf=False,
        initial_capital=10000, slippage_pips=0.5, commission_per_lot=3.5,
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

    for name, cls in strategies:
        t0 = time.time()
        gold_strat = cls()
        adapter = GoldStrategyAdapter(gold_strat, multi_tf_data=multi_tf)
        engine = BacktestEngine(config)
        engine.set_strategy(adapter)
        engine.load_data(data_base, ts_base)
        r = engine.run()
        elapsed = time.time() - t0
        m = r["metrics"]
        print(f"{name:<20} {elapsed:>6.1f}s  trades={m.total_trades}  P&L=${m.total_pnl:+,.2f}")
