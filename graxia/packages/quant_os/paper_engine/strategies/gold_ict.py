"""
Gold ICT Strategies — wraps gold_bot order-flow/ICT strategies for paper_engine.

Each wrapper iterates bar-by-bar, passing point-in-time data to the gold_bot
strategy's analyze() method. The same OHLCV data is passed for all timeframe
keys (honest single-TF adaptation — no look-ahead).

Strategies wrapped:
  - order_block: ICT Order Block on H1
  - fair_value_gap: ICT Fair Value Gap on M15
  - liquidity_sweep: ICT Liquidity Sweep on M15
  - bos_choch: Break of Structure / Change of Character on M15
  - multi_tf_align: Multi-timeframe EMA alignment
  - london_breakout: London session breakout on M15
  - news_fade: News spike fade on M1
  - vwap_rejection: VWAP rejection on M15
  - fibonacci: Fibonacci retracement on H1
  - rsi_divergence: RSI divergence on M15
  - ema_cross: EMA 9/21 crossover on M15
  - supply_demand: Supply/demand zones on M15
  - opening_range: Opening range breakout on M5
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseStrategy, Signal, StrategyResult

# Batch signal generators (O(n) vectorized — 100x faster than bar-by-bar)
_batch_registry = {}
try:
    from .gold_ict_batch import BATCH_REGISTRY as _batch_registry
except ImportError:
    pass

# Gold bot strategy imports (lazy — may not be installed)
_gold_bot_available = False
try:
    from graxia.packages.quant_os.gold_bot.strategies.order_block import OrderBlockStrategy
    from graxia.packages.quant_os.gold_bot.strategies.fair_value_gap import FairValueGapStrategy
    from graxia.packages.quant_os.gold_bot.strategies.liquidity_sweep import LiquiditySweepStrategy
    from graxia.packages.quant_os.gold_bot.strategies.bos_choch import BOSCHoCHStrategy
    from graxia.packages.quant_os.gold_bot.strategies.multi_tf_align import MultiTFAlignStrategy
    from graxia.packages.quant_os.gold_bot.strategies.london_breakout import LondonBreakoutStrategy
    from graxia.packages.quant_os.gold_bot.strategies.news_fade import NewsFadeStrategy
    from graxia.packages.quant_os.gold_bot.strategies.vwap_rejection import VWAPRejectionStrategy
    from graxia.packages.quant_os.gold_bot.strategies.fibonacci import FibonacciStrategy
    from graxia.packages.quant_os.gold_bot.strategies.rsi_divergence import RSIDivergenceStrategy
    from graxia.packages.quant_os.gold_bot.strategies.ema_cross import EMACrossStrategy
    from graxia.packages.quant_os.gold_bot.strategies.supply_demand import SupplyDemandStrategy
    from graxia.packages.quant_os.gold_bot.strategies.opening_range import OpeningRangeStrategy
    from graxia.packages.quant_os.gold_bot.core.engine import SignalDirection
    _gold_bot_available = True
except ImportError:
    pass


class _GoldICTWrapper(BaseStrategy):
    """Generic wrapper for a single gold_bot strategy."""

    # Subclasses override these — use string name to avoid import-time failure
    _gold_strategy_name = ""
    _strategy_name = ""
    _primary_tf = "M15"
    _timeframes: list[str] = []
    _min_bars = 50

    def __init__(self):
        super().__init__(self._strategy_name)

    def generate_signals(self, df: pd.DataFrame, params: dict) -> StrategyResult:
        # ── Fast path: vectorized batch generator (O(n)) ──
        batch_fn = _batch_registry.get(self._strategy_name)
        if batch_fn is not None:
            return self._generate_signals_batch(df, params, batch_fn)

        # ── Slow path: bar-by-bar gold_bot (O(n²)) ──
        return self._generate_signals_bar(df, params)

    def _generate_signals_batch(self, df: pd.DataFrame, params: dict, batch_fn) -> StrategyResult:
        """Fast O(n) path using vectorized batch signal generator."""
        import inspect
        min_bars = params.get("min_bars", self._min_bars)
        close = df["close"].values.astype(float)
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        vol = df["volume"].values.astype(float) if "volume" in df.columns else None

        sig = inspect.signature(batch_fn)
        kwargs = {"close": close, "high": high, "low": low}
        if "volume" in sig.parameters and vol is not None:
            kwargs["volume"] = vol
        result = batch_fn(**kwargs)
        n = len(close)
        signals = []

        for i in range(min_bars, n):
            d = result.directions[i]
            if d == 0:
                continue
            score = int(result.scores[i])
            confidence = score / 100.0
            if confidence < 0.5:
                continue
            signals.append(Signal(
                timestamp=str(df.index[i]),
                direction=int(d),
                confidence=round(confidence, 3),
                entry_price=round(close[i], 5),
                stop_loss=round(result.sl[i], 5) if result.sl[i] > 0 else None,
                take_profit=round(result.tp[i], 5) if result.tp[i] > 0 else None,
                reason=f"{self._strategy_name} batch signal",
                bar_index=i,
            ))

        return StrategyResult(signals=signals, metrics={
            "strategy": self._strategy_name,
            "min_bars": min_bars,
            "path": "batch",
        })

    def _generate_signals_bar(self, df: pd.DataFrame, params: dict) -> StrategyResult:
        if not _gold_bot_available:
            return StrategyResult(signals=[], metrics={"strategy": self._strategy_name, "error": "gold_bot not installed"})

        # Lookup strategy class by name from the module-level imports
        _STRAT_MAP = {
            "OrderBlockStrategy": OrderBlockStrategy,
            "FairValueGapStrategy": FairValueGapStrategy,
            "LiquiditySweepStrategy": LiquiditySweepStrategy,
            "BOSCHoCHStrategy": BOSCHoCHStrategy,
            "MultiTFAlignStrategy": MultiTFAlignStrategy,
            "LondonBreakoutStrategy": LondonBreakoutStrategy,
            "NewsFadeStrategy": NewsFadeStrategy,
            "VWAPRejectionStrategy": VWAPRejectionStrategy,
            "FibonacciStrategy": FibonacciStrategy,
            "RSIDivergenceStrategy": RSIDivergenceStrategy,
            "EMACrossStrategy": EMACrossStrategy,
            "SupplyDemandStrategy": SupplyDemandStrategy,
            "OpeningRangeStrategy": OpeningRangeStrategy,
        }
        gold_cls = _STRAT_MAP.get(self._gold_strategy_name)
        if gold_cls is None:
            return StrategyResult(signals=[], metrics={"strategy": self._strategy_name, "error": f"class {self._gold_strategy_name} not found"})

        # Configurable minimum bars (allows param search)
        min_bars = params.get("min_bars", self._min_bars)

        # Pre-extract numpy arrays ONCE (no per-bar .tolist() allocation)
        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        vols = df["volume"].values.astype(float) if "volume" in df.columns else np.ones(len(df))
        n = len(closes)

        # Pre-build the data template dict — reuse same structure, swap array views
        tfs = self._timeframes

        gold_strat = gold_cls()
        symbol = params.get("symbol", "XAUUSD")
        signals = []

        for i in range(min_bars, n):
            current_price = closes[i]
            # Pass numpy views (slices are O(1) views, no copy/tolist)
            end = i + 1
            tf_data = {
                "close": closes[:end],
                "high": highs[:end],
                "low": lows[:end],
                "volume": vols[:end],
            }
            data = {tf: tf_data for tf in tfs}

            try:
                result = gold_strat.analyze(data, current_price, symbol=symbol)
            except Exception:
                continue

            if result is None:
                continue

            # Convert direction
            if result.direction == SignalDirection.BUY:
                direction = 1
            elif result.direction == SignalDirection.SELL:
                direction = -1
            else:
                continue

            # Convert score (0-100) → confidence (0.0-1.0)
            confidence = result.score / 100.0

            if confidence < 0.5:
                continue

            signals.append(Signal(
                timestamp=str(df.index[i]),
                direction=direction,
                confidence=round(confidence, 3),
                entry_price=round(current_price, 5),
                stop_loss=round(result.stop_loss, 5) if result.stop_loss else None,
                take_profit=round(result.take_profit, 5) if result.take_profit else None,
                reason=result.reasoning,
                bar_index=i,
            ))

        return StrategyResult(signals=signals, metrics={
            "strategy": self._strategy_name,
            "min_bars": min_bars,
        })


# ── Concrete wrapper classes ──────────────────────────────────────────────


class OrderBlockWrapper(_GoldICTWrapper):
    _gold_strategy_name = "OrderBlockStrategy"
    _strategy_name = "gi_order_block"
    _primary_tf = "H1"
    _timeframes = ["M15", "H1", "H4"]
    _min_bars = 60


class FairValueGapWrapper(_GoldICTWrapper):
    _gold_strategy_name = "FairValueGapStrategy"
    _strategy_name = "gi_fair_value_gap"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 30


class LiquiditySweepWrapper(_GoldICTWrapper):
    _gold_strategy_name = "LiquiditySweepStrategy"
    _strategy_name = "gi_liquidity_sweep"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 35


class BOSCHoCHWrapper(_GoldICTWrapper):
    _gold_strategy_name = "BOSCHoCHStrategy"
    _strategy_name = "gi_bos_choch"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 35


class MultiTFAlignWrapper(_GoldICTWrapper):
    _gold_strategy_name = "MultiTFAlignStrategy"
    _strategy_name = "gi_multi_tf_align"
    _primary_tf = "M15"
    _timeframes = ["M15", "H1", "H4"]
    _min_bars = 60


class LondonBreakoutWrapper(_GoldICTWrapper):
    _gold_strategy_name = "LondonBreakoutStrategy"
    _strategy_name = "gi_london_breakout"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 30


class NewsFadeWrapper(_GoldICTWrapper):
    _gold_strategy_name = "NewsFadeStrategy"
    _strategy_name = "gi_news_fade"
    _primary_tf = "M1"
    _timeframes = ["M1"]
    _min_bars = 35


class VWAPRejectionWrapper(_GoldICTWrapper):
    _gold_strategy_name = "VWAPRejectionStrategy"
    _strategy_name = "gi_vwap_rejection"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 30


class FibonacciWrapper(_GoldICTWrapper):
    _gold_strategy_name = "FibonacciStrategy"
    _strategy_name = "gi_fibonacci"
    _primary_tf = "H1"
    _timeframes = ["H1"]
    _min_bars = 60


class RSIDivergenceWrapper(_GoldICTWrapper):
    _gold_strategy_name = "RSIDivergenceStrategy"
    _strategy_name = "gi_rsi_divergence"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 35


class EMACrossWrapper(_GoldICTWrapper):
    _gold_strategy_name = "EMACrossStrategy"
    _strategy_name = "gi_ema_cross"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 60


class SupplyDemandWrapper(_GoldICTWrapper):
    _gold_strategy_name = "SupplyDemandStrategy"
    _strategy_name = "gi_supply_demand"
    _primary_tf = "M15"
    _timeframes = ["M15"]
    _min_bars = 60


class OpeningRangeWrapper(_GoldICTWrapper):
    _gold_strategy_name = "OpeningRangeStrategy"
    _strategy_name = "gi_opening_range"
    _primary_tf = "M5"
    _timeframes = ["M5"]
    _min_bars = 20


# ── Registry (maps strategy_id → class) ─────────────────────────────────

GOLD_ICT_REGISTRY: dict[str, type[_GoldICTWrapper]] = {
    "gi_order_block": OrderBlockWrapper,
    "gi_fair_value_gap": FairValueGapWrapper,
    "gi_liquidity_sweep": LiquiditySweepWrapper,
    "gi_bos_choch": BOSCHoCHWrapper,
    "gi_multi_tf_align": MultiTFAlignWrapper,
    "gi_london_breakout": LondonBreakoutWrapper,
    "gi_news_fade": NewsFadeWrapper,
    "gi_vwap_rejection": VWAPRejectionWrapper,
    "gi_fibonacci": FibonacciWrapper,
    "gi_rsi_divergence": RSIDivergenceWrapper,
    "gi_ema_cross": EMACrossWrapper,
    "gi_supply_demand": SupplyDemandWrapper,
    "gi_opening_range": OpeningRangeWrapper,
}
