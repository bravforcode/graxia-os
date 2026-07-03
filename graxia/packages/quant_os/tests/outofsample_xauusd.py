"""
Out-of-sample backtest on XAUUSD data (bars 200-400) for all 13 gold_bot strategies.
"""

import importlib
import os
from decimal import Decimal
from typing import Any

from quant_os.backtest.data_loader import load_csv_data
from quant_os.backtest.engine import BacktestConfig, BacktestEngine
from quant_os.core.enums import SignalType
from quant_os.strategies.base import Signal, Strategy

DATA_DIR = os.path.join("graxia", "packages", "quant_os", "data")

STRATEGY_MAP = [
    ("order_block", "quant_os.gold_bot.strategies.order_block", "OrderBlockStrategy"),
    ("supply_demand", "quant_os.gold_bot.strategies.supply_demand", "SupplyDemandStrategy"),
    ("ema_cross", "quant_os.gold_bot.strategies.ema_cross", "EMACrossStrategy"),
    ("rsi_divergence", "quant_os.gold_bot.strategies.rsi_divergence", "RSIDivergenceStrategy"),
    ("london_breakout", "quant_os.gold_bot.strategies.london_breakout", "LondonBreakoutStrategy"),
    ("fibonacci", "quant_os.gold_bot.strategies.fibonacci", "FibonacciStrategy"),
    ("vwap_rejection", "quant_os.gold_bot.strategies.vwap_rejection", "VWAPRejectionStrategy"),
    ("news_fade", "quant_os.gold_bot.strategies.news_fade", "NewsFadeStrategy"),
    ("multi_tf_align", "quant_os.gold_bot.strategies.multi_tf_align", "MultiTFAlignStrategy"),
    ("bos_choch", "quant_os.gold_bot.strategies.bos_choch", "BOSCHoCHStrategy"),
    ("liquidity_sweep", "quant_os.gold_bot.strategies.liquidity_sweep", "LiquiditySweepStrategy"),
    ("fair_value_gap", "quant_os.gold_bot.strategies.fair_value_gap", "FairValueGapStrategy"),
    ("opening_range", "quant_os.gold_bot.strategies.opening_range", "OpeningRangeStrategy"),
]


class MultiTFAdapter(Strategy):
    """Wraps gold_bot GoldStrategy with real multi-TF data."""

    def __init__(self, gold_strategy, multi_tf_data: dict):
        super().__init__()
        self._gold = gold_strategy
        self.multi_tf_data = multi_tf_data
        self.config.name = gold_strategy.name

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
    ) -> Signal | None:
        nested = {}
        for tf in ["M1", "M5", "M15", "H1", "H4", "D1"]:
            nested[tf] = self.multi_tf_data.get(tf, ohlcv_data)

        current_price = ohlcv_data["close"][-1] if ohlcv_data.get("close") else 0
        gs = self._gold.analyze(data=nested, current_price=current_price, symbol=symbol)
        if gs is None:
            return None

        if gs.direction.value == "BUY":
            sig_type = SignalType.BUY
        elif gs.direction.value == "SELL":
            sig_type = SignalType.SELL
        else:
            return None

        self.signals_generated += 1
        return Signal.create(
            strategy_id=self.id,
            symbol=symbol,
            signal_type=sig_type,
            confidence=gs.confidence,
            entry_price=Decimal(str(gs.entry_price)) if gs.entry_price else None,
            stop_loss=Decimal(str(gs.stop_loss)) if gs.stop_loss else None,
            take_profit=Decimal(str(gs.take_profit)) if gs.take_profit else None,
        )

    def required_features(self) -> list[str]:
        return []


def load_strategy(name, module_path, class_name):
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


def main():
    print("Loading XAUUSD data...")
    d1_data, d1_ts = load_csv_data(
        os.path.join(DATA_DIR, "XAUUSD_D1.csv"),
        date_column="time",
        date_format="%Y-%m-%d %H:%M:%S",
    )
    h1_data, h1_ts = load_csv_data(
        os.path.join(DATA_DIR, "XAUUSD_H1.csv"),
        date_column="time",
        date_format="%Y-%m-%d %H:%M:%S",
    )
    m15_data, m15_ts = load_csv_data(
        os.path.join(DATA_DIR, "XAUUSD_M15.csv"),
        date_column="time",
        date_format="%Y-%m-%d %H:%M:%S",
    )
    print(f"  D1: {len(d1_data['close'])} bars | H1: {len(h1_data['close'])} bars | M15: {len(m15_data['close'])} bars")

    # Out-of-sample slice: bars 200-400 from D1
    oos_start, oos_end = 200, 400
    d1_oos = {k: v[oos_start:oos_end] for k, v in d1_data.items()}
    d1_oos_ts = d1_ts[oos_start:oos_end]

    # Multi-TF reference data (use latest bars, strategies read from these)
    multi_tf_ref = {
        "D1": d1_data,
        "H1": {k: v[-500:] for k, v in h1_data.items()},
        "M15": {k: v[-2000:] for k, v in m15_data.items()},
    }

    config = BacktestConfig(
        initial_capital=10000.0,
        slippage_pips=0.5,
        commission_per_lot=3.5,
        risk_per_trade_pct=1.0,
        units_per_lot=100.0,
        max_positions=3,
    )

    results = []
    sl_distances = []

    for name, mod_path, cls_name in STRATEGY_MAP:
        print(f"\n{'='*60}")
        print(f"  Strategy: {name}")
        print(f"{'='*60}")
        try:
            gold_strat = load_strategy(name, mod_path, cls_name)
            adapter = MultiTFAdapter(gold_strat, multi_tf_ref)

            engine = BacktestEngine(config)
            engine.set_strategy(adapter)
            engine.load_data(d1_oos, d1_oos_ts)
            bt = engine.run()

            m = bt["metrics"]
            trades = bt["trades"]

            # SL distance diagnostic
            sl_dists = []
            for t in trades:
                if t.get("stop_loss"):
                    sl_dists.append(abs(t["entry_price"] - t["stop_loss"]))
            if sl_dists:
                sl_distances.append((name, min(sl_dists), max(sl_dists), sum(sl_dists) / len(sl_dists)))

            results.append(
                {
                    "name": name,
                    "trades": m.total_trades,
                    "win_rate": m.win_rate,
                    "profit_factor": m.profit_factor,
                    "sharpe": m.sharpe_ratio,
                    "max_dd": m.max_drawdown_pct,
                    "pnl": m.total_pnl,
                }
            )

            print(
                f"  Trades: {m.total_trades}  WR: {m.win_rate*100:.1f}%  PF: {m.profit_factor:.2f}  "
                f"Sharpe: {m.sharpe_ratio:.2f}  MaxDD: {m.max_drawdown_pct:.1f}%  P&L: ${m.total_pnl:+,.2f}"
            )

        except Exception as e:
            import traceback

            traceback.print_exc()
            results.append({"name": name, "trades": 0, "error": str(e)})

    # Results table
    print("\n\n" + "=" * 90)
    print("  OUT-OF-SAMPLE RESULTS — XAUUSD D1 bars 200-400")
    print("=" * 90)
    print(f"\n  {'Strategy':<20} {'Trades':>7} {'WR%':>6} {'PF':>7} {'Sharpe':>7} {'MaxDD%':>7} {'P&L':>12}")
    print(f"  {'-'*80}")

    for r in sorted(results, key=lambda x: x.get("pnl", 0), reverse=True):
        if "error" in r:
            print(f"  {r['name']:<20} ERROR: {r['error'][:50]}")
        else:
            print(
                f"  {r['name']:<20} {r['trades']:>7} {r['win_rate']*100:>5.1f}% {r['profit_factor']:>7.2f} "
                f"{r['sharpe']:>7.2f} {r['max_dd']:>6.1f}% ${r['pnl']:>+10.2f}"
            )

    # SL distance diagnostic
    if sl_distances:
        print("\n\n  SL Distance Diagnostic (entry vs SL in price units):")
        print(f"  {'Strategy':<20} {'Min':>10} {'Max':>10} {'Avg':>10}")
        print(f"  {'-'*52}")
        for name, mn, mx, avg in sl_distances:
            print(f"  {name:<20} {mn:>10.2f} {mx:>10.2f} {avg:>10.2f}")

    # Sorted summary
    print("\n\n  SUMMARY (sorted by P&L):")
    print(f"  {'-'*52}")
    for r in sorted(results, key=lambda x: x.get("pnl", 0), reverse=True):
        if "error" not in r:
            print(f"  {r['name']:<20} P&L: ${r['pnl']:>+10.2f}  Trades: {r['trades']}")


if __name__ == "__main__":
    main()
