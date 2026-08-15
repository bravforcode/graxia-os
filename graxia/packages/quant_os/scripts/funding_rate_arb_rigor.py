"""Funding Rate Arbitrage — Rigor Pass (Direction D, Trial #4003).

Pre-registered in research/hypothesis_registry_d.json BEFORE this script was run.

Trial #4001 (feasibility pilot) used a weak threshold (>=2 symbols, net yield>0,
>50% periods positive) with no significance test, no cost stress, single exchange,
no crash-period stress, and no comparison to the risk-free rate. This script closes
those gaps, per explicit user demand: apply the SAME rigor standard already used to
REJECT Direction A/B (HAC/Newey-West significance, cost stress, out-of-sample-like
robustness), and compare directly to T-bill yield -- be ready for this to kill the
last surviving "edge".

NOT the DK-test/PBO/label-shuffle machinery (there is no fitted model here to
overfit -- this measures a real market-structure cashflow). The correct tool for
"is the mean funding rate distinguishable from zero given autocorrelation" is a
Newey-West HAC t-test on the per-period rate series, computed with the EXACT same
formula already used and trusted in scripts/edge_search_cross_sectional.py's
run_dk_test() (Bartlett kernel, T^(1/3) lag truncation).

No API keys, no order execution, no capital at risk. Public ccxt endpoints only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt

ROOT = Path(__file__).resolve().parent.parent

FUNDING_INTERVAL_HOURS = 8
PERIODS_PER_YEAR = 365 * 24 / FUNDING_INTERVAL_HOURS  # 1095

ASSUMED_SPOT_FEE_BPS = 10.0
ASSUMED_PERP_FEE_BPS = 4.0
ASSUMED_SPREAD_BPS = 2.0
BASE_ROUND_TRIP_COST_BPS = 2 * (ASSUMED_SPOT_FEE_BPS + ASSUMED_PERP_FEE_BPS + ASSUMED_SPREAD_BPS)

# External assumption, dated -- not derived from any API in this repo.
# 3-month T-bill secondary market rate, approximate, as of the analysis date.
# Source: this is a manually-entered reference value; re-check against a live
# source (e.g. FRED DGS3MO) before relying on it for a real decision.
TBILL_ANNUAL_YIELD_PCT_ASSUMED = 4.5
TBILL_SOURCE_NOTE = (
    "Assumed 3-month T-bill yield ~4.5%/yr (approximate, manually entered "
    "2026-07-28 -- NOT fetched live. Re-verify against FRED DGS3MO before "
    "using this comparison to make a real capital-allocation decision."
)

# Known historical crypto crash/crisis windows to stress-test funding yield during
CRASH_WINDOWS = [
    ("2020-03-12", "2020-03-13", "COVID crash / Black Thursday"),
    ("2022-05-07", "2022-05-13", "Terra/LUNA collapse"),
    ("2022-06-13", "2022-06-19", "Celsius/3AC contagion"),
    ("2022-11-06", "2022-11-14", "FTX collapse"),
]

EXCHANGES = {
    "binance": lambda: ccxt.binance({"options": {"defaultType": "future"}}),
    "okx": lambda: ccxt.okx({"options": {"defaultType": "swap"}}),
    "bitget": lambda: ccxt.bitget({"options": {"defaultType": "swap"}}),
}

# Per-exchange unified symbol overrides (ccxt symbol notation differs by exchange:
# Binance USDT-M perp = "BTC/USDT", Bitget/OKX swap = "BTC/USDT:USDT")
SYMBOL_OVERRIDES = {
    "bitget": {"BTC/USDT": "BTC/USDT:USDT", "ETH/USDT": "ETH/USDT:USDT"},
    "okx": {"BTC/USDT": "BTC/USDT:USDT", "ETH/USDT": "ETH/USDT:USDT"},
}


def fetch_funding_history(exchange: ccxt.Exchange, symbol: str, lookback_days: int) -> list[dict]:
    since = exchange.milliseconds() - lookback_days * 24 * 60 * 60 * 1000
    all_rates: list[dict] = []
    cursor = since
    while True:
        try:
            batch = exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
        except Exception as e:
            print(f"    fetch error at cursor={cursor}: {e}")
            break
        if not batch:
            break
        all_rates.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if last_ts <= cursor or len(batch) < 1000:
            break
        cursor = last_ts + 1
    return all_rates


def newey_west_t_test(rates: list[float]) -> dict:
    """HAC (Newey-West) t-test: is mean(rates) significantly different from 0?

    Identical formula/kernel to scripts/edge_search_cross_sectional.py::run_dk_test()
    (Bartlett kernel, T^(1/3) lag truncation) -- reused deliberately for consistency
    with the project's already-trusted significance-test convention.
    """
    import numpy as np
    import pandas as pd

    s = pd.Series(rates)
    T = len(s)
    if T < 30:
        return {"t_stat": 0.0, "p_value_two_sided": 1.0, "significant_p05": False, "note": "insufficient periods"}

    mu = float(s.mean())
    max_lag = max(1, int(T ** (1 / 3)))
    gamma_0 = float(s.var(ddof=1))
    nw_var = gamma_0
    for lag in range(1, max_lag + 1):
        cov = float(s.iloc[lag:].cov(s.iloc[:-lag]))
        weight = 1.0 - lag / (max_lag + 1)
        nw_var += 2 * weight * cov

    nw_se = math.sqrt(nw_var / T) if nw_var > 0 else 1e-12
    t_stat = mu / nw_se if nw_se > 0 else 0.0

    # Two-sided p-value from normal approx (T is large for daily/8h funding series)
    from math import erf
    p_value = 2 * (1 - 0.5 * (1 + erf(abs(t_stat) / math.sqrt(2))))

    return {
        "mean_rate": mu,
        "n_periods": T,
        "max_lag": max_lag,
        "nw_t_stat": round(t_stat, 4),
        "p_value_two_sided": round(p_value, 6),
        "significant_p05": bool(p_value < 0.05),
    }


def cost_stress(annualized_raw_bps: float, actual_days: float, multipliers: list[float]) -> dict:
    out = {}
    for m in multipliers:
        cost_bps = BASE_ROUND_TRIP_COST_BPS * m
        amortized_annual_cost = cost_bps * (365 / actual_days)
        net = annualized_raw_bps - amortized_annual_cost
        out[f"{m}x"] = {
            "round_trip_cost_bps": round(cost_bps, 2),
            "net_annualized_yield_bps": round(net, 2),
            "net_annualized_yield_pct": round(net / 100, 3),
            "still_positive": bool(net > 0),
        }
    return out


def crash_window_yield(history: list[dict], window_start: str, window_end: str) -> dict | None:
    start_ms = int(datetime.fromisoformat(window_start).replace(tzinfo=UTC).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(window_end).replace(tzinfo=UTC).timestamp() * 1000)
    in_window = [h for h in history if start_ms <= h["timestamp"] <= end_ms]
    if len(in_window) < 2:
        return None
    rates = [h["fundingRate"] for h in in_window if h.get("fundingRate") is not None]
    if not rates:
        return None
    cumulative = sum(rates)
    return {
        "n_periods_in_window": len(rates),
        "cumulative_rate_in_window_bps": round(cumulative * 10_000, 2),
        "mean_rate_per_period_bps": round((cumulative / len(rates)) * 10_000, 4),
        "durably_positive_in_crash": bool(cumulative > 0),
    }


def analyze_symbol_on_exchange(exchange_id: str, exchange: ccxt.Exchange, symbol: str, lookback_days: int) -> dict:
    print(f"\n[{exchange_id}] Fetching {symbol} funding rate history ({lookback_days}d)...")
    history = fetch_funding_history(exchange, symbol, lookback_days)
    if not history:
        return {"exchange": exchange_id, "symbol": symbol, "error": "no data returned"}

    rates = [h["fundingRate"] for h in history if h.get("fundingRate") is not None]
    n = len(rates)
    if n == 0:
        return {"exchange": exchange_id, "symbol": symbol, "error": "no funding rates in response"}

    actual_days = (history[-1]["timestamp"] - history[0]["timestamp"]) / (1000 * 60 * 60 * 24)
    actual_days = max(actual_days, 1.0)
    total_cumulative_rate = sum(rates)
    annualized_raw_bps = (total_cumulative_rate / actual_days) * 365 * 10_000
    positive_periods = sum(1 for r in rates if r > 0)

    nw = newey_west_t_test(rates)
    stress = cost_stress(annualized_raw_bps, actual_days, [1.0, 1.2, 1.5])
    crash_results = {}
    for start, end, label in CRASH_WINDOWS:
        r = crash_window_yield(history, start, end)
        if r is not None:
            crash_results[label] = {"window": [start, end], **r}

    base_net_bps = stress["1.0x"]["net_annualized_yield_bps"]
    base_net_pct = base_net_bps / 100
    tbill_comparison = {
        "net_apy_pct": round(base_net_pct, 3),
        "tbill_apy_pct_assumed": TBILL_ANNUAL_YIELD_PCT_ASSUMED,
        "excess_over_tbill_pct": round(base_net_pct - TBILL_ANNUAL_YIELD_PCT_ASSUMED, 3),
        "beats_tbill": bool(base_net_pct > TBILL_ANNUAL_YIELD_PCT_ASSUMED),
        "note": TBILL_SOURCE_NOTE,
    }

    print(f"  n_periods={n}  actual_days={actual_days:.1f}  positive={positive_periods}/{n}")
    print(f"  raw APY: {annualized_raw_bps/100:.2f}%  NW t-stat: {nw.get('nw_t_stat')}  "
          f"p={nw.get('p_value_two_sided')}  significant@5%={nw.get('significant_p05')}")
    print(f"  net APY (1.0x/1.2x/1.5x cost): "
          f"{stress['1.0x']['net_annualized_yield_pct']}% / "
          f"{stress['1.2x']['net_annualized_yield_pct']}% / "
          f"{stress['1.5x']['net_annualized_yield_pct']}%")
    print(f"  vs T-bill ({TBILL_ANNUAL_YIELD_PCT_ASSUMED}%/yr assumed): "
          f"beats_tbill={tbill_comparison['beats_tbill']}")
    for label, r in crash_results.items():
        print(f"  crash window [{label}]: cumulative={r['cumulative_rate_in_window_bps']}bps "
              f"positive={r['durably_positive_in_crash']}")

    return {
        "exchange": exchange_id,
        "symbol": symbol,
        "n_periods": n,
        "actual_days_observed": round(actual_days, 1),
        "positive_period_pct": round(100 * positive_periods / n, 2),
        "raw_annualized_yield_pct": round(annualized_raw_bps / 100, 3),
        "newey_west_significance": nw,
        "cost_stress": stress,
        "tbill_comparison": tbill_comparison,
        "crash_window_results": crash_results,
        "first_ts": history[0]["datetime"],
        "last_ts": history[-1]["datetime"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Funding rate arb rigor pass (Direction D, Trial #4003)")
    parser.add_argument("--symbols", type=str, default="BTC/USDT,ETH/USDT")
    parser.add_argument("--secondary-exchange", type=str, default="bitget", choices=list(EXCHANGES))
    parser.add_argument("--lookback-days", type=int, default=1460, help="~4yr, to reach FTX/LUNA/COVID windows")
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not args.output:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        args.output = str(ROOT / "reports" / f"funding_rate_arb_rigor_{date_str}.json")

    print("=" * 70)
    print("  FUNDING RATE ARBITRAGE — RIGOR PASS (Direction D, Trial #4003)")
    print("=" * 70)

    all_results = []
    for exch_id in ["binance", args.secondary_exchange]:
        exchange = EXCHANGES[exch_id]()
        for symbol in symbols:
            actual_symbol = SYMBOL_OVERRIDES.get(exch_id, {}).get(symbol, symbol)
            try:
                r = analyze_symbol_on_exchange(exch_id, exchange, actual_symbol, args.lookback_days)
            except Exception as e:
                print(f"  ERROR on {exch_id}/{actual_symbol}: {e}")
                r = {"exchange": exch_id, "symbol": actual_symbol, "error": str(e)}
            all_results.append(r)

    valid = [r for r in all_results if "error" not in r]

    print(f"\n{'=' * 70}\n  SUMMARY\n{'=' * 70}")
    for r in valid:
        print(f"  {r['exchange']:<8} {r['symbol']:<10} "
              f"net_apy(1.0x)={r['cost_stress']['1.0x']['net_annualized_yield_pct']:>7.3f}%  "
              f"sig@5%={r['newey_west_significance'].get('significant_p05')}  "
              f"beats_tbill={r['tbill_comparison']['beats_tbill']}")

    payload = {
        "trial_number": 4003,
        "generated_at": datetime.now(UTC).isoformat(),
        "test": "funding_rate_arb_rigor_pass",
        "assumed_costs_bps_1x": BASE_ROUND_TRIP_COST_BPS,
        "tbill_assumption": TBILL_SOURCE_NOTE,
        "results": all_results,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\n  Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
