"""Evidence triage + cost-viability math (spec §5 P3, 0 N).

Pure arithmetic on cost_calibration.json — no backtests, no returns.
Cost rule (A1): calibrated symbols use their FROM_TICKS round trip;
uncalibrated symbols use the asset-class worst-case among calibrated
symbols × 1.5 (conservative). Viability: annual cost (cost_bps × 2 ×
trades_per_day × 252) must stay < 10% of a 20% annual edge assumption.
Martingale/grid entries are excluded unless a gate-pass record exists
(Phase 0 hard gate — spec §4).
"""

from __future__ import annotations

import json
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_COST = json.loads((_BASE / "config" / "cost_calibration.json").read_text(encoding="utf-8"))

PROXY_MARGIN = 1.5
ASSUMED_ANNUAL_EDGE = 0.20  # conservative target for viability math
COST_BUDGET_FRACTION = 0.10
DEFAULT_TRADES_PER_DAY = 0.5  # slow-biased conservative default; P4 refines per family

_MARTINGALE_GATE_PASSES: set[str] = set()  # populated at P4 by the hard-gate runner


def _calibrated_round_trip(symbol: str) -> float | None:
    assets = _COST.get("assets", {})
    meta = assets.get(symbol) or {}
    if meta.get("status") == "FROM_TICKS":
        rt = meta.get("round_trip_bps_measured") or meta.get("round_trip_bps")
        if isinstance(rt, int | float) and rt > 0:
            return float(rt)
    return None


def _asset_class(symbol: str) -> str:
    if symbol in {"BTCUSD", "ETHUSD", "SOLUSD"}:
        return "crypto"
    if symbol in {"XAUUSD", "XAGUSD", "SILVER", "XPDUSD", "XPTUSD"}:
        return "metals"
    if symbol in {"NAS100", "US30", "US500", "GER40", "UK100", "SPX500"}:
        return "indices"
    return "fx"


def _class_worst_case(asset_class: str) -> float:
    worst = 0.0
    assets = _COST.get("assets", {})
    for sym, meta in assets.items():
        if isinstance(meta, dict) and meta.get("status") == "FROM_TICKS" and _asset_class(sym) == asset_class:
            rt = meta.get("round_trip_bps")
            if isinstance(rt, int | float) and rt > worst:
                worst = float(rt)
    return worst


def ROUND_TRIP_BPS(symbol: str) -> float:
    calibrated = _calibrated_round_trip(symbol)
    if calibrated is not None:
        return calibrated
    worst = _class_worst_case(_asset_class(symbol))
    return worst * PROXY_MARGIN if worst > 0 else 24.75 * PROXY_MARGIN  # floor: BTCUSD measured


def cost_viability(entry: dict, trades_per_day: float) -> dict:
    if trades_per_day <= 0:
        return {
            "viable": True,
            "cost_bps": ROUND_TRIP_BPS(entry.get("symbol", "")),
            "annual_cost_pct": 0.0,
            "reason": "no trades -> no cost",
        }
    rt = ROUND_TRIP_BPS(entry.get("symbol", ""))
    annual_cost = rt * 2 * trades_per_day * 252 / 100  # bps -> % annualized
    budget = ASSUMED_ANNUAL_EDGE * COST_BUDGET_FRACTION * 100
    viable = annual_cost < budget
    return {
        "viable": viable,
        "cost_bps": rt,
        "annual_cost_pct": round(annual_cost, 2),
        "reason": f"annual cost {annual_cost:.2f}% vs budget {budget:.2f}%" if not viable else "within cost budget",
    }


def shortlist(entries: list[dict]) -> list[dict]:
    tier_rank = {"literature": 0, "myfxbook_verified": 1, "practitioner": 2}
    out = []
    for e in entries:
        if e.get("requires_martingale_gate") and e.get("catalog_id", "?") not in _MARTINGALE_GATE_PASSES:
            continue  # hard gate required (spec §4)
        v = cost_viability(e, trades_per_day=DEFAULT_TRADES_PER_DAY)
        if not v["viable"]:
            continue
        out.append({**e, "triage": v})
    out.sort(key=lambda e: (tier_rank.get(e.get("evidence_tier"), 9), e.get("name", "")))
    return out
