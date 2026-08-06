"""Mechanism taxonomy + fingerprint dedup (spec §5 P2, 0 N).

Classifies entries into canonical mechanism families, fingerprints
(family|symbol|timeframe|structural params), dedups to one
representative per fingerprint, excludes partition-CLOSED families
(owned by Direction H), and flags martingale/grid for the hard gate.
"""

from __future__ import annotations

import hashlib
import json

from research.partition_registry import check_partition

MECHANISM_FAMILIES: dict[str, list[str]] = {
    "trend_following": ["trend_following", "donchian", "moving_average", "ma_cross", "tsmom", "faber"],
    "breakout": ["breakout", "range_breakout", "donchian_breakout", "session_breakout", "dual_thrust"],
    "momentum": ["momentum", "relative_strength", "cross_sectional_momentum"],
    "mean_reversion": ["mean_reversion", "rsi_mean_reversion", "rsi_mr", "bollinger", "zscore"],
    "grid_martingale": ["grid", "martingale", "grid_martingale", "recovery", "averaging"],
    "scalper": ["scalper", "scalping", "m1_scalp", "m5_scalp", "intraday_scalp"],
    "carry": ["carry", "rollover", "funding_rate", "swap"],
    "seasonality": ["seasonality", "calendar", "monthly_pattern", "day_of_week"],
    "vol_targeting": ["vol_targeting", "volatility_targeting", "yang_zhang"],
    "event": ["fomc", "cpi", "nfp", "news", "event_driven"],
    "orderflow": ["orderflow", "order_flow", "bid_ask", "liquidity"],
    "regime": ["regime", "filter", "trend_filter", "vol_filter"],
    "session": ["session", "london", "new_york", "asia", "time_window"],
    "multi_asset": ["portfolio", "multi_asset", "cross_asset", "rotation"],
    "microstructure": ["microstructure", "spread", "quote", "tick"],
    "other": [],
}

MARTINGALE_FAMILIES = {"grid_martingale"}


def _normalize(mechanism: str) -> str:
    return mechanism.lower().replace(" ", "_").replace("-", "_")


def classify_mechanism(entry: dict) -> str:
    m = _normalize(entry.get("mechanism", ""))
    for family, keywords in MECHANISM_FAMILIES.items():
        if m in keywords or any(k in m for k in keywords):
            return family
    return "other"


def fingerprint(entry: dict) -> str:
    family = classify_mechanism(entry)
    # structural params only: drop claimed_perf / name / source (non-structural)
    structural = {k: v for k, v in (entry.get("params") or {}).items() if isinstance(v, int | float | str | bool)}
    canonical = "|".join(
        [
            family,
            str(entry.get("symbol", "")).upper(),
            str(entry.get("timeframe", "")).upper(),
            json.dumps(structural, sort_keys=True),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dedup_to_canonical(entries: list[dict]) -> list[dict]:
    by_fp: dict[str, dict] = {}
    for e in entries:
        # Spec §1.8/A17: P2 MUST check the partition registry itself, not just
        # trust the ingest tag (defense in depth at both layers).
        part = check_partition(e.get("mechanism", ""), e.get("symbol", ""), e.get("timeframe", ""))
        if part["status"] == "CLOSED":
            continue  # Direction H owns this family (A17)
        partition = e.get("partition") or {}
        if partition.get("status") == "CLOSED":
            continue  # ingest-tagged CLOSED (e.g. future partition rules)
        fp = fingerprint(e)
        if fp in by_fp:
            continue
        out = dict(e)
        out["mechanism_family"] = classify_mechanism(e)
        out["requires_martingale_gate"] = out["mechanism_family"] in MARTINGALE_FAMILIES
        by_fp[fp] = out
    return list(by_fp.values())
