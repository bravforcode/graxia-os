"""
Run all 13 gold_bot strategies through BacktestEngine on real EURUSD data.
Reports trades, win rate, P&L for each strategy.
"""
import os

from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, List

from quant_os.backtest.engine import BacktestEngine, BacktestConfig
from quant_os.backtest.data_loader import load_csv_data
from quant_os.strategies.base import Strategy, Signal
from quant_os.core.enums import SignalType


class GoldStrategyAdapter(Strategy):
    """Wraps a gold_bot GoldStrategy to work with BacktestEngine."""

    def __init__(self, gold_strategy):
        super().__init__()
        self._gold = gold_strategy
        self.config.name = gold_strategy.name

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: Dict[str, List],
        indicators: Optional[Dict[str, Any]] = None,
        regime=None,
    ) -> Optional[Signal]:
        # Convert single-timeframe OHLCV to multi-timeframe format
        multi_data = {"M15": ohlcv_data, "H1": ohlcv_data, "H4": ohlcv_data}
        current_price = ohlcv_data["close"][-1] if ohlcv_data.get("close") else 0

        gs = self._gold.analyze(data=multi_data, current_price=current_price, symbol=symbol)
        if gs is None:
            return None

        # Convert gold_bot StrategySignal to quant_os Signal
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
            timeframe=gs.timeframe,
            notes=gs.reasoning,
        )

    def required_features(self) -> List[str]:
        return []


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


def load_strategy(name, module_path, class_name):
    """Dynamically import and instantiate a strategy"""
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


def run_all():
    # Load data
    csv_path = os.path.join("graxia", "packages", "quant_os", "data", "EURUSD_X.csv")
    print(f"Loading data from {csv_path}...")
    data, timestamps = load_csv_data(csv_path, date_column="Date", date_format="%Y-%m-%d %H:%M:%S%z")
    print(f"Loaded {len(data['close'])} bars")

    results = []

    for name, mod_path, cls_name in STRATEGY_MAP:
        print(f"\n{'='*60}")
        print(f"  Strategy: {name}")
        print(f"{'='*60}")

        try:
            gold_strat = load_strategy(name, mod_path, cls_name)
            adapter = GoldStrategyAdapter(gold_strat)

            config = BacktestConfig(
                initial_capital=10000.0,
                slippage_pips=0.5,
                commission_per_lot=3.5,
                risk_per_trade_pct=1.0,
            )

            engine = BacktestEngine(config)
            engine.set_strategy(adapter)
            engine.load_data(data, timestamps)
            bt_results = engine.run()

            metrics = bt_results["metrics"]
            trades = bt_results["trades"]

            print(f"  Trades: {metrics.total_trades}")
            print(f"  Win Rate: {metrics.win_rate*100:.1f}%")
            print(f"  Profit Factor: {metrics.profit_factor:.2f}")
            print(f"  Total P&L: ${metrics.total_pnl:+,.2f}")
            print(f"  Max DD: {metrics.max_drawdown_pct:.1f}%")
            print(f"  Sharpe: {metrics.sharpe_ratio:.2f}")
            print(f"  Long/Short: {metrics.long_trades}/{metrics.short_trades}")

            if trades:
                print(f"  Last 3 trades:")
                for t in trades[-3:]:
                    print(f"    {t['side']} entry={t['entry_price']:.5f} "
                          f"exit={t['exit_price']:.5f} pnl=${t['pnl']:+.2f}")

            results.append({
                "name": name,
                "trades": metrics.total_trades,
                "win_rate": metrics.win_rate,
                "profit_factor": metrics.profit_factor,
                "pnl": metrics.total_pnl,
                "max_dd": metrics.max_drawdown_pct,
                "sharpe": metrics.sharpe_ratio,
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"name": name, "trades": 0, "error": str(e)})

    # Summary table
    print("\n" + "=" * 80)
    print("  SUMMARY — All 13 Gold Bot Strategies on EURUSD")
    print("=" * 80)
    print(f"\n  {'Strategy':<20} {'Trades':<8} {'Win%':<8} {'PF':<8} {'P&L':<12} {'MaxDD':<8} {'Sharpe':<8}")
    print(f"  {'-'*72}")

    for r in sorted(results, key=lambda x: x.get("pnl", 0), reverse=True):
        if "error" in r:
            print(f"  {r['name']:<20} ERROR: {r['error'][:40]}")
        else:
            print(f"  {r['name']:<20} {r['trades']:<8} {r['win_rate']*100:<8.1f} "
                  f"{r['profit_factor']:<8.2f} ${r['pnl']:+<10.2f} {r['max_dd']:<8.1f} {r['sharpe']:<8.2f}")


if __name__ == "__main__":
    run_all()
