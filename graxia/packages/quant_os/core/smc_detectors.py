"""Shared SMC / ICT detector library.

This module implements the six foundational detectors from
MULTI_ASSET_REDESIGN_PLAN_v3.md §3.2 plus the composite concepts in §3.1.
It is deliberately shared: the ML feature pipeline and the rule-based
signal layer both import from here. Do NOT create a second implementation
of swing-point detection "for the rules engine".

Design notes:
- Inputs are pandas DataFrames with columns: open, high, low, close, volume.
- A ``time`` column or DatetimeIndex is required for killzone / session logic.
- Every detector is lookahead-safe: fractal highs/lows are only marked once
  the confirming future bar has closed (k-bar lag). No detector uses the
  still-forming bar's close as an input for a signal on that same bar.
- Functions return BOTH (a) numeric feature columns suitable for ML and
  (b) event objects for the rule-based layer, bundled in a small result
  container.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd


# ── Result containers ────────────────────────────────────────────────────────

@dataclass
class SwingEvent:
    bar_idx: int
    timestamp: datetime
    price: float
    direction: str  # "high" | "low"


@dataclass
class SweepEvent:
    direction: str  # "bearish" | "bullish"
    level: float
    trigger_bar_idx: int
    trigger_timestamp: datetime
    magnitude: float  # ATR-normalized excess beyond the level
    reclaimed_bar_idx: Optional[int] = None


@dataclass
class OrderBlock:
    bar_idx: int
    timestamp: datetime
    direction: str  # "bullish" | "bearish"
    top: float
    bottom: float
    mitigated: bool = False
    mitigation_bar_idx: Optional[int] = None


@dataclass
class FairValueGap:
    start_bar_idx: int
    end_bar_idx: int
    timestamp: datetime
    direction: str  # "bullish" | "bearish"
    top: float
    bottom: float
    filled: bool = False
    fill_bar_idx: Optional[int] = None


@dataclass
class StructureEvent:
    bar_idx: int
    timestamp: datetime
    event: str  # "BOS_up" | "BOS_down" | "CHoCH_up" | "CHoCH_down"
    level: float


@dataclass
class LiquidityPool:
    level: float
    direction: str  # "high" | "low"
    strength: int
    oldest_bar_idx: int
    newest_bar_idx: int
    age_bars: int


# ── Foundational detector: swing points ──────────────────────────────────────

def detect_fractals(df: pd.DataFrame, k: int = 2) -> pd.DataFrame:
    """Mark fractal swing highs/lows with a k-bar lookforward lag.

    fractal_high[i] = True iff high[i] > high[i-k..i-1] and high[i] > high[i+1..i+k]
    fractal_low[i]  = True iff low[i]  < low[i-k..i-1]  and low[i]  < low[i+1..i+k]

    The event is only *known* once bar i+k has closed. This function returns
    the events at bar i+k (the confirmation bar) to make the lag explicit.
    Callers that need a live signal timestamp should use the confirmation bar,
    not bar i.

    Returns DataFrame with columns:
        swing_high_price, swing_low_price, swing_high_event, swing_low_event
    """
    n = len(df)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()

    swing_high = np.zeros(n, dtype=bool)
    swing_low = np.zeros(n, dtype=bool)

    for i in range(k, n - k):
        if high[i] > high[i - k : i].max() and high[i] > high[i + 1 : i + k + 1].max():
            swing_high[i] = True
        if low[i] < low[i - k : i].min() and low[i] < low[i + 1 : i + k + 1].min():
            swing_low[i] = True

    high_price = np.where(swing_high, high, np.nan)
    low_price = np.where(swing_low, low, np.nan)

    # Build events with lag-adjusted timestamp (confirmation bar i+k)
    idx = df.index
    time_col = _get_time_column(df)
    events: List[SwingEvent] = []
    for i in np.where(swing_high)[0]:
        confirm = min(i + k, n - 1)
        events.append(
            SwingEvent(
                bar_idx=i,
                timestamp=time_col.iloc[confirm],
                price=float(high[i]),
                direction="high",
            )
        )
    for i in np.where(swing_low)[0]:
        confirm = min(i + k, n - 1)
        events.append(
            SwingEvent(
                bar_idx=i,
                timestamp=time_col.iloc[confirm],
                price=float(low[i]),
                direction="low",
            )
        )
    events.sort(key=lambda e: e.bar_idx)

    out = pd.DataFrame(
        {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "swing_high_price": high_price,
            "swing_low_price": low_price,
        },
        index=idx,
    )
    out.attrs["events"] = events
    return out


# ── Foundational detector: liquidity sweep ───────────────────────────────────

def detect_sweeps(
    df: pd.DataFrame,
    fractals: pd.DataFrame,
    sweep_max_atr: float = 0.5,
    max_reclaim_bars: int = 3,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Detect liquidity sweeps of prior fractal highs/lows.

    For each fractal high H at bar j:
      - price must pierce H.price within M bars,
      - then close back below H.price,
      - and the excess beyond H must be < sweep_max_atr * ATR.

    Returns DataFrame with columns:
        sweep_bearish_flag, sweep_bullish_flag, sweep_magnitude,
        bars_since_sweep
    plus a list of SweepEvent in .attrs["events"].
    """
    n = len(df)
    atr = _atr(df, atr_period)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    time_col = _get_time_column(df)

    bearish = np.zeros(n, dtype=bool)
    bullish = np.zeros(n, dtype=bool)
    magnitude = np.zeros(n, dtype=float)
    bars_since = np.full(n, np.nan, dtype=float)

    events: List[SweepEvent] = []

    highs = fractals[fractals["swing_high"]].index.to_numpy()
    lows = fractals[fractals["swing_low"]].index.to_numpy()

    # Bearish sweeps of prior highs
    for j in highs:
        j = int(j)
        level = high[j]
        for i in range(j + 1, min(j + max_reclaim_bars + 1, n)):
            excess = high[i] - level
            if excess > 0 and excess < sweep_max_atr * atr[i] and close[i] < level:
                bearish[i] = True
                magnitude[i] = excess / atr[i] if atr[i] > 0 else 0.0
                bars_since[i] = i - j
                events.append(
                    SweepEvent(
                        direction="bearish",
                        level=float(level),
                        trigger_bar_idx=i,
                        trigger_timestamp=time_col.iloc[i],
                        magnitude=float(magnitude[i]),
                        reclaimed_bar_idx=i,
                    )
                )
                break

    # Bullish sweeps of prior lows
    for j in lows:
        j = int(j)
        level = low[j]
        for i in range(j + 1, min(j + max_reclaim_bars + 1, n)):
            excess = level - low[i]
            if excess > 0 and excess < sweep_max_atr * atr[i] and close[i] > level:
                bullish[i] = True
                magnitude[i] = excess / atr[i] if atr[i] > 0 else 0.0
                bars_since[i] = i - j
                events.append(
                    SweepEvent(
                        direction="bullish",
                        level=float(level),
                        trigger_bar_idx=i,
                        trigger_timestamp=time_col.iloc[i],
                        magnitude=float(magnitude[i]),
                        reclaimed_bar_idx=i,
                    )
                )
                break

    out = pd.DataFrame(
        {
            "sweep_bearish_flag": bearish,
            "sweep_bullish_flag": bullish,
            "sweep_magnitude": magnitude,
            "bars_since_sweep": bars_since,
        },
        index=df.index,
    )
    out.attrs["events"] = events
    return out


# ── Foundational detector: order block ───────────────────────────────────────

def detect_order_blocks(
    df: pd.DataFrame,
    fractals: pd.DataFrame,
    impulse_min_atr: float = 1.0,
    max_lookback_bars: int = 5,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Detect unmitigated order blocks.

    For each structure-breaking impulsive move, the last opposing-color candle
    before the move becomes an order block. We use the full candle range
    [low, high] for the zone and document that choice explicitly.

    Returns DataFrame with columns:
        ob_distance_atr, ob_age_bars, ob_strength
    plus list of OrderBlock in .attrs["events"].
    """
    n = len(df)
    atr = _atr(df, atr_period)
    open_ = df["open"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    time_col = _get_time_column(df)

    obs: List[OrderBlock] = []

    swing_highs = fractals[fractals["swing_high"]].index.to_numpy()
    swing_lows = fractals[fractals["swing_low"]].index.to_numpy()

    # Helper: find the last opposing candle before a break
    def candle_color(idx: int) -> str:
        return "green" if close[idx] >= open_[idx] else "red"

    # Bearish move: break below a swing low
    for low_idx in swing_lows:
        low_idx = int(low_idx)
        level = low[low_idx]
        for i in range(low_idx + 1, min(low_idx + max_lookback_bars + 1, n)):
            if close[i] < level - impulse_min_atr * atr[i]:
                # Last green candle before the break
                for j in range(i - 1, max(i - max_lookback_bars, -1), -1):
                    if candle_color(j) == "green":
                        obs.append(
                            OrderBlock(
                                bar_idx=j,
                                timestamp=time_col.iloc[j],
                                direction="bullish",
                                top=float(high[j]),
                                bottom=float(low[j]),
                            )
                        )
                        break
                break

    # Bullish move: break above a swing high
    for high_idx in swing_highs:
        high_idx = int(high_idx)
        level = high[high_idx]
        for i in range(high_idx + 1, min(high_idx + max_lookback_bars + 1, n)):
            if close[i] > level + impulse_min_atr * atr[i]:
                # Last red candle before the break
                for j in range(i - 1, max(i - max_lookback_bars, -1), -1):
                    if candle_color(j) == "red":
                        obs.append(
                            OrderBlock(
                                bar_idx=j,
                                timestamp=time_col.iloc[j],
                                direction="bearish",
                                top=float(high[j]),
                                bottom=float(low[j]),
                            )
                        )
                        break
                break

    # Mitigation tracking: price closes back inside the zone
    for ob in obs:
        for i in range(ob.bar_idx + 1, n):
            if ob.bottom <= close[i] <= ob.top:
                ob.mitigated = True
                ob.mitigation_bar_idx = i
                break

    # Feature columns: distance from current close to nearest unmitigated OB
    ob_distance = np.full(n, np.nan, dtype=float)
    ob_age = np.full(n, np.nan, dtype=float)
    ob_strength = np.full(n, np.nan, dtype=float)

    for i in range(n):
        active = [ob for ob in obs if ob.bar_idx < i and not ob.mitigated_at(i)]
        if active:
            nearest = min(
                active,
                key=lambda ob: min(
                    abs(close[i] - ob.top), abs(close[i] - ob.bottom)
                ),
            )
            dist = min(abs(close[i] - nearest.top), abs(close[i] - nearest.bottom))
            ob_distance[i] = dist / atr[i] if atr[i] > 0 else dist
            ob_age[i] = i - nearest.bar_idx
            # Strength: inverse normalized distance to zone center
            center = (nearest.top + nearest.bottom) / 2.0
            half_width = abs(nearest.top - nearest.bottom) / 2.0 + 1e-9
            ob_strength[i] = max(0.0, 1.0 - abs(close[i] - center) / half_width)

    out = pd.DataFrame(
        {
            "ob_distance_atr": ob_distance,
            "ob_age_bars": ob_age,
            "ob_strength": ob_strength,
        },
        index=df.index,
    )
    out.attrs["events"] = obs
    return out


# Monkey-patch mitigation helper (cleaner than inline method)
def _mitigated_at(self: OrderBlock, bar_idx: int) -> bool:
    return self.mitigated and self.mitigation_bar_idx is not None and self.mitigation_bar_idx <= bar_idx


OrderBlock.mitigated_at = _mitigated_at  # type: ignore[method-assign]


# ── Foundational detector: fair value gap ────────────────────────────────────

def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Detect bullish and bearish fair value gaps.

    Bullish FVG: high[i-1] < low[i+1]  -> gap = [high[i-1], low[i+1]]
    Bearish FVG: low[i-1] > high[i+1]  -> gap = [high[i+1], low[i-1]]

    A gap is filled the first time price trades through the full range.

    Returns DataFrame with columns:
        fvg_nearest_distance_atr, fvg_nearest_size_atr, fvg_inside_flag
    plus list of FairValueGap in .attrs["events"].
    """
    n = len(df)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    atr = _atr(df, 14)
    time_col = _get_time_column(df)

    fvgs: List[FairValueGap] = []

    for i in range(1, n - 1):
        if high[i - 1] < low[i + 1]:
            fvgs.append(
                FairValueGap(
                    start_bar_idx=i - 1,
                    end_bar_idx=i + 1,
                    timestamp=time_col.iloc[i],
                    direction="bullish",
                    top=float(low[i + 1]),
                    bottom=float(high[i - 1]),
                )
            )
        elif low[i - 1] > high[i + 1]:
            fvgs.append(
                FairValueGap(
                    start_bar_idx=i - 1,
                    end_bar_idx=i + 1,
                    timestamp=time_col.iloc[i],
                    direction="bearish",
                    top=float(low[i - 1]),
                    bottom=float(high[i + 1]),
                )
            )

    # Fill detection
    for fvg in fvgs:
        for j in range(fvg.end_bar_idx + 1, n):
            if (
                (fvg.direction == "bullish" and low[j] <= fvg.bottom and high[j] >= fvg.top)
                or (fvg.direction == "bearish" and high[j] >= fvg.top and low[j] <= fvg.bottom)
            ):
                fvg.filled = True
                fvg.fill_bar_idx = j
                break

    # Feature columns
    dist = np.full(n, np.nan, dtype=float)
    size = np.full(n, np.nan, dtype=float)
    inside = np.zeros(n, dtype=bool)

    for i in range(n):
        active = [f for f in fvgs if f.end_bar_idx < i and not f.filled_at(i)]
        if active:
            nearest = min(
                active,
                key=lambda f: min(abs(close[i] - f.top), abs(close[i] - f.bottom)),
            )
            d = min(abs(close[i] - nearest.top), abs(close[i] - nearest.bottom))
            dist[i] = d / atr[i] if atr[i] > 0 else d
            sz = abs(nearest.top - nearest.bottom)
            size[i] = sz / atr[i] if atr[i] > 0 else sz
            inside[i] = nearest.bottom <= close[i] <= nearest.top

    out = pd.DataFrame(
        {
            "fvg_nearest_distance_atr": dist,
            "fvg_nearest_size_atr": size,
            "fvg_inside_flag": inside,
        },
        index=df.index,
    )
    out.attrs["events"] = fvgs
    return out


def _filled_at(self: FairValueGap, bar_idx: int) -> bool:
    return self.filled and self.fill_bar_idx is not None and self.fill_bar_idx <= bar_idx


FairValueGap.filled_at = _filled_at  # type: ignore[method-assign]


# ── Foundational detector: market structure shift (BOS / CHoCH) ──────────────

def detect_structure(
    df: pd.DataFrame,
    fractals: pd.DataFrame,
) -> pd.DataFrame:
    """Detect BOS (break of structure) and CHoCH (change of character).

    Trend is defined by the most recent higher-high / higher-low (up) or
    lower-high / lower-low (down). A break beyond the last swing high in an
    up-trend is BOS_up; a break beyond the last swing high in a down-trend is
    CHoCH_up; symmetric for lows.

    Returns DataFrame with columns:
        structure_state, bars_since_bos_choch, structure_event_flag
    plus list of StructureEvent in .attrs["events"].
    """
    n = len(df)
    time_col = _get_time_column(df)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()

    state = np.full(n, "undefined", dtype=object)
    bars_since = np.full(n, np.nan, dtype=float)
    event_flag = np.zeros(n, dtype=bool)

    events: List[StructureEvent] = []

    # Build ordered list of swing points
    highs = fractals[fractals["swing_high"]].index.to_numpy()
    lows = fractals[fractals["swing_low"]].index.to_numpy()
    points = sorted(
        [(int(i), "high", high[int(i)]) for i in highs]
        + [(int(i), "low", low[int(i)]) for i in lows]
    )

    if len(points) < 2:
        out = pd.DataFrame(
            {
                "structure_state": state,
                "bars_since_bos_choch": bars_since,
                "structure_event_flag": event_flag,
            },
            index=df.index,
        )
        out.attrs["events"] = events
        return out

    trend = "undefined"
    last_high_idx = points[0][0] if points[0][1] == "high" else None
    last_low_idx = points[0][0] if points[0][1] == "low" else None

    for idx, direction, price in points[1:]:
        if direction == "high":
            if last_high_idx is None:
                last_high_idx = idx
                continue
            last_high_price = high[last_high_idx]
            if price > last_high_price:
                if trend == "up":
                    event = "BOS_up"
                elif trend == "down":
                    event = "CHoCH_up"
                    trend = "up"
                else:
                    event = "CHoCH_up"
                    trend = "up"
                event_flag[idx] = True
                state[idx] = trend
                bars_since[idx] = 0.0
                events.append(
                    StructureEvent(
                        bar_idx=idx,
                        timestamp=time_col.iloc[idx],
                        event=event,
                        level=float(price),
                    )
                )
            last_high_idx = idx
        else:  # low
            if last_low_idx is None:
                last_low_idx = idx
                continue
            last_low_price = low[last_low_idx]
            if price < last_low_price:
                if trend == "down":
                    event = "BOS_down"
                elif trend == "up":
                    event = "CHoCH_down"
                    trend = "down"
                else:
                    event = "CHoCH_down"
                    trend = "down"
                event_flag[idx] = True
                state[idx] = trend
                bars_since[idx] = 0.0
                events.append(
                    StructureEvent(
                        bar_idx=idx,
                        timestamp=time_col.iloc[idx],
                        event=event,
                        level=float(price),
                    )
                )
            last_low_idx = idx

    # Forward-fill state and bars_since
    last_state = "undefined"
    last_event_bar: Optional[int] = None
    for i in range(n):
        if state[i] != "undefined":
            last_state = state[i]
        if event_flag[i]:
            last_event_bar = i
        state[i] = last_state
        if last_event_bar is not None:
            bars_since[i] = i - last_event_bar

    out = pd.DataFrame(
        {
            "structure_state": state,
            "bars_since_bos_choch": bars_since,
            "structure_event_flag": event_flag,
        },
        index=df.index,
    )
    out.attrs["events"] = events
    return out


# ── Foundational detector: equal highs / lows (liquidity pools) ──────────────

def detect_liquidity_pools(
    df: pd.DataFrame,
    fractals: pd.DataFrame,
    tolerance_atr: float = 0.3,
    lookback_bars: int = 50,
    min_cluster_size: int = 2,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Detect clusters of equal highs/lows (liquidity pools).

    A pool is a group of >= min_cluster_size fractal highs (or lows) whose
    prices fall within tolerance_atr * ATR of each other.

    Returns DataFrame with columns:
        pool_nearest_distance_atr, pool_age_bars, pool_strength
    plus list of LiquidityPool in .attrs["events"].
    """
    n = len(df)
    atr = _atr(df, atr_period)
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    time_col = _get_time_column(df)

    pools: List[LiquidityPool] = []

    highs = fractals[fractals["swing_high"]].index.to_numpy()
    lows = fractals[fractals["swing_low"]].index.to_numpy()

    def build_pools(idxs: np.ndarray, direction: str) -> List[LiquidityPool]:
        prices = np.array([high[i] if direction == "high" else low[i] for i in idxs])
        used = np.zeros(len(idxs), dtype=bool)
        result: List[LiquidityPool] = []
        for i, idx in enumerate(idxs):
            if used[i]:
                continue
            # Only look back within lookback_bars
            candidates = [
                (j, idxs[j])
                for j in range(i)
                if not used[j] and idx - idxs[j] <= lookback_bars
            ]
            cluster = [i] + [
                j for j, _ in candidates if abs(prices[j] - prices[i]) <= tolerance_atr * atr[idx]
            ]
            if len(cluster) >= min_cluster_size:
                for j in cluster:
                    used[j] = True
                levels = [prices[j] for j in cluster]
                result.append(
                    LiquidityPool(
                        level=float(np.mean(levels)),
                        direction=direction,
                        strength=len(cluster),
                        oldest_bar_idx=int(idxs[cluster[-1]]),
                        newest_bar_idx=int(idx),
                        age_bars=int(idx - idxs[cluster[-1]]),
                    )
                )
        return result

    pools.extend(build_pools(highs, "high"))
    pools.extend(build_pools(lows, "low"))

    dist = np.full(n, np.nan, dtype=float)
    age = np.full(n, np.nan, dtype=float)
    strength = np.full(n, np.nan, dtype=float)

    for i in range(n):
        relevant = [p for p in pools if p.newest_bar_idx < i]
        if relevant:
            nearest = min(relevant, key=lambda p: abs(close[i] - p.level))
            d = abs(close[i] - nearest.level)
            dist[i] = d / atr[i] if atr[i] > 0 else d
            age[i] = i - nearest.newest_bar_idx
            strength[i] = nearest.strength

    out = pd.DataFrame(
        {
            "pool_nearest_distance_atr": dist,
            "pool_age_bars": age,
            "pool_strength": strength,
        },
        index=df.index,
    )
    out.attrs["events"] = pools
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Return ATR series as numpy array."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    atr = pd.Series(tr).rolling(window=period, min_periods=1).mean().to_numpy()
    return atr


def _get_time_column(df: pd.DataFrame) -> pd.Series:
    if "time" in df.columns:
        return pd.to_datetime(df["time"])
    if isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(df.index, index=df.index)
    raise ValueError("DataFrame must have a 'time' column or DatetimeIndex")


# ── Composite: Killzones / session schedule (§7) ─────────────────────────────

class Killzone(str, Enum):
    ASIAN = "asian"
    LONDON_OPEN = "london_open"
    LONDON_NY_OVERLAP = "overlap"
    NY_OPEN = "ny_open"
    NY_PM = "ny_pm"
    CRYPTO_FUNDING = "crypto_funding"
    OUTSIDE = "outside"


# UTC boundaries from plan §7
KILLZONE_SCHEDULE: List[tuple[str, time, time]] = [
    (Killzone.ASIAN, time(23, 0), time(8, 0)),
    (Killzone.LONDON_OPEN, time(7, 0), time(10, 0)),
    (Killzone.LONDON_NY_OVERLAP, time(12, 0), time(17, 0)),
    (Killzone.NY_OPEN, time(12, 0), time(15, 0)),
    (Killzone.NY_PM, time(18, 0), time(21, 0)),
]

CRYPTO_FUNDING_TIMES = [time(0, 0), time(8, 0), time(16, 0)]


def _in_window(t: time, start: time, end: time) -> bool:
    if start < end:
        return start <= t < end
    # Wraps midnight (e.g. Asian 23:00-08:00)
    return t >= start or t < end


def classify_killzone(timestamps: pd.Series) -> pd.DataFrame:
    """Classify each timestamp into the killzone schedule from §7.

    Returns DataFrame with columns:
        killzone_primary, is_london_open, is_ny_open, is_overlap, is_crypto_funding
    """
    times = timestamps.dt.time
    primary = []
    is_london_open = []
    is_ny_open = []
    is_overlap = []
    is_funding = []

    for t in times:
        kz = Killzone.OUTSIDE
        if _in_window(t, time(7, 0), time(10, 0)):
            kz = Killzone.LONDON_OPEN
        elif _in_window(t, time(12, 0), time(17, 0)):
            kz = Killzone.LONDON_NY_OVERLAP
        elif _in_window(t, time(18, 0), time(21, 0)):
            kz = Killzone.NY_PM
        elif _in_window(t, time(23, 0), time(8, 0)):
            kz = Killzone.ASIAN
        primary.append(kz)
        is_london_open.append(kz == Killzone.LONDON_OPEN)
        is_ny_open.append(kz == Killzone.NY_OPEN or _in_window(t, time(12, 0), time(15, 0)))
        is_overlap.append(kz == Killzone.LONDON_NY_OVERLAP)
        is_funding.append(any(t.hour == ft.hour and t.minute == ft.minute for ft in CRYPTO_FUNDING_TIMES))

    return pd.DataFrame(
        {
            "killzone_primary": primary,
            "is_london_open": is_london_open,
            "is_ny_open": is_ny_open,
            "is_overlap": is_overlap,
            "is_crypto_funding": is_funding,
        },
        index=timestamps.index,
    )


# ── Composite: Optimal Trade Entry (OTE) ─────────────────────────────────────

def detect_ote(
    df: pd.DataFrame,
    fractals: pd.DataFrame,
    fib_low: float = 0.62,
    fib_high: float = 0.79,
) -> pd.DataFrame:
    """Detect position within the 62-79% Fibonacci retracement of the latest impulsive leg.

    Uses the most recent confirmed swing high and swing low. Returns columns:
        ote_in_band, ote_retracement_pct
    """
    n = len(df)
    close = df["close"].to_numpy()
    in_band = np.zeros(n, dtype=bool)
    retracement = np.full(n, np.nan, dtype=float)

    high_prices = fractals["swing_high_price"].to_numpy()
    low_prices = fractals["swing_low_price"].to_numpy()

    last_high = np.full(n, np.nan)
    last_low = np.full(n, np.nan)
    cur_high = np.nan
    cur_low = np.nan
    for i in range(n):
        if not np.isnan(high_prices[i]):
            cur_high = high_prices[i]
        if not np.isnan(low_prices[i]):
            cur_low = low_prices[i]
        last_high[i] = cur_high
        last_low[i] = cur_low

    for i in range(n):
        h = last_high[i]
        l = last_low[i]
        if np.isnan(h) or np.isnan(l) or h == l:
            continue
        c = close[i]
        # Retracement of the down-leg h->l measured from the high
        if c >= l and c <= h:
            retracement[i] = (h - c) / (h - l)
            in_band[i] = fib_low <= retracement[i] <= fib_high

    return pd.DataFrame(
        {
            "ote_in_band": in_band,
            "ote_retracement_pct": retracement,
        },
        index=df.index,
    )


# ── Composite: Liquidity Void ────────────────────────────────────────────────

def detect_liquidity_voids(
    df: pd.DataFrame,
    lookback: int = 5,
    min_void_size_atr: float = 1.5,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Detect runs of small-bodied, one-directional candles (liquidity voids).

    A void is a window of ``lookback`` bars where the cumulative body is small
    relative to the range, indicating low two-sided trading. Returns columns:
        liquidity_void_flag, liquidity_void_size_atr, liquidity_void_age_bars
    """
    n = len(df)
    open_ = df["open"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    atr = _atr(df, atr_period)

    body = np.abs(close - open_)
    range_ = high - low

    void_flag = np.zeros(n, dtype=bool)
    void_size = np.zeros(n, dtype=float)
    void_age = np.full(n, np.nan, dtype=float)

    for i in range(lookback, n):
        window_range = range_[i - lookback : i + 1].sum()
        window_body = body[i - lookback : i + 1].sum()
        if window_range > 0 and window_body / window_range < 0.3:
            size = window_range / atr[i] if atr[i] > 0 else window_range
            if size >= min_void_size_atr:
                void_flag[i] = True
                void_size[i] = size

    last_void: Optional[int] = None
    for i in range(n):
        if void_flag[i]:
            last_void = i
        if last_void is not None:
            void_age[i] = i - last_void

    return pd.DataFrame(
        {
            "liquidity_void_flag": void_flag,
            "liquidity_void_size_atr": void_size,
            "liquidity_void_age_bars": void_age,
        },
        index=df.index,
    )


# ── Composite: Mitigation block + Inversion FVG ──────────────────────────────

def detect_mitigation_and_inversion(
    df: pd.DataFrame,
    obs: List[OrderBlock],
    fvgs: List[FairValueGap],
    atr_period: int = 14,
) -> pd.DataFrame:
    """Compute mitigation depth for OBs and flag inversion FVGs.

    Mitigation depth = how far price retraced into the impulsive leg
    before touching the OB zone. Inversion FVG = a previously filled FVG
    that is now being re-tested from the opposite side.

    Returns columns:
        ob_mitigation_depth, inversion_fvg_flag
    """
    n = len(df)
    atr = _atr(df, atr_period)
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()

    mitigation_depth = np.full(n, np.nan, dtype=float)
    for ob in obs:
        # Find the extreme of the move that created the OB (swing before OB)
        if ob.bar_idx <= 0:
            continue
        if ob.direction == "bullish":
            move_low = float(df["low"].iloc[max(0, ob.bar_idx - 5) : ob.bar_idx + 1].min())
            move_high = ob.top
            for i in range(ob.bar_idx + 1, n):
                if ob.mitigated_at(i):
                    depth = (move_high - close[i]) / (move_high - move_low) if move_high != move_low else 0.0
                    mitigation_depth[i] = depth
                    break
        else:
            move_high = float(df["high"].iloc[max(0, ob.bar_idx - 5) : ob.bar_idx + 1].max())
            move_low = ob.bottom
            for i in range(ob.bar_idx + 1, n):
                if ob.mitigated_at(i):
                    depth = (close[i] - move_low) / (move_high - move_low) if move_high != move_low else 0.0
                    mitigation_depth[i] = depth
                    break

    inversion_flag = np.zeros(n, dtype=bool)
    for fvg in fvgs:
        if not fvg.filled:
            continue
        fill_idx = fvg.fill_bar_idx
        if fill_idx is None:
            continue
        # After fill, if price returns to the zone from the opposite side
        for i in range(fill_idx + 1, n):
            if fvg.direction == "bullish":
                # Was support; now resistance if price approaches from below and fails
                if high[i] >= fvg.bottom and close[i] < fvg.bottom:
                    inversion_flag[i] = True
                    break
            else:
                if low[i] <= fvg.top and close[i] > fvg.top:
                    inversion_flag[i] = True
                    break

    return pd.DataFrame(
        {
            "ob_mitigation_depth": mitigation_depth,
            "inversion_fvg_flag": inversion_flag,
        },
        index=df.index,
    )


# ── Composite: Judas Swing (Power-of-Three manipulation leg) ─────────────────

def detect_judas_swings(
    df: pd.DataFrame,
    sweeps: pd.DataFrame,
    killzones: pd.DataFrame,
    max_minutes_from_open: int = 60,
) -> pd.DataFrame:
    """Flag sweeps that occur within the opening window of London or NY killzones.

    A Judas Swing is a liquidity sweep near a major session open that quickly
    reverses — the "manipulation" leg of Power of Three. Returns columns:
        judas_swing_flag, judas_direction
    """
    n = len(df)
    time_col = _get_time_column(df)
    flag = np.zeros(n, dtype=bool)
    direction = np.full(n, "", dtype=object)

    # Determine open-boundary minutes for each bar (minutes since session start)
    minutes = time_col.dt.hour * 60 + time_col.dt.minute

    in_open_window = (
        (killzones["is_london_open"] & (minutes >= 7 * 60) & (minutes < 7 * 60 + max_minutes_from_open))
        | (killzones["is_ny_open"] & (minutes >= 12 * 60) & (minutes < 12 * 60 + max_minutes_from_open))
    )

    for i in range(n):
        if not in_open_window.iloc[i]:
            continue
        if sweeps.loc[i, "sweep_bearish_flag"]:
            flag[i] = True
            direction[i] = "bearish"
        elif sweeps.loc[i, "sweep_bullish_flag"]:
            flag[i] = True
            direction[i] = "bullish"

    return pd.DataFrame(
        {
            "judas_swing_flag": flag,
            "judas_direction": direction,
        },
        index=df.index,
    )


# ── Composite: Wyckoff accumulation / distribution schematic ─────────────────

def detect_wyckoff_events(
    df: pd.DataFrame,
    lookback: int = 20,
    spring_threshold_atr: float = 0.5,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Slower-timeframe Wyckoff-style spring/upthrust detection.

    Identifies range-bound regimes and false breakdowns/breakouts. Designed
    as an HTF bias filter, not a standalone trigger.

    Returns columns:
        wyckoff_range_bound, wyckoff_spring_flag, wyckoff_upthrust_flag
    """
    n = len(df)
    atr = _atr(df, atr_period)
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()

    range_bound = np.zeros(n, dtype=bool)
    spring = np.zeros(n, dtype=bool)
    upthrust = np.zeros(n, dtype=bool)

    for i in range(lookback, n):
        window_high = high[i - lookback : i + 1].max()
        window_low = low[i - lookback : i + 1].min()
        # Support/resistance for spring/upthrust is defined by prior bars only
        prior_low = low[i - lookback : i].min() if i - lookback < i else window_low
        prior_high = high[i - lookback : i].max() if i - lookback < i else window_high
        range_size = window_high - window_low
        if range_size <= 0:
            continue
        # Range-bound if recent ATR is a small fraction of the total range
        avg_atr = atr[i - lookback : i + 1].mean()
        if avg_atr > 0 and range_size / avg_atr < lookback * 0.4:
            range_bound[i] = True

        # Spring: close back above prior support after piercing below it
        if (
            low[i] < prior_low - spring_threshold_atr * atr[i]
            and close[i] > prior_low - spring_threshold_atr * atr[i]
        ):
            spring[i] = True
        # Upthrust: close back below prior resistance after piercing above it
        if (
            high[i] > prior_high + spring_threshold_atr * atr[i]
            and close[i] < prior_high + spring_threshold_atr * atr[i]
        ):
            upthrust[i] = True

    return pd.DataFrame(
        {
            "wyckoff_range_bound": range_bound,
            "wyckoff_spring_flag": spring,
            "wyckoff_upthrust_flag": upthrust,
        },
        index=df.index,
    )


# ── Composite: Volume Profile (POC / VAH / VAL / HVN / LVN) ──────────────────

def volume_profile_features(
    df: pd.DataFrame,
    lookback: int = 50,
    value_area_pct: float = 0.70,
) -> pd.DataFrame:
    """Rolling volume profile features.

    POC = price level with highest volume in the lookback window.
    Value Area = price range containing ``value_area_pct`` of total volume.
    HVN/LVN are approximated by distance to POC relative to value area width.

    Returns columns:
        vp_poc_distance_atr, vp_inside_value_area, vp_hvn_proximity
    """
    n = len(df)
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()
    atr = _atr(df, 14)

    poc_dist = np.full(n, np.nan, dtype=float)
    inside_va = np.zeros(n, dtype=bool)
    hvn_prox = np.zeros(n, dtype=float)

    for i in range(lookback, n):
        sub = df.iloc[i - lookback : i + 1]
        vol_by_price = sub.groupby(np.round(sub["close"], 6))["volume"].sum()
        if vol_by_price.empty:
            continue
        poc = vol_by_price.idxmax()
        total_vol = vol_by_price.sum()
        sorted_prices = vol_by_price.sort_values(ascending=False)
        cum_pct = sorted_prices.cumsum() / total_vol
        va_prices = sorted_prices[cum_pct <= value_area_pct].index
        if len(va_prices) == 0:
            continue
        vah = float(va_prices.max())
        val = float(va_prices.min())

        poc_dist[i] = abs(close[i] - poc) / atr[i] if atr[i] > 0 else abs(close[i] - poc)
        inside_va[i] = val <= close[i] <= vah
        center = (vah + val) / 2.0
        half_width = (vah - val) / 2.0 + 1e-9
        hvn_prox[i] = max(0.0, 1.0 - abs(close[i] - center) / half_width)

    return pd.DataFrame(
        {
            "vp_poc_distance_atr": poc_dist,
            "vp_inside_value_area": inside_va,
            "vp_hvn_proximity": hvn_prox,
        },
        index=df.index,
    )
