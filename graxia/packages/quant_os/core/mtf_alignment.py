"""Multi-timeframe alignment — live signal consensus (INV-004).

INV-004: Strict MTF blocks static fallback without cursor.
This module only aligns signals — does NOT provide fallback data.

Usage:
    from core.mtf_alignment import MTFAlignmentChecker, TimeframeSignal, TrendDirection
    checker = MTFAlignmentChecker(min_agreement=0.6)
    signals = [
        TimeframeSignal("M15", TrendDirection.BULLISH, 0.8),
        TimeframeSignal("H1", TrendDirection.BULLISH, 0.7),
        TimeframeSignal("D1", TrendDirection.BEARISH, 0.5),
    ]
    result = checker.align(signals)
    if result.aligned:
        print(f"Direction: {result.direction}, agreement: {result.agreement_ratio}")
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TrendDirection(Enum):
    """Trend direction for a single timeframe."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class TimeframeSignal:
    """Signal from a single timeframe."""

    timeframe: str  # "M15", "H1", "D1", etc.
    direction: TrendDirection
    strength: float  # 0.0-1.0


@dataclass
class MTFAlignment:
    """Result of multi-timeframe alignment check."""

    aligned: bool
    direction: TrendDirection
    signals: list[TimeframeSignal]
    agreement_ratio: float
    details: dict | None = None


class MTFAlignmentChecker:
    """Check multi-timeframe signal alignment for live trading.

    INV-004: Strict MTF — no static fallback without cursor.
    This checker validates signal consensus, not data availability.
    """

    def __init__(self, min_agreement: float = 0.6):
        self._min_agreement = min_agreement

    def align(self, signals: list[TimeframeSignal]) -> MTFAlignment:
        """Check if signals across timeframes agree on direction.

        Agreement = count of dominant direction / total signals.
        Strength-weighted agreement also considered.

        Args:
            signals: List of signals from different timeframes.

        Returns:
            MTFAlignment with aligned=True if agreement >= min_agreement.
        """
        if not signals:
            return MTFAlignment(
                False, TrendDirection.NEUTRAL, [], 0.0,
                details={"reason": "no_signals"},
            )

        # Count direction votes
        bullish_count = sum(1 for s in signals if s.direction == TrendDirection.BULLISH)
        bearish_count = sum(1 for s in signals if s.direction == TrendDirection.BEARISH)
        total = len(signals)

        # Weighted by strength
        bull_strength = sum(
            s.strength for s in signals if s.direction == TrendDirection.BULLISH
        )
        bear_strength = sum(
            s.strength for s in signals if s.direction == TrendDirection.BEARISH
        )

        # Determine dominant direction
        if bull_strength > bear_strength:
            dominant = TrendDirection.BULLISH
            agreement = bullish_count / total
            dominant_count = bullish_count
        elif bear_strength > bull_strength:
            dominant = TrendDirection.BEARISH
            agreement = bearish_count / total
            dominant_count = bearish_count
        else:
            dominant = TrendDirection.NEUTRAL
            agreement = 0.0
            dominant_count = 0

        return MTFAlignment(
            aligned=agreement >= self._min_agreement and dominant != TrendDirection.NEUTRAL,
            direction=dominant,
            signals=signals,
            agreement_ratio=agreement,
            details={
                "total_signals": total,
                "dominant_count": dominant_count,
                "bull_strength": round(bull_strength, 3),
                "bear_strength": round(bear_strength, 3),
                "min_agreement": self._min_agreement,
            },
        )

    def align_from_dicts(
        self, signal_dicts: list[dict]
    ) -> MTFAlignment:
        """Convenience: accept list of {timeframe, direction, strength} dicts."""
        signals = [
            TimeframeSignal(
                timeframe=d["timeframe"],
                direction=TrendDirection(d["direction"]),
                strength=d.get("strength", 0.5),
            )
            for d in signal_dicts
        ]
        return self.align(signals)
