"""
Strategy Ensemble — generic multi-strategy signal combiner with dynamic weighting.

Combines signals from an arbitrary set of Strategy instances using weighted
voting.  Weights are seeded from a config dict and then adjusted online based
on rolling Sharpe / win-rate performance so the ensemble self-balances toward
strategies that are currently working.

Public API
----------
StrategyEnsemble
    .add_strategy(strategy, weight)
    .remove_strategy(name)
    .get_weights() -> dict[str, float]
    .get_ensemble_signal(symbol, ohlcv, indicators, regime, **kw) -> Signal | None
    .record_outcome(strategy_name, pnl_pct)
    .adjust_weights()
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import structlog

try:
    from ..core.enums import DecisionType, RegimeType, SignalType
    from .base import Signal, Strategy, StrategyConfig
except (ImportError, SystemError):
    from core.enums import DecisionType, RegimeType, SignalType
    from strategies.base import Signal, Strategy

logger = structlog.get_logger(__name__)

# ── defaults ────────────────────────────────────────────────────────────

_DEFAULT_MIN_CONFIDENCE: float = 0.60
_DEFAULT_PERFORMANCE_WINDOW: int = 30
_DEFAULT_LEARNING_RATE: float = 0.10
_DEFAULT_MIN_WEIGHT: float = 0.05
_DEFAULT_MAX_WEIGHT: float = 0.80


# ── data classes ────────────────────────────────────────────────────────


@dataclass
class StrategyRecord:
    """Tracks one strategy inside the ensemble."""

    strategy: Strategy
    weight: float

    # rolling performance buffer
    recent_pnls: deque[float] = field(default_factory=lambda: deque(maxlen=_DEFAULT_PERFORMANCE_WINDOW))
    cumulative_pnl_pct: float = 0.0
    trades_recorded: int = 0

    @property
    def name(self) -> str:
        return self.strategy.config.name


@dataclass(frozen=True)
class EnsembleVote:
    """One strategy's vote inside the ensemble."""

    strategy_name: str
    weight: float
    signal_type: SignalType
    confidence: float
    weighted_score: float
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None


@dataclass
class EnsembleResult:
    """Full ensemble output."""

    decision: DecisionType
    confidence: float
    votes: list[EnsembleVote]
    consensus_signal: Signal | None
    reason: str
    weights_snapshot: dict[str, float]


# ── ensemble class ──────────────────────────────────────────────────────


class StrategyEnsemble:
    """
    Generic strategy ensemble.

    Strategies are added with ``add_strategy`` (or via the constructor) and
    assigned an initial weight.  Each call to ``get_ensemble_signal`` collects
    sub-signals, applies weighted voting, and returns a single aggregated
    ``Signal`` (or ``None``).

    Weights are periodically adjusted with ``adjust_weights()`` — call this
    after a batch of trades has closed to re-balance toward better performers.

    Parameters
    ----------
    confidence_threshold : float
        Minimum aggregate confidence to emit a signal (default 0.60).
    performance_window : int
        Number of recent trades used for dynamic weight adjustment.
    learning_rate : float
        Speed of weight re-balancing (0 = frozen, 1 = instant).
    min_weight : float
        Floor for any single strategy weight.
    max_weight : float
        Ceiling for any single strategy weight.
    """

    def __init__(
        self,
        confidence_threshold: float = _DEFAULT_MIN_CONFIDENCE,
        performance_window: int = _DEFAULT_PERFORMANCE_WINDOW,
        learning_rate: float = _DEFAULT_LEARNING_RATE,
        min_weight: float = _DEFAULT_MIN_WEIGHT,
        max_weight: float = _DEFAULT_MAX_WEIGHT,
    ) -> None:
        self._records: dict[str, StrategyRecord] = {}
        self._confidence_threshold = confidence_threshold
        self._performance_window = performance_window
        self._learning_rate = learning_rate
        self._min_weight = min_weight
        self._max_weight = max_weight

        logger.info(
            "ensemble_init",
            confidence_threshold=confidence_threshold,
            performance_window=performance_window,
            learning_rate=learning_rate,
        )

    # ── strategy management ────────────────────────────────────────────

    def add_strategy(self, strategy: Strategy, weight: float | None = None) -> None:
        """
        Register a strategy in the ensemble.

        Parameters
        ----------
        strategy : Strategy
            Instance that implements ``generate_signal``.
        weight : float, optional
            Initial weight.  If *None*, weight is distributed evenly across
            all registered strategies (including this one).
        """
        name = strategy.config.name
        if name in self._records:
            logger.warning("ensemble_strategy_exists", name=name)
            return

        if weight is None:
            # even distribution
            n = len(self._records) + 1
            for rec in self._records.values():
                rec.weight = 1.0 / n
            weight = 1.0 / n

        self._records[name] = StrategyRecord(strategy=strategy, weight=weight)
        logger.info("ensemble_strategy_added", name=name, weight=weight)

    def remove_strategy(self, name: str) -> bool:
        """
        Remove a strategy by config name.

        Returns ``True`` if the strategy was found and removed.
        """
        if name not in self._records:
            return False
        del self._records[name]
        # re-normalise
        total = sum(r.weight for r in self._records.values())
        if total > 0:
            for rec in self._records.values():
                rec.weight /= total
        logger.info("ensemble_strategy_removed", name=name)
        return True

    def get_weights(self) -> dict[str, float]:
        """Return a {strategy_name: weight} snapshot."""
        return {name: rec.weight for name, rec in self._records.items()}

    # ── signal generation ──────────────────────────────────────────────

    def get_ensemble_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime: RegimeType | None = None,
        **kwargs: Any,
    ) -> Signal | None:
        """
        Collect signals from every registered strategy, apply weighted voting,
        and return a single ``Signal`` if confidence exceeds the threshold.

        Parameters
        ----------
        symbol : str
        ohlcv_data : dict
            Keys ``open``, ``high``, ``low``, ``close``, ``volume``.
        indicators : dict, optional
            Pre-computed indicators.
        regime : RegimeType, optional
        **kwargs
            Forwarded to sub-strategy ``generate_signal``.

        Returns
        -------
        Signal | None
        """
        if not self._records:
            logger.warning("ensemble_empty")
            return None

        votes: list[EnsembleVote] = []
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0

        for name, rec in self._records.items():
            try:
                sig = rec.strategy.generate_signal(symbol, ohlcv_data, indicators, regime, **kwargs)
            except Exception:
                logger.exception("ensemble_sub_error", strategy=name)
                continue

            total_weight += rec.weight
            if sig is None or sig.signal_type == SignalType.NO_TRADE:
                continue

            weighted = rec.weight * sig.confidence
            votes.append(
                EnsembleVote(
                    strategy_name=name,
                    weight=rec.weight,
                    signal_type=sig.signal_type,
                    confidence=sig.confidence,
                    weighted_score=weighted,
                    stop_loss=sig.stop_loss,
                    take_profit=sig.take_profit,
                )
            )
            if sig.signal_type == SignalType.BUY:
                buy_score += weighted
            elif sig.signal_type == SignalType.SELL:
                sell_score += weighted

        # ── decide ─────────────────────────────────────────────────────
        if total_weight == 0:
            return None

        # normalise
        norm_buy = buy_score / total_weight
        norm_sell = sell_score / total_weight

        best_dir = "buy" if norm_buy >= norm_sell else "sell"
        best_score = max(norm_buy, norm_sell)

        reason = "ensemble_vote"
        decision: DecisionType

        if best_score < self._confidence_threshold:
            decision = DecisionType.NO_TRADE
            reason = "insufficient_confidence"
        elif norm_buy > 0.4 and norm_sell > 0.4:
            # strong disagreement
            decision = DecisionType.NO_TRADE
            reason = "conflicting_signals"
        elif best_dir == "buy":
            decision = DecisionType.BUY
        else:
            decision = DecisionType.SELL

        if decision not in (DecisionType.BUY, DecisionType.SELL):
            logger.debug(
                "ensemble_abstain",
                reason=reason,
                buy=round(norm_buy, 4),
                sell=round(norm_sell, 4),
            )
            return None

        # ── build consensus Signal ─────────────────────────────────────
        sig_type = SignalType.BUY if decision == DecisionType.BUY else SignalType.SELL
        current_price = Decimal(str(ohlcv_data.get("close", [0])[-1]))

        # consensus SL / TP (weighted average across winning-side votes)
        winning_votes = [v for v in votes if v.signal_type == sig_type]
        consensus_sl, consensus_tp = self._consensus_levels(winning_votes, current_price, sig_type, ohlcv_data)

        strength = "strong" if best_score > 0.75 else "medium" if best_score > 0.65 else "weak"

        self._records[next(iter(self._records))].strategy.signals_generated += 1

        ensemble_sig = Signal.create(
            strategy_id="ensemble",
            symbol=symbol,
            signal_type=sig_type,
            confidence=best_score,
            strength=strength,
            entry_price=current_price,
            stop_loss=consensus_sl,
            take_profit=consensus_tp,
            regime=regime,
            timeframe=kwargs.get("timeframe", "M15"),
            indicator_values={
                "votes": [
                    {
                        "strategy": v.strategy_name,
                        "weight": v.weight,
                        "signal": v.signal_type.value,
                        "confidence": v.confidence,
                        "weighted": round(v.weighted_score, 4),
                    }
                    for v in votes
                ],
                "buy_score": round(norm_buy, 4),
                "sell_score": round(norm_sell, 4),
                "weights": self.get_weights(),
            },
            notes=f"Ensemble {decision.value} on {symbol} — {best_score:.2f} confidence",
        )

        logger.info(
            "ensemble_signal",
            decision=decision.value,
            confidence=round(best_score, 4),
            symbol=symbol,
            n_strategies=len(votes),
        )

        return ensemble_sig

    # ── performance tracking ───────────────────────────────────────────

    def record_outcome(self, strategy_name: str, pnl_pct: float) -> None:
        """
        Feed back a closed-trade PnL for one strategy.

        Parameters
        ----------
        strategy_name : str
            Must match ``config.name`` of a registered strategy.
        pnl_pct : float
            Percentage PnL (e.g. 0.5 for +0.5%).
        """
        rec = self._records.get(strategy_name)
        if rec is None:
            logger.warning("ensemble_record_unknown", name=strategy_name)
            return
        rec.recent_pnls.append(pnl_pct)
        rec.cumulative_pnl_pct += pnl_pct
        rec.trades_recorded += 1

    def adjust_weights(self) -> dict[str, float]:
        """
        Rebalance weights based on recent performance (rolling Sharpe proxy).

        Called after a batch of trades closes.  The adjustment shifts weight
        toward strategies with higher recent risk-adjusted returns and away
        from under-performers, subject to ``min_weight`` / ``max_weight``.

        Returns the new weight map.
        """
        if not self._records:
            return {}

        scores: dict[str, float] = {}
        for name, rec in self._records.items():
            pnls = list(rec.recent_pnls)
            if len(pnls) < 2:
                scores[name] = 0.0
                continue
            mean = sum(pnls) / len(pnls)
            var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
            std = math.sqrt(var) if var > 0 else 1e-9
            scores[name] = mean / std  # Sharpe-like proxy

        # normalise scores to [0, 1]
        min_s = min(scores.values())
        max_s = max(scores.values())
        spread = max_s - min_s if max_s != min_s else 1.0
        normed = {k: (v - min_s) / spread for k, v in scores.items()}

        # blend with current weights (learning rate controls speed)
        new_weights: dict[str, float] = {}
        for name, rec in self._records.items():
            blended = rec.weight * (1 - self._learning_rate) + normed[name] * self._learning_rate
            new_weights[name] = max(self._min_weight, min(self._max_weight, blended))

        # re-normalise to sum=1
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: v / total for k, v in new_weights.items()}

        # apply
        for name, rec in self._records.items():
            old = rec.weight
            rec.weight = new_weights[name]
            if abs(old - rec.weight) > 1e-6:
                logger.info(
                    "ensemble_weight_adjusted",
                    name=name,
                    old=round(old, 4),
                    new=round(rec.weight, 4),
                )

        return new_weights

    # ── internals ──────────────────────────────────────────────────────

    @staticmethod
    def _compute_atr(highs: list, lows: list, closes: list, period: int = 14) -> Decimal | None:
        """Simple ATR from OHLC arrays. Returns None if insufficient data."""
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
            return None
        tr_sum = 0.0
        for i in range(-period, 0):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_sum += tr
        return Decimal(str(tr_sum / period))

    @staticmethod
    def _consensus_levels(
        votes: Sequence[EnsembleVote],
        current_price: Decimal,
        signal_type: Any | None = None,
        ohlcv_data: dict[str, list] | None = None,
    ) -> tuple[Decimal | None, Decimal | None]:
        """
        Weighted-average stop-loss / take-profit across winning-side votes.

        Falls back to ATR-based SL/TP when no sub-signal provided levels.
        """
        if not votes:
            return None, None

        votes_with_sl = [v for v in votes if v.stop_loss is not None]
        votes_with_tp = [v for v in votes if v.take_profit is not None]

        consensus_sl = None
        consensus_tp = None

        if votes_with_sl:
            total_weight_sl = Decimal(str(sum(v.weight for v in votes_with_sl)))
            if total_weight_sl > 0:
                weighted_sl_sum = sum(v.stop_loss * Decimal(str(v.weight)) for v in votes_with_sl)
                consensus_sl = weighted_sl_sum / total_weight_sl

        if votes_with_tp:
            total_weight_tp = Decimal(str(sum(v.weight for v in votes_with_tp)))
            if total_weight_tp > 0:
                weighted_tp_sum = sum(v.take_profit * Decimal(str(v.weight)) for v in votes_with_tp)
                consensus_tp = weighted_tp_sum / total_weight_tp

        # ── ATR-based fallback when sub-strategies don't provide SL/TP ──
        if consensus_sl is None or consensus_tp is None:
            atr = None
            if ohlcv_data:
                highs = ohlcv_data.get("high", [])
                lows = ohlcv_data.get("low", [])
                closes = ohlcv_data.get("close", [])
                atr = StrategyEnsemble._compute_atr(highs, lows, closes)

            if atr and atr > 0:
                is_long = signal_type is not None and str(signal_type).upper() in ("BUY", "SIGNALTYPE.BUY")
                if consensus_sl is None:
                    consensus_sl = current_price - (2 * atr) if is_long else current_price + (2 * atr)
                if consensus_tp is None:
                    consensus_tp = current_price + (3 * atr) if is_long else current_price - (3 * atr)
                logger.warning(
                    "ensemble_fallback_sl_tp",
                    reason="WARNING: Using ATR-based fallback SL/TP — sub-strategies did not provide levels",
                    atr=str(round(atr, 6)),
                    sl=str(round(consensus_sl, 6)),
                    tp=str(round(consensus_tp, 6)),
                )

        return consensus_sl, consensus_tp

    def __repr__(self) -> str:
        names = ", ".join(self._records.keys())
        return f"<StrategyEnsemble strategies=[{names}]>"


# ── Backward-compat aliases ────────────────────────────────────────
EnsembleStrategy = StrategyEnsemble

STRATEGY_WEIGHTS = {
    "mtm": 0.40,
    "mrb": 0.25,
    "mlb": 0.35,
}


def get_ensemble_signal(
    strategies: list | None = None,
    symbol: str = "",
    ohlcv: dict | None = None,
    indicators: dict | None = None,
    regime=None,
    mtm_signal=None,
    mrb_signal=None,
    mlb_signal=None,
    **kwargs,
):
    """Legacy function — wraps StrategyEnsemble.get_ensemble_signal()."""
    ensemble = StrategyEnsemble()

    # Map old keyword args to strategy objects
    signal_map = {
        "mtm": mtm_signal,
        "mrb": mrb_signal,
        "mlb": mlb_signal,
    }

    for name, sig in signal_map.items():
        if sig is not None:
            weight = STRATEGY_WEIGHTS.get(name, 1.0 / len(signal_map))
            ensemble.add_strategy(_FakeStrategy(name, sig), weight)

    if strategies:
        for s in strategies:
            ensemble.add_strategy(s)

    result = ensemble.get_ensemble_signal(
        symbol or (mtm_signal.symbol if mtm_signal else ""),
        ohlcv or {},
        indicators,
        regime,
        **kwargs,
    )

    # Backward-compat: return (decision, confidence, details) tuple
    if result is None:
        return SignalType.NO_TRADE, 0.0, {}
    return result.signal_type, result.confidence, result.indicator_values


class _FakeStrategy:
    """Minimal strategy wrapper for backward-compat get_ensemble_signal."""

    def __init__(self, name: str, signal):
        self._name = name
        self._signal = signal
        self.config = type("Config", (), {"name": name})()
        self.signals_generated = 0

    @property
    def name(self):
        return self._name

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kw):
        return self._signal
