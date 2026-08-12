"""Liquidity Map — identifies key liquidity levels from OHLCV data.

Level types: PDH/PDL, session H/L, swing H/L, EQH/EQL, round numbers.
"""
from dataclasses import dataclass
from typing import List
from datetime import datetime
from enum import Enum


class LevelType(str, Enum):
    PDH = "PDH"  # Previous Day High
    PDL = "PDL"  # Previous Day Low
    ASIAN_H = "ASIAN_H"  # Asian Session High
    ASIAN_L = "ASIAN_L"  # Asian Session Low
    LONDON_H = "LONDON_H"  # London Session High
    LONDON_L = "LONDON_L"  # London Session Low
    NY_H = "NY_H"  # New York Session High
    NY_L = "NY_L"  # New York Session Low
    SWING_H = "SWING_H"  # Swing High
    SWING_L = "SWING_L"  # Swing Low
    EQH = "EQH"  # Equal Highs
    EQL = "EQL"  # Equal Lows
    ROUND = "ROUND"  # Round Number


@dataclass
class LiquidityLevel:
    level_type: str  # from LevelType enum
    price: float
    session: str = ""  # ASIAN | LONDON | NY | OVERNIGHT | ""
    touch_count: int = 0
    strength_score: float = 0.0  # 0.0-1.0
    freshness_score: float = 0.0  # 0.0-1.0 (newer = higher)
    sweep_side: str = ""  # ABOVE | BELOW | NONE
    is_active: bool = True
    bars_since_formed: int = 0
    reason_code: str = ""


def hour_ict(t: datetime) -> int:
    """Convert UTC datetime to ICT (UTC+7) hour."""
    return (t.hour + 7) % 24


def get_session(t: datetime) -> str:
    """Determine trading session from timestamp (ICT)."""
    h = hour_ict(t)
    if 7 <= h < 15:
        return "ASIAN"
    elif 15 <= h < 23:
        return "LONDON"
    else:
        return "NY"  # NY session covers ICT 23:00-07:00


class LiquidityMap:
    """Builds a map of liquidity levels from OHLCV bars.

    Args:
        bars: List of dicts with keys: time, high, low, close
              time = datetime object (UTC)
    """

    def __init__(self, bars: List[dict]):
        self.bars = bars
        self.levels: List[LiquidityLevel] = []

    def build(self) -> List[LiquidityLevel]:
        """Build complete liquidity map."""
        self.levels = []
        if len(self.bars) < 10:
            return self.levels

        self._add_session_levels()
        self._add_swing_levels()
        self._add_equal_levels()
        self._add_round_numbers()
        self._score_levels()

        return sorted(self.levels, key=lambda x: x.strength_score, reverse=True)

    # --- Session levels ---

    def _add_session_levels(self):
        """Add session high/low for each trading session."""
        if not self.bars:
            return

        # Group bars by session
        sessions = {"ASIAN": [], "LONDON": [], "NY": []}
        for b in self.bars:
            sess = get_session(b["time"])
            sessions[sess].append(b)

        for sess_name, bars in sessions.items():
            if not bars:
                continue
            high = max(b["high"] for b in bars)
            low = min(b["low"] for b in bars)
            self.levels.append(LiquidityLevel(
                level_type=f"{sess_name}_H",
                price=high, session=sess_name, touch_count=0,
                strength_score=0.6, freshness_score=1.0,
                is_active=True, reason_code=f"{sess_name}_HIGH",
            ))
            self.levels.append(LiquidityLevel(
                level_type=f"{sess_name}_L",
                price=low, session=sess_name, touch_count=0,
                strength_score=0.6, freshness_score=1.0,
                is_active=True, reason_code=f"{sess_name}_LOW",
            ))

    # --- Swing levels ---

    def _add_swing_levels(self, lookback: int = 20, max_levels: int = 10):
        """Detect swing highs and lows."""
        if len(self.bars) < lookback + 2:
            return

        swing_highs = []
        swing_lows = []

        for i in range(1, len(self.bars) - 1):
            if i < lookback:
                continue
            h = self.bars[i]["high"]
            l = self.bars[i]["low"]
            prev_highs = [self.bars[j]["high"] for j in range(i - lookback, i)]
            prev_lows = [self.bars[j]["low"] for j in range(i - lookback, i)]

            if h > max(prev_highs):
                strength = min(1.0, (h - sum(prev_highs) / len(prev_highs)) / h * 1000)
                swing_highs.append((h, i, strength))

            if l <= min(prev_lows):
                strength = min(1.0, (sum(prev_lows) / len(prev_lows) - l) / l * 1000)
                swing_lows.append((l, i, strength))

        # Keep only strongest swings
        swing_highs.sort(key=lambda x: x[2], reverse=True)
        swing_lows.sort(key=lambda x: x[2], reverse=True)

        for price, idx, strength in swing_highs[:max_levels]:
            self.levels.append(LiquidityLevel(
                level_type="SWING_H", price=price, session=get_session(self.bars[idx]["time"]),
                touch_count=0, strength_score=strength,
                freshness_score=1.0, sweep_side="ABOVE",
                is_active=True, bars_since_formed=len(self.bars) - idx,
                reason_code=f"SWING_H@{idx}",
            ))

        for price, idx, strength in swing_lows[:max_levels]:
            self.levels.append(LiquidityLevel(
                level_type="SWING_L", price=price, session=get_session(self.bars[idx]["time"]),
                touch_count=0, strength_score=strength,
                freshness_score=1.0, sweep_side="BELOW",
                is_active=True, bars_since_formed=len(self.bars) - idx,
                reason_code=f"SWING_L@{idx}",
            ))

    # --- Equal Highs/Lows ---

    def _add_equal_levels(self, tolerance_pct: float = 0.0005):
        """Detect equal highs and lows (double tops/bottoms)."""
        swings_h = [(l.price, l.reason_code) for l in self.levels
                    if l.level_type == "SWING_H"]
        swings_l = [(l.price, l.reason_code) for l in self.levels
                    if l.level_type == "SWING_L"]

        if len(swings_h) >= 2:
            for i in range(len(swings_h)):
                for j in range(i + 1, len(swings_h)):
                    diff = abs(swings_h[i][0] - swings_h[j][0])
                    avg = (swings_h[i][0] + swings_h[j][0]) / 2
                    if avg > 0 and diff / avg < tolerance_pct:
                        self.levels.append(LiquidityLevel(
                            level_type="EQH", price=swings_h[i][0],
                            touch_count=2, strength_score=0.85,
                            freshness_score=0.9, sweep_side="ABOVE",
                            reason_code=f"EQH_{swings_h[i][1]}_{swings_h[j][1]}",
                        ))

        if len(swings_l) >= 2:
            for i in range(len(swings_l)):
                for j in range(i + 1, len(swings_l)):
                    diff = abs(swings_l[i][0] - swings_l[j][0])
                    avg = (swings_l[i][0] + swings_l[j][0]) / 2
                    if avg > 0 and diff / avg < tolerance_pct:
                        self.levels.append(LiquidityLevel(
                            level_type="EQL", price=swings_l[i][0],
                            touch_count=2, strength_score=0.85,
                            freshness_score=0.9, sweep_side="BELOW",
                            reason_code=f"EQL_{swings_l[i][1]}_{swings_l[j][1]}",
                        ))

    # --- Round numbers ---

    def _add_round_numbers(self, tolerance: float = 0.005):
        """Add round number levels near current price."""
        if not self.bars:
            return
        current = self.bars[-1]["close"]

        # Determine step size from price level
        if current < 10:  # FX pairs like EURUSD ~1.08
            steps = [0.01, 0.005]
            precision = 4
        elif current < 200:  # USDJPY ~150, etc.
            steps = [1.0, 0.5]
            precision = 2
        elif current < 1000:  # Indices, etc.
            steps = [10.0, 5.0]
            precision = 1
        else:  # XAUUSD > 1000
            steps = [100.0, 50.0]
            precision = 0

        spread = current * tolerance
        low = current - spread
        high = current + spread
        seen = set()

        for step in steps:
            level = round(low / step) * step
            while level <= high:
                if level >= low:
                    price = round(level, precision)
                    if price not in seen:
                        seen.add(price)
                        side = "ABOVE" if price > current else "BELOW" if price < current else ""
                        strength = 0.7 if step == steps[0] else 0.5
                        self.levels.append(LiquidityLevel(
                            level_type="ROUND", price=price,
                            touch_count=0, strength_score=strength,
                            freshness_score=0.7, sweep_side=side,
                            reason_code=f"ROUND_{price}",
                        ))
                level += step

    # --- Scoring ---

    def _score_levels(self):
        """Recalculate strength and freshness scores."""
        if not self.bars:
            return
        total_bars = len(self.bars)
        current_close = self.bars[-1]["close"]

        for lvl in self.levels:
            # Freshness: newer levels score higher
            lvl.freshness_score = max(0.0, 1.0 - lvl.bars_since_formed / total_bars)

            # Proximity to current price: closer = more relevant
            if current_close > 0:
                prox = abs(lvl.price - current_close) / current_close
                if prox < 0.01:  # within 1%
                    lvl.strength_score *= 1.2
                elif prox < 0.02:  # within 2%
                    lvl.strength_score *= 1.0
                else:
                    lvl.strength_score *= 0.5  # far away = less relevant

            # Clamp
            lvl.strength_score = min(1.0, max(0.0, lvl.strength_score))
