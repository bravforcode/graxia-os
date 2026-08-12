"""
Alpha Engine — strategy routing, signal aggregation, and conviction scoring.

Routes market data to asset-class-specific strategies, aggregates signals
from multiple agreeing strategies, and applies regime gating to filter
low-conviction or regime-incompatible signals.

Only signals with aggregated conviction > 0.6 are emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Protocol

import structlog

from ..core.signal_gateway import AssetClass, Signal, SignalSource, Side

logger = structlog.get_logger(__name__)

CONVICTION_THRESHOLD: float = 0.60


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class StrategyCallable(Protocol):
    """Protocol for a strategy function or callable.

    Each strategy receives (data, symbol) and returns a list of raw signal
    dicts with keys: side, conviction, entry_price, stop_loss, take_profit,
    strategy, regime, metadata.
    """

    def __call__(
        self, data: Dict[str, Any], symbol: str
    ) -> List[Dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Signal Scorer
# ---------------------------------------------------------------------------


@dataclass
class ScoredSignal:
    """Result of scoring a cluster of agreeing strategy outputs."""

    side: str
    conviction: float
    strategies: List[str]
    entry_price: float
    stop_loss: float
    take_profit: float
    regime: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SignalScorer:
    """Aggregate conviction from multiple strategies that agree on direction.

    Scoring algorithm:
    1. Group raw signals by side (BUY / SELL).
    2. For the dominant side, compute weighted-average conviction where
       each strategy gets equal weight.
    3. Apply a consensus bonus: more agreeing strategies → higher conviction.
    4. Return the scored signal only if conviction > CONVICTION_THRESHOLD.
    """

    CONSENSUS_BONUS_PER_STRATEGY: float = 0.03
    MAX_CONSENSUS_BONUS: float = 0.12

    def score(self, raw_signals: List[Dict[str, Any]]) -> Optional[ScoredSignal]:
        """Score a list of raw signals. Returns None if no actionable signal."""
        if not raw_signals:
            return None

        # Group by side
        buy_signals: List[Dict[str, Any]] = []
        sell_signals: List[Dict[str, Any]] = []

        for sig in raw_signals:
            side = sig.get("side", "").upper()
            if side == "BUY":
                buy_signals.append(sig)
            elif side == "SELL":
                sell_signals.append(sig)

        # Pick dominant side
        if len(buy_signals) > len(sell_signals):
            dominant = buy_signals
            side = "BUY"
        elif len(sell_signals) > len(buy_signals):
            dominant = sell_signals
            side = "SELL"
        elif buy_signals and sell_signals:
            # Equal split — abstain
            return None
        else:
            return None

        if not dominant:
            return None

        # Average conviction
        avg_conviction = sum(s.get("conviction", 0.5) for s in dominant) / len(dominant)

        # Consensus bonus
        n = len(dominant)
        bonus = min(self.CONSENSUS_BONUS_PER_STRATEGY * (n - 1), self.MAX_CONSENSUS_BONUS)
        final_conviction = min(avg_conviction + bonus, 1.0)

        if final_conviction < CONVICTION_THRESHOLD:
            return None

        # Consensus entry/SL/TP (median of agreeing signals)
        entry_prices = [s["entry_price"] for s in dominant if "entry_price" in s]
        stop_losses = [s["stop_loss"] for s in dominant if "stop_loss" in s]
        take_profits = [s["take_profit"] for s in dominant if "take_profit" in s]

        def _median(values: List[float]) -> float:
            s = sorted(values)
            n = len(s)
            if n == 0:
                return 0.0
            mid = n // 2
            return (s[mid] + s[mid - 1]) / 2 if n % 2 == 0 else s[mid]

        # Merge metadata
        merged_meta: Dict[str, Any] = {}
        for s in dominant:
            merged_meta.update(s.get("metadata", {}))

        # Pick regime from first signal that has one
        regime = next((s.get("regime") for s in dominant if s.get("regime")), None)

        return ScoredSignal(
            side=side,
            conviction=round(final_conviction, 4),
            strategies=[s.get("strategy", "unknown") for s in dominant],
            entry_price=_median(entry_prices),
            stop_loss=_median(stop_losses),
            take_profit=_median(take_profits),
            regime=regime,
            metadata=merged_meta,
        )


# ---------------------------------------------------------------------------
# Strategy Router
# ---------------------------------------------------------------------------


class StrategyRouter:
    """Maps asset_class to a list of strategy callables.

    Strategies are registered per asset class. The router calls each
    strategy with the market data and collects raw signal dicts.
    """

    def __init__(self) -> None:
        self._strategies: Dict[AssetClass, List[StrategyCallable]] = {
            AssetClass.METALS: [],
            AssetClass.CRYPTO: [],
            AssetClass.FOREX: [],
            AssetClass.INDICES: [],
        }

    def register(self, asset_class: AssetClass, strategy: StrategyCallable) -> None:
        """Register a strategy for an asset class."""
        self._strategies[asset_class].append(strategy)

    def register_many(
        self, asset_class: AssetClass, strategies: List[StrategyCallable]
    ) -> None:
        """Register multiple strategies for an asset class."""
        self._strategies[asset_class].extend(strategies)

    def get_strategies(self, asset_class: AssetClass) -> List[StrategyCallable]:
        """Return registered strategies for an asset class."""
        return self._strategies.get(asset_class, [])

    def route(
        self, data: Dict[str, Any], symbol: str, asset_class: AssetClass
    ) -> List[Dict[str, Any]]:
        """Run all strategies for the given asset class and collect signals."""
        strategies = self._strategies.get(asset_class, [])
        if not strategies:
            logger.warning(
                "alpha_engine.no_strategies",
                asset_class=asset_class.value,
                symbol=symbol,
            )
            return []

        all_signals: List[Dict[str, Any]] = []
        for strategy in strategies:
            try:
                signals = strategy(data, symbol)
                if signals:
                    all_signals.extend(signals)
            except NotImplementedError:
                logger.info(
                    "alpha_engine.strategy_not_implemented",
                    strategy=strategy.__name__ if hasattr(strategy, "__name__") else str(strategy),
                    asset_class=asset_class.value,
                )
            except Exception:
                logger.exception(
                    "alpha_engine.strategy_error",
                    strategy=strategy.__name__ if hasattr(strategy, "__name__") else str(strategy),
                )

        return all_signals


# ---------------------------------------------------------------------------
# Alpha Engine
# ---------------------------------------------------------------------------


class AlphaEngine:
    """Top-level alpha engine.

    Responsibilities:
    - Route market data to asset-class-specific strategies via StrategyRouter.
    - Aggregate conviction from multiple agreeing strategies via SignalScorer.
    - Apply regime gating (skip signals incompatible with current regime).
    - Emit only signals with conviction > CONVICTION_THRESHOLD.

    Usage:
        engine = AlphaEngine()
        engine.router.register(AssetClass.METALS, my_gold_strategy)
        signals = engine.analyze(data, "XAUUSD", AssetClass.METALS)
    """

    def __init__(
        self,
        router: Optional[StrategyRouter] = None,
        scorer: Optional[SignalScorer] = None,
    ) -> None:
        self.router = router or StrategyRouter()
        self.scorer = scorer or SignalScorer()
        self._regime_detector: Optional[Any] = None  # lazy import

    @property
    def regime_detector(self) -> Any:
        """Lazy-load the RegimeDetector singleton."""
        if self._regime_detector is None:
            from .regime_detector import RegimeDetector
            self._regime_detector = RegimeDetector()
        return self._regime_detector

    def analyze(
        self,
        data: Dict[str, Any],
        symbol: str,
        asset_class: AssetClass,
    ) -> List[Signal]:
        """Analyze market data and return high-conviction signals.

        Args:
            data: Market data dict with OHLCV arrays and optional indicators.
            symbol: Trading symbol (e.g. "XAUUSD").
            asset_class: Asset class for strategy routing.

        Returns:
            List of Signal objects with conviction > 0.6, regime-gated.
        """
        # 1. Detect regime
        regime = self._detect_regime(data, asset_class)

        # 2. Route to strategies
        raw_signals = self.router.route(data, symbol, asset_class)

        if not raw_signals:
            return []

        # 3. Score and aggregate
        scored = self.scorer.score(raw_signals)
        if scored is None:
            return []

        # 4. Regime gating
        if not self._is_regime_compatible(scored, regime, asset_class):
            logger.info(
                "alpha_engine.regime_gated",
                symbol=symbol,
                regime=regime,
                side=scored.side,
                conviction=scored.conviction,
            )
            return []

        # 5. Build Signal
        signal = Signal(
            symbol=symbol,
            asset_class=asset_class,
            side=Side(scored.side),
            conviction=scored.conviction,
            strategy="+".join(scored.strategies),
            entry_price=scored.entry_price,
            stop_loss=scored.stop_loss,
            take_profit=scored.take_profit,
            timestamp=datetime.now(UTC),
            source=SignalSource.PYTHON,
            regime=regime,
            metadata={
                **scored.metadata,
                "strategies_count": len(scored.strategies),
                "scorer": "SignalScorer",
            },
        )

        logger.info(
            "alpha_engine.signal_emitted",
            signal_id=signal.signal_id,
            symbol=symbol,
            side=scored.side,
            conviction=scored.conviction,
            strategies=scored.strategies,
            regime=regime,
        )

        return [signal]

    # ------------------------------------------------------------------
    # Regime detection
    # ------------------------------------------------------------------

    def _detect_regime(self, data: Dict[str, Any], asset_class: AssetClass) -> str:
        """Detect current market regime for the given asset class."""
        try:
            return self.regime_detector.detect(data, asset_class)
        except Exception:
            logger.exception("alpha_engine.regime_detection_error")
            return "UNKNOWN"

    def _is_regime_compatible(
        self,
        scored: ScoredSignal,
        regime: str,
        asset_class: AssetClass,
    ) -> bool:
        """Check if a signal is compatible with the detected regime.

        Uses RegimeDetector.get_allowed_strategies to filter.
        """
        if regime == "UNKNOWN":
            return True  # allow if detection failed

        try:
            allowed = self.regime_detector.get_allowed_strategies(regime, asset_class)
            if not allowed:
                return True  # no filter defined → allow
            # Check if any of the scoring strategies are allowed
            for strat in scored.strategies:
                strat_lower = strat.lower()
                for a in allowed:
                    if a.lower() in strat_lower or strat_lower in a.lower():
                        return True
            return False
        except Exception:
            return True  # fail-open if gating check errors


# ---------------------------------------------------------------------------
# Gold Bot Strategies (metals)
# ---------------------------------------------------------------------------


def _mtm_strategy(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Multi-Timeframe Momentum strategy wrapper for metals."""
    from ..strategies.mtm import MultiTimeframeMomentum

    strat = MultiTimeframeMomentum()
    signal = strat.generate_signal(
        symbol=symbol,
        ohlcv_data=data.get("ohlcv", data),
        indicators=data.get("indicators"),
        regime=data.get("regime_enum"),
    )
    if signal is None:
        return []
    return [
        {
            "side": signal.signal_type.value,
            "conviction": signal.confidence,
            "entry_price": float(signal.entry_price) if signal.entry_price else 0.0,
            "stop_loss": float(signal.stop_loss) if signal.stop_loss else 0.0,
            "take_profit": float(signal.take_profit) if signal.take_profit else 0.0,
            "strategy": "mtm",
            "regime": signal.regime.value if signal.regime else None,
            "metadata": signal.indicator_values,
        }
    ]


def _mrb_strategy(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Mean Reversion Bollinger strategy wrapper for metals."""
    from ..strategies.mrb import MeanReversionBollinger

    strat = MeanReversionBollinger()
    signal = strat.generate_signal(
        symbol=symbol,
        ohlcv_data=data.get("ohlcv", data),
        indicators=data.get("indicators"),
        regime=data.get("regime_enum"),
    )
    if signal is None:
        return []
    return [
        {
            "side": signal.signal_type.value,
            "conviction": signal.confidence,
            "entry_price": float(signal.entry_price) if signal.entry_price else 0.0,
            "stop_loss": float(signal.stop_loss) if signal.stop_loss else 0.0,
            "take_profit": float(signal.take_profit) if signal.take_profit else 0.0,
            "strategy": "mrb",
            "regime": signal.regime.value if signal.regime else None,
            "metadata": signal.indicator_values,
        }
    ]


def _mlb_strategy(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """ML Breakout strategy wrapper for metals."""
    from ..strategies.mlb import MLBreakout

    strat = MLBreakout()
    signal = strat.generate_signal(
        symbol=symbol,
        ohlcv_data=data.get("ohlcv", data),
        indicators=data.get("indicators"),
        regime=data.get("regime_enum"),
    )
    if signal is None:
        return []
    return [
        {
            "side": signal.signal_type.value,
            "conviction": signal.confidence,
            "entry_price": float(signal.entry_price) if signal.entry_price else 0.0,
            "stop_loss": float(signal.stop_loss) if signal.stop_loss else 0.0,
            "take_profit": float(signal.take_profit) if signal.take_profit else 0.0,
            "strategy": "mlb",
            "regime": signal.regime.value if signal.regime else None,
            "metadata": signal.indicator_values,
        }
    ]


def _ensemble_strategy(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Ensemble strategy wrapper for metals (combines MTM + MRB + MLB)."""
    from ..strategies.ensemble import EnsembleStrategy

    strat = EnsembleStrategy()
    signal = strat.generate_signal(
        symbol=symbol,
        ohlcv_data=data.get("ohlcv", data),
        indicators=data.get("indicators"),
        regime=data.get("regime_enum"),
    )
    if signal is None:
        return []
    return [
        {
            "side": signal.signal_type.value,
            "conviction": signal.confidence,
            "entry_price": float(signal.entry_price) if signal.entry_price else 0.0,
            "stop_loss": float(signal.stop_loss) if signal.stop_loss else 0.0,
            "take_profit": float(signal.take_profit) if signal.take_profit else 0.0,
            "strategy": "ensemble",
            "regime": signal.regime.value if signal.regime else None,
            "metadata": signal.indicator_values,
        }
    ]


def _placeholder_crypto(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Placeholder for crypto strategies — not yet implemented."""
    raise NotImplementedError("Crypto strategies not yet implemented")


def _placeholder_forex(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Placeholder for forex strategies — not yet implemented."""
    raise NotImplementedError("Forex strategies not yet implemented")


def _placeholder_indices(data: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    """Placeholder for indices strategies — not yet implemented."""
    raise NotImplementedError("Indices strategies not yet implemented")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_alpha_engine() -> AlphaEngine:
    """Create an AlphaEngine pre-configured with all built-in strategies.

    Metals: MTM, MRB, MLB, Ensemble (13 gold_bot strategies via the 4 wrappers)
    Crypto/Forex/Indices: placeholder strategies (raise NotImplementedError)
    """
    router = StrategyRouter()

    # Metals — route to existing gold_bot strategies
    router.register_many(AssetClass.METALS, [
        _mtm_strategy,
        _mrb_strategy,
        _mlb_strategy,
        _ensemble_strategy,
    ])

    # Crypto, Forex, Indices — placeholders
    router.register(AssetClass.CRYPTO, _placeholder_crypto)
    router.register(AssetClass.FOREX, _placeholder_forex)
    router.register(AssetClass.INDICES, _placeholder_indices)

    return AlphaEngine(router=router)
