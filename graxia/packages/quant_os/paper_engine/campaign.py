"""
Campaign definitions — what to run, with what params.
Each campaign = 1 strategy × 1 symbol × 1 timeframe × 1 param set.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

BASE = Path(__file__).resolve().parent.parent
CAMPAIGNS_DIR = BASE / "paper_engine" / "campaigns"
COST_CALIBRATION_PATH = BASE / "config" / "cost_calibration.json"

# Spread bps lookup from cost_calibration.json (Pepperstone Razor, MEASURED)
# Fallback estimates for assets not in calibration file
_SPREAD_BPS_ESTIMATES = {
    "AUDUSD": 0.1,   # forex Razor, similar to GBPUSD
    "NAS100": 1.0,   # index CFD, not measured
    "US30": 0.5,     # index CFD, not measured
}

# Symbol → calibration key mapping (cost_calibration.json uses different names)
_SYMBOL_TO_CAL_KEY = {
    "XAGUSD": "SILVER",
    "OIL": "OIL",
    # Add more if needed
}


def get_spread_bps(symbol: str) -> float:
    """Get measured spread in bps for a symbol from cost_calibration.json.

    Returns 0.0 if symbol not found (safe default).
    """
    try:
        with open(COST_CALIBRATION_PATH, encoding="utf-8") as f:
            cal = json.load(f)
        assets = cal.get("assets", {})
        sym = symbol.upper()

        # 1. Try exact match
        if sym in assets:
            return assets[sym].get("spread_bps_measured", 0.0)

        # 2. Try known mapping
        cal_key = _SYMBOL_TO_CAL_KEY.get(sym)
        if cal_key and cal_key in assets:
            return assets[cal_key].get("spread_bps_measured", 0.0)

        # 3. Partial match: check if any asset key is contained in symbol or vice versa
        for asset_sym, asset_data in assets.items():
            if asset_sym in sym or sym in asset_sym:
                return asset_data.get("spread_bps_measured", 0.0)

        # 4. Fallback to estimates
        return _SPREAD_BPS_ESTIMATES.get(sym, 0.0)
    except Exception:
        return _SPREAD_BPS_ESTIMATES.get(symbol.upper(), 0.0)

StrategyId = Literal[
    "tsm",
    "rsi_bb",
    "donchian",
    "volume_breakout",
    "mrb",
    # Gold ICT strategies (wrapped from gold_bot/)
    "gi_order_block",
    "gi_fair_value_gap",
    "gi_liquidity_sweep",
    "gi_bos_choch",
    "gi_multi_tf_align",
    "gi_london_breakout",
    "gi_news_fade",
    "gi_vwap_rejection",
    "gi_fibonacci",
    "gi_rsi_divergence",
    "gi_ema_cross",
    "gi_supply_demand",
    "gi_opening_range",
]


@dataclass
class CampaignConfig:
    """Single campaign — one strategy, one symbol, one timeframe."""

    campaign_id: str
    strategy_id: StrategyId
    symbol: str
    timeframe: str  # D1, H4, H1, M15
    capital: float = 100_000.0
    risk_per_trade_pct: float = 1.0
    max_positions: int = 1
    commission_bps: float = 2.2
    slippage_bps: float = 0.5
    spread_bps: float = 0.0  # bid-ask spread in bps (yfinance=mid, MT5=bid/ask)
    params: dict = field(default_factory=dict)
    start_date: str = ""  # empty = max available
    end_date: str = ""  # empty = latest
    mode: Literal["historical", "live"] = "historical"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> CampaignConfig:
        return cls(**d)


def get_param_grid(strategy_id: str, param_variations: bool = True) -> list[dict]:
    """Fixed param search space per strategy — the same grid used to assign each
    campaign's params at generation time. Reused by walk-forward validation so
    per-fold param selection searches the identical space (no new optimizer)."""
    param_grids: dict[str, list[dict]] = {}
    param_grids["tsm"] = [
        {"lookbacks": [20, 40, 60, 120], "vol_target": 0.10},
        {"lookbacks": [10, 30, 50, 100], "vol_target": 0.12},
        {"lookbacks": [40, 80, 120, 200], "vol_target": 0.08},
    ] if param_variations else [{}]

    param_grids["rsi_bb"] = [
        {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "bb_period": 20, "bb_std": 2.0},
        {"rsi_period": 7, "rsi_oversold": 25, "rsi_overbought": 75, "bb_period": 10, "bb_std": 1.5},
        {"rsi_period": 21, "rsi_oversold": 35, "rsi_overbought": 65, "bb_period": 30, "bb_std": 2.5},
    ] if param_variations else [{"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "bb_period": 20, "bb_std": 2.0}]

    param_grids["donchian"] = [
        {"period": 20, "vol_filter": True},
        {"period": 10, "vol_filter": True},
        {"period": 40, "vol_filter": True},
        {"period": 20, "vol_filter": False},
    ] if param_variations else [{"period": 20, "vol_filter": True}]

    param_grids["volume_breakout"] = [
        {"vol_period": 20, "vol_mult": 2.0, "lookback": 20},
        {"vol_period": 10, "vol_mult": 1.5, "lookback": 10},
        {"vol_period": 30, "vol_mult": 2.5, "lookback": 30},
    ] if param_variations else [{"vol_period": 20, "vol_mult": 2.0, "lookback": 20}]

    param_grids["mrb"] = [
        {"lookback": 20, "entry_z": 2.0, "exit_z": 0.5},
        {"lookback": 10, "entry_z": 1.5, "exit_z": 0.3},
        {"lookback": 30, "entry_z": 2.5, "exit_z": 0.7},
    ] if param_variations else [{"lookback": 20, "entry_z": 2.0, "exit_z": 0.5}]

    # ── Gold ICT strategies (wrapped from gold_bot/) ──────────────────────
    # Minimal param variation — gold_bot strategies are already tuned.
    # Only vary min_bars to test warmup sensitivity.

    _gold_ict_defaults = [
        {"min_bars": 50},
        {"min_bars": 60},
        {"min_bars": 40},
    ] if param_variations else [{"min_bars": 50}]

    for sid in [
        "gi_order_block", "gi_fair_value_gap", "gi_liquidity_sweep",
        "gi_bos_choch", "gi_multi_tf_align", "gi_london_breakout",
        "gi_news_fade", "gi_vwap_rejection", "gi_fibonacci",
        "gi_rsi_divergence", "gi_ema_cross", "gi_supply_demand",
        "gi_opening_range",
    ]:
        param_grids[sid] = _gold_ict_defaults

    return param_grids.get(strategy_id, [{}])


def generate_campaigns(
    strategies: list[StrategyId] | None = None,
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    param_variations: bool = True,
) -> list[CampaignConfig]:
    """Auto-generate all campaign combinations.

    Defaults — 5 strategies × ~11 symbols × 2-3 timeframes × param vars = 500+ campaigns.
    """
    if strategies is None:
        strategies = [
            "tsm", "rsi_bb", "donchian", "volume_breakout", "mrb",
            "gi_order_block", "gi_fair_value_gap", "gi_liquidity_sweep",
            "gi_bos_choch", "gi_multi_tf_align", "gi_london_breakout",
            "gi_news_fade", "gi_vwap_rejection", "gi_fibonacci",
            "gi_rsi_divergence", "gi_ema_cross", "gi_supply_demand",
            "gi_opening_range",
        ]

    if symbols is None:
        symbols = [
            "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
            "BTCUSD", "ETHUSD", "NAS100", "US30", "OIL", "XAGUSD",
        ]

    if timeframes is None:
        timeframes = ["D1", "H4", "H1", "M15"]

    campaigns = []
    cid = 0
    for sid in strategies:
        params_list = get_param_grid(sid, param_variations)
        for params in params_list:
            for sym in symbols:
                for tf in timeframes:
                    cid += 1
                    campaigns.append(CampaignConfig(
                        campaign_id=f"camp_{cid:04d}",
                        strategy_id=sid,
                        symbol=sym,
                        timeframe=tf,
                        params=params,
                        tags=[sid, sym, tf],
                    ))

    return campaigns


def save_campaigns(campaigns: list[CampaignConfig], path: str | Path | None = None) -> str:
    """Save campaigns list to JSON."""
    if path is None:
        os.makedirs(CAMPAIGNS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = CAMPAIGNS_DIR / f"campaign_batch_{ts}.json"
    data = [c.to_dict() for c in campaigns]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return str(path)


def load_campaigns(path: str | Path) -> list[CampaignConfig]:
    """Load campaigns from JSON."""
    with open(path) as f:
        data = json.load(f)
    return [CampaignConfig.from_dict(d) for d in data]


def estimate_duration(campaigns: list[CampaignConfig], workers: int = 8) -> dict:
    """Estimate total run time based on data size per campaign."""
    avg_d1_bars = 2500  # ~10 years of daily
    avg_h4_bars = 6000
    avg_h1_bars = 20000

    bar_counts = {"D1": avg_d1_bars, "H4": avg_h4_bars, "H1": avg_h1_bars}
    ms_per_bar = 0.05  # ~50μs per bar per strategy

    total_ms = 0
    for c in campaigns:
        bars = bar_counts.get(c.timeframe, 2500)
        total_ms += bars * ms_per_bar

    total_sec = total_ms / 1000
    parallel_sec = total_sec / workers
    n = len(campaigns)

    return {
        "total_campaigns": n,
        "workers": workers,
        "estimated_sequential_sec": round(total_sec, 1),
        "estimated_parallel_sec": round(parallel_sec, 1),
        "estimated_parallel_min": round(parallel_sec / 60, 1),
        "estimated_parallel_hours": round(parallel_sec / 3600, 2),
    }
