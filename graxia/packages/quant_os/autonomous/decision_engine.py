"""LLM Decision Engine — autonomous trade signal generation from chart data.

Takes ChartSnapshot from ChartMonitor, sends OHLCV + indicators to LLM
for analysis, produces TradeDecision with confidence scores.

Safety:
    AI_CANNOT_SUBMIT_ORDER = True
    This module ONLY produces TradeDecision objects.
    Order submission is the OrderExecutor's responsibility.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from ..core.agents.llm_router import TIER1_PROVIDERS, get_router
from ..core.enums import SignalType
from .chart_monitor import ChartSnapshot
from .config import (
    DECISION_COOLDOWN_SECONDS,
    LLM_ANALYSIS_TIMEOUT,
    LLM_MIN_CONFIDENCE,
    LLM_USE_SCREENSHOT,
)

logger = structlog.get_logger(__name__)

MAX_HISTORY = 100
MAX_OHLCV_ROWS = 30

ANALYSIS_PROMPT = """You are a professional trading analyst for {symbol} on {timeframe}.

Analyze the following OHLCV data and indicators to produce a trade decision.

{data_section}

{indicator_section}

{screenshot_section}

Rules:
- Identify trend direction, support/resistance levels, and momentum
- Only signal BUY or SELL if there is a clear edge with confluence
- Default to NO_TRADE if uncertain — capital preservation is priority
- Confidence must reflect genuine conviction (0.0–1.0)
- Entry, SL, and TP must be realistic price levels
- Red flags: list any concerns (low volume, divergence, news risk, etc.)

Return ONLY valid JSON:
{{"direction": "BUY" or "SELL" or "NO_TRADE", "confidence": 0.0-1.0, "entry": 0.0, "sl": 0.0, "tp": 0.0, "reasoning": "brief analysis", "red_flags": []}}"""


@dataclass(frozen=True)
class TradeDecision:
    """Immutable trade decision from LLM analysis."""

    symbol: str
    direction: SignalType
    confidence: float
    entry: float
    stop_loss: float
    take_profit: float
    reasoning: str
    red_flags: tuple[str, ...]
    timestamp: datetime
    timeframe: str = ""
    snapshot_ts: datetime | None = None
    latency_ms: float = 0.0
    llm_provider: str = ""


class DecisionEngine:
    """LLM-powered trade decision engine for the autonomous loop.

    Takes ChartSnapshot input, analyzes via CascadeRouter, outputs
    TradeDecision objects. Never submits orders.
    """

    def __init__(
        self,
        min_confidence: float | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        self._min_confidence = min_confidence or LLM_MIN_CONFIDENCE
        self._cooldown_seconds = cooldown_seconds or DECISION_COOLDOWN_SECONDS
        self._history: dict[str, list[TradeDecision]] = defaultdict(list)
        self._last_analysis: dict[str, float] = {}

    async def analyze(self, snapshot: ChartSnapshot) -> TradeDecision:
        """Main analysis entry point. Returns a TradeDecision for the snapshot.

        Respects cooldown — skips re-analysis if same symbol/timeframe
        was analyzed recently.
        """
        key = self._cache_key(snapshot.symbol, snapshot.timeframe)

        if not self._should_analyze(key):
            logger.debug(
                "decision_engine_cooldown",
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
            )
            return self._no_trade_decision(snapshot, "Cooldown active — recent analysis exists")

        prompt = self._build_prompt(snapshot)

        try:
            decision = await asyncio.wait_for(
                self._call_llm(prompt, snapshot),
                timeout=LLM_ANALYSIS_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                "decision_engine_timeout",
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                timeout_s=LLM_ANALYSIS_TIMEOUT,
            )
            decision = self._no_trade_decision(snapshot, "LLM analysis timed out")
        except Exception as exc:
            logger.warning(
                "decision_engine_error",
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                error=str(exc),
            )
            decision = self._no_trade_decision(snapshot, f"Analysis error: {exc}")

        self._last_analysis[key] = time.monotonic()
        self._record(decision)

        logger.info(
            "decision_engine_result",
            symbol=decision.symbol,
            direction=decision.direction.value,
            confidence=round(decision.confidence, 3),
            entry=decision.entry,
            sl=decision.stop_loss,
            tp=decision.take_profit,
            should_trade=self._should_trade(decision),
            latency_ms=round(decision.latency_ms, 1),
            red_flags=list(decision.red_flags),
        )

        return decision

    def get_decision_history(self, symbol: str, n: int = 10) -> list[TradeDecision]:
        """Return up to *n* most recent decisions for *symbol*."""
        history = self._history.get(symbol, [])
        return history[-n:]

    def _should_trade(self, decision: TradeDecision) -> bool:
        """Check if decision meets confidence threshold for execution."""
        if decision.direction == SignalType.NO_TRADE:
            return False
        return decision.confidence >= self._min_confidence

    def _should_analyze(self, key: str) -> bool:
        """Check cooldown — skip if analyzed within DECISION_COOLDOWN_SECONDS."""
        last = self._last_analysis.get(key, 0.0)
        return (time.monotonic() - last) >= self._cooldown_seconds

    async def _call_llm(self, prompt: str, snapshot: ChartSnapshot) -> TradeDecision:
        """Send prompt to LLM cascade and parse response."""
        start = time.monotonic()

        router = get_router()
        raw_response, latency_ms, provider = await router._call_llm_chain(TIER1_PROVIDERS, prompt)

        if not raw_response:
            return self._no_trade_decision(snapshot, "All LLM providers failed")

        total_ms = (time.monotonic() - start) * 1000
        decision = self._parse_response(raw_response, snapshot)
        # Override latency with total wall-clock time
        return TradeDecision(
            symbol=decision.symbol,
            direction=decision.direction,
            confidence=decision.confidence,
            entry=decision.entry,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            reasoning=decision.reasoning,
            red_flags=decision.red_flags,
            timestamp=decision.timestamp,
            timeframe=decision.timeframe,
            snapshot_ts=decision.snapshot_ts,
            latency_ms=total_ms,
            llm_provider=provider.name if provider else "",
        )

    def _build_prompt(self, snapshot: ChartSnapshot) -> str:
        """Build the LLM analysis prompt from OHLCV + indicators."""
        ohlcv_text = self._format_ohlcv(snapshot.ohlcv[-MAX_OHLCV_ROWS:])

        indicator_section = ""
        if snapshot.indicators:
            indicator_section = "Technical Indicators:\n" + "\n".join(
                f"- {k}: {v}" for k, v in snapshot.indicators.items()
            )

        screenshot_section = ""
        if LLM_USE_SCREENSHOT and snapshot.screenshot_path:
            screenshot_section = (
                f"A chart screenshot is available at: {snapshot.screenshot_path}\n"
                "Analyze the visual pattern if you can, but base decisions on the OHLCV data."
            )

        return ANALYSIS_PROMPT.format(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            data_section=ohlcv_text,
            indicator_section=indicator_section,
            screenshot_section=screenshot_section,
        )

    def _parse_response(self, raw: str, snapshot: ChartSnapshot) -> TradeDecision:
        """Parse LLM JSON response into a TradeDecision."""
        data = self._extract_json(raw)

        direction_str = str(data.get("direction", "NO_TRADE")).upper()
        try:
            direction = SignalType(direction_str)
        except ValueError:
            direction = SignalType.NO_TRADE

        raw_conf = data.get("confidence", 0.0)
        confidence = self._clamp_confidence(float(raw_conf) if raw_conf is not None else 0.0)

        # If LLM returned a trade direction but confidence is below threshold,
        # downgrade to NO_TRADE
        if direction in (SignalType.BUY, SignalType.SELL) and confidence < self._min_confidence:
            direction = SignalType.NO_TRADE

        raw_flags = data.get("red_flags", [])
        red_flags = tuple(str(f) for f in raw_flags if f) if isinstance(raw_flags, list) else ()

        decision = TradeDecision(
            symbol=snapshot.symbol,
            direction=direction,
            confidence=confidence,
            entry=float(data.get("entry", 0.0)),
            stop_loss=float(data.get("sl", 0.0)),
            take_profit=float(data.get("tp", 0.0)),
            reasoning=str(data.get("reasoning", ""))[:500],
            red_flags=red_flags,
            timestamp=datetime.now(tz=UTC),
            timeframe=snapshot.timeframe,
            snapshot_ts=snapshot.timestamp,
        )

        return self._validate_numeric_output(decision)

    def _validate_numeric_output(self, decision: TradeDecision) -> TradeDecision:
        """Validate LLM numeric fields. Downgrades to NO_TRADE on failure."""
        if decision.direction == SignalType.NO_TRADE:
            return decision

        entry = decision.entry
        sl = decision.stop_loss
        tp = decision.take_profit
        errors: list[str] = []

        if entry <= 0:
            errors.append(f"entry_not_positive:{entry}")
        if sl <= 0:
            errors.append(f"sl_not_positive:{sl}")
        if tp <= 0:
            errors.append(f"tp_not_positive:{tp}")

        if entry > 0 and sl > 0 and entry == sl:
            errors.append("entry_equals_sl")
        if entry > 0 and tp > 0 and entry == tp:
            errors.append("entry_equals_tp")

        if not errors:
            if decision.direction == SignalType.BUY:
                if entry <= sl:
                    errors.append(f"buy_entry_not_above_sl:{entry}<={sl}")
                if entry >= tp:
                    errors.append(f"buy_entry_not_below_tp:{entry}>={tp}")
            elif decision.direction == SignalType.SELL:
                if entry >= sl:
                    errors.append(f"sell_entry_not_below_sl:{entry}>={sl}")
                if entry <= tp:
                    errors.append(f"sell_entry_not_above_tp:{entry}<={tp}")

        if errors:
            logger.warning(
                "decision_engine_numeric_invalid",
                symbol=decision.symbol,
                direction=decision.direction.value,
                entry=entry,
                sl=sl,
                tp=tp,
                errors=errors,
            )
            return TradeDecision(
                symbol=decision.symbol,
                direction=SignalType.NO_TRADE,
                confidence=0.0,
                entry=entry,
                stop_loss=sl,
                take_profit=tp,
                reasoning=decision.reasoning,
                red_flags=decision.red_flags + ("invalid_numeric_output",),
                timestamp=decision.timestamp,
                timeframe=decision.timeframe,
                snapshot_ts=decision.snapshot_ts,
                latency_ms=decision.latency_ms,
                llm_provider=decision.llm_provider,
            )

        return decision

    def _no_trade_decision(self, snapshot: ChartSnapshot, reason: str) -> TradeDecision:
        """Create a deterministic NO_TRADE decision."""
        return TradeDecision(
            symbol=snapshot.symbol,
            direction=SignalType.NO_TRADE,
            confidence=0.0,
            entry=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            reasoning=reason,
            red_flags=("deterministic_fallback",),
            timestamp=datetime.now(tz=UTC),
            timeframe=snapshot.timeframe,
            snapshot_ts=snapshot.timestamp,
        )

    def _record(self, decision: TradeDecision) -> None:
        """Append decision to per-symbol history ring buffer."""
        history = self._history[decision.symbol]
        history.append(decision)
        if len(history) > MAX_HISTORY:
            self._history[decision.symbol] = history[-MAX_HISTORY:]

    @staticmethod
    def _format_ohlcv(bars: list[Any]) -> str:
        """Format OHLCV bars into a compact text table."""
        if not bars:
            return "OHLCV Data: (no data available)"

        lines = ["Timestamp               | Open      | High      | Low       | Close     | Volume"]
        lines.append("-" * 90)
        for bar in bars:
            ts = bar.timestamp.strftime("%Y-%m-%d %H:%M") if hasattr(bar.timestamp, "strftime") else str(bar.timestamp)
            lines.append(
                f"{ts:<24}| {bar.open:<10.5f}| {bar.high:<10.5f}| {bar.low:<10.5f}| {bar.close:<10.5f}| {bar.volume}"
            )
        return "OHLCV Data:\n" + "\n".join(lines)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract JSON from LLM response, handling markdown fences."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {}

    @staticmethod
    def _clamp_confidence(value: float) -> float:
        """Clamp confidence to [0.0, 0.95] — never 100% certain."""
        return max(0.0, min(0.95, value))

    @staticmethod
    def _cache_key(symbol: str, timeframe: str) -> str:
        return f"{symbol}:{timeframe}"
