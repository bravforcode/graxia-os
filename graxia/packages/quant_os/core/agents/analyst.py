"""
TechnicalAnalystAgent (C1)

Reads BarEvents and emits a technical opinion as a SignalEvent.
Rules: simple moving average crossover + RSI-like momentum check.
"""

from dataclasses import dataclass, field

from ..enums import SignalType
from ..events import BarEvent, Event, SignalEvent
from .base import Agent


@dataclass
class TechnicalOpinion:
    """Internal opinion produced by TechnicalAnalystAgent."""

    symbol: str = ""
    direction: SignalType = SignalType.NO_TRADE
    confidence: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reasons: list[str] = field(default_factory=list)


class TechnicalAnalystAgent(Agent):
    """
    Rule-based technical analyst.

    Strategy:
        - Track closing prices per symbol
        - Compute short SMA (5 bars) vs long SMA (20 bars)
        - Short > Long + last bar bullish → BUY
        - Short < Long + last bar bearish → SELL
        - Otherwise → NO_TRADE
    """

    SHORT_WINDOW = 5
    LONG_WINDOW = 20
    SL_ATR_MULT = 1.5
    TP_ATR_MULT = 2.0

    def __init__(self, name: str = "technical_analyst") -> None:
        super().__init__(name)
        self._closes: dict[str, list[float]] = {}
        self._highs: dict[str, list[float]] = {}
        self._lows: dict[str, list[float]] = {}
        self._last_opinion: TechnicalOpinion | None = None

    def observe(self, event: Event) -> None:
        if not isinstance(event, BarEvent):
            return
        sym = event.symbol
        if sym not in self._closes:
            self._closes[sym] = []
            self._highs[sym] = []
            self._lows[sym] = []
        self._closes[sym].append(event.close)
        self._highs[sym].append(event.high)
        self._lows[sym].append(event.low)
        # Keep bounded
        max_len = self.LONG_WINDOW + 10
        if len(self._closes[sym]) > max_len:
            self._closes[sym] = self._closes[sym][-max_len:]
            self._highs[sym] = self._highs[sym][-max_len:]
            self._lows[sym] = self._lows[sym][-max_len:]

    def act(self) -> Event | None:
        opinions = []
        for sym in list(self._closes.keys()):
            closes = self._closes[sym]
            highs = self._highs[sym]
            lows = self._lows[sym]
            if len(closes) < self.LONG_WINDOW:
                continue
            opinion = self._evaluate(sym, closes, highs, lows)
            if opinion.direction != SignalType.NO_TRADE:
                opinions.append(opinion)
        if not opinions:
            return None
        # Return highest confidence opinion
        best = max(opinions, key=lambda o: o.confidence)
        self._last_opinion = best
        return SignalEvent(
            symbol=best.symbol,
            signal_type=best.direction,
            confidence=best.confidence,
            entry_price=best.entry_price,
            stop_loss=best.stop_loss,
            take_profit=best.take_profit,
            source=self.name,
            metadata={"reasons": best.reasons},
        )

    def _evaluate(self, sym: str, closes: list[float], highs: list[float], lows: list[float]) -> TechnicalOpinion:
        reasons: list[str] = []

        # SMA crossover
        short_sma = sum(closes[-self.SHORT_WINDOW :]) / self.SHORT_WINDOW
        long_sma = sum(closes[-self.LONG_WINDOW :]) / self.LONG_WINDOW
        last_close = closes[-1]
        prev_close = closes[-2]

        bullish_cross = short_sma > long_sma
        bearish_cross = short_sma < long_sma
        last_bar_bullish = last_close > prev_close
        last_bar_bearish = last_close < prev_close

        # Simple ATR estimate (average true range)
        trs = []
        for i in range(-self.SHORT_WINDOW, 0):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        atr = sum(trs) / len(trs) if trs else 1.0

        direction = SignalType.NO_TRADE
        confidence = 0.0

        if bullish_cross and last_bar_bullish:
            direction = SignalType.BUY
            confidence = min(0.9, 0.5 + (short_sma - long_sma) / last_close * 100)
            reasons.append(f"bullish_sma_cross({self.SHORT_WINDOW}>{self.LONG_WINDOW})")
            reasons.append("last_bar_bullish")
        elif bearish_cross and last_bar_bearish:
            direction = SignalType.SELL
            confidence = min(0.9, 0.5 + (long_sma - short_sma) / last_close * 100)
            reasons.append(f"bearish_sma_cross({self.SHORT_WINDOW}<{self.LONG_WINDOW})")
            reasons.append("last_bar_bearish")

        entry = last_close
        if direction == SignalType.BUY:
            sl = entry - atr * self.SL_ATR_MULT
            tp = entry + atr * self.TP_ATR_MULT
        elif direction == SignalType.SELL:
            sl = entry + atr * self.SL_ATR_MULT
            tp = entry - atr * self.TP_ATR_MULT
        else:
            sl = 0.0
            tp = 0.0

        return TechnicalOpinion(
            symbol=sym,
            direction=direction,
            confidence=round(confidence, 4),
            entry_price=entry,
            stop_loss=round(sl, 5),
            take_profit=round(tp, 5),
            reasons=reasons,
        )

    def reset(self) -> None:
        super().reset()
        self._closes.clear()
        self._highs.clear()
        self._lows.clear()
        self._last_opinion = None
