"""Funding Rate Arbitrage — Historical Carry Feasibility Pilot (Direction D, Trial #4001).

Pre-registered in research/hypothesis_registry_d.json BEFORE this script was run.

This does NOT test price direction prediction. It measures a structural market
fact: has Binance's perpetual funding rate, historically, paid the short side
(collectible via long-spot + short-perp cash-and-carry) enough to durably
exceed realistic round-trip trading costs?

No API keys, no order execution, no capital at risk. Public ccxt endpoints only.

Usage:
    python scripts/funding_rate_arb_pilot.py --symbols BTC/USDT,ETH/USDT --lookback-days 365
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ccxt

ROOT = Path(__file__).resolve().parent.parent

FUNDING_INTERVAL_HOURS = 8
PERIODS_PER_YEAR = 365 * 24 / FUNDING_INTERVAL_HOURS  # 1095

# Realistic Binance costs (documented public fee schedule, regular/VIP0 tier)
ASSUMED_SPOT_FEE_BPS = 10.0    # 0.10% taker, spot
ASSUMED_PERP_FEE_BPS = 4.0     # 0.04% taker, USDT-M futures
ASSUMED_SPREAD_BPS = 2.0       # conservative top-of-book spread estimate, BTC/ETH majors
ROUND_TRIP_COST_BPS = 2 * (ASSUMED_SPOT_FEE_BPS + ASSUMED_PERP_FEE_BPS + ASSUMED_SPREAD_BPS)  # entry + exit


def fetch_funding_history(exchange: ccxt.Exchange, symbol: str, lookback_days: int) -> list[dict]:
    """Fetch real funding rate history via ccxt's public endpoint (no auth)."""
    since = exchange.milliseconds() - lookback_days * 24 * 60 * 60 * 1000
    all_rates: list[dict] = []
    cursor = since
    while True:
        batch = exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
        if not batch:
            break
        all_rates.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if last_ts <= cursor or len(batch) < 1000:
            break
        cursor = last_ts + 1
    return all_rates


def analyze_symbol(exchange: ccxt.Exchange, symbol: str, lookback_days: int) -> dict:
    print(f"\nFetching {symbol} funding rate history ({lookback_days}d)...")
    history = fetch_funding_history(exchange, symbol, lookback_days)
    if not history:
        return {"symbol": symbol, "error": "no data returned"}

    rates = [h["fundingRate"] for h in history if h.get("fundingRate") is not None]
    n = len(rates)
    if n == 0:
        return {"symbol": symbol, "error": "no funding rates in response"}

    mean_rate_per_period = sum(rates) / n
    positive_periods = sum(1 for r in rates if r > 0)
    total_cumulative_rate = sum(rates)  # sum of per-period rates over the actual window observed

    # Annualize using the ACTUAL observed period count over ACTUAL observed days,
    # not the theoretical 1095/year, to avoid overstating from any data gaps.
    actual_days = (history[-1]["timestamp"] - history[0]["timestamp"]) / (1000 * 60 * 60 * 24)
    actual_days = max(actual_days, 1.0)
    annualized_funding_yield_bps = (total_cumulative_rate / actual_days) * 365 * 10_000

    net_annualized_yield_bps = annualized_funding_yield_bps - ROUND_TRIP_COST_BPS * (365 / max(actual_days, 1.0))
    # Round-trip cost is a ONE-TIME cost for a static held-for-window position,
    # not a recurring annual cost — so amortize it over the actual window length.
    onetime_cost_amortized_annual_bps = ROUND_TRIP_COST_BPS * (365 / actual_days)
    net_annualized_yield_bps = annualized_funding_yield_bps - onetime_cost_amortized_annual_bps

    print(f"  n_periods={n}  actual_days={actual_days:.1f}  positive_periods={positive_periods}/{n} "
          f"({100*positive_periods/n:.1f}%)")
    print(f"  raw annualized funding yield: {annualized_funding_yield_bps:.1f} bps/yr "
          f"({annualized_funding_yield_bps/100:.2f}%/yr)")
    print(f"  one-time round-trip cost (amortized over window): {onetime_cost_amortized_annual_bps:.1f} bps/yr")
    print(f"  NET annualized yield: {net_annualized_yield_bps:.1f} bps/yr "
          f"({net_annualized_yield_bps/100:.2f}%/yr)")

    return {
        "symbol": symbol,
        "n_periods": n,
        "actual_days_observed": round(actual_days, 1),
        "positive_periods": positive_periods,
        "positive_period_pct": round(100 * positive_periods / n, 2),
        "mean_rate_per_8h_period": mean_rate_per_period,
        "cumulative_rate_over_window": total_cumulative_rate,
        "raw_annualized_funding_yield_bps": round(annualized_funding_yield_bps, 2),
        "onetime_roundtrip_cost_bps": ROUND_TRIP_COST_BPS,
        "onetime_cost_amortized_annual_bps": round(onetime_cost_amortized_annual_bps, 2),
        "net_annualized_yield_bps": round(net_annualized_yield_bps, 2),
        "net_annualized_yield_pct": round(net_annualized_yield_bps / 100, 3),
        "durably_positive": bool(net_annualized_yield_bps > 0 and positive_periods / n > 0.5),
        "first_ts": history[0]["datetime"],
        "last_ts": history[-1]["datetime"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Funding rate arb feasibility pilot (Direction D, Trial #4001)")
    parser.add_argument("--symbols", type=str, default="BTC/USDT,ETH/USDT")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not args.output:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        args.output = str(ROOT / "reports" / f"funding_rate_arb_pilot_{date_str}.json")

    print("=" * 70)
    print("  FUNDING RATE ARBITRAGE — FEASIBILITY PILOT (Direction D, Trial #4001)")
    print("  Testing a market-STRUCTURE fact, not a price-direction prediction")
    print("=" * 70)
    print(f"  Symbols: {symbols}")
    print(f"  Lookback: {args.lookback_days} days")
    print(f"  Assumed costs: spot={ASSUMED_SPOT_FEE_BPS}bps perp={ASSUMED_PERP_FEE_BPS}bps "
          f"spread={ASSUMED_SPREAD_BPS}bps -> round-trip={ROUND_TRIP_COST_BPS}bps (one-time)")

    exchange = ccxt.binance({"options": {"defaultType": "future"}})

    results = []
    for symbol in symbols:
        try:
            r = analyze_symbol(exchange, symbol, args.lookback_days)
            results.append(r)
        except Exception as e:
            print(f"  ERROR on {symbol}: {e}")
            results.append({"symbol": symbol, "error": str(e)})

    valid = [r for r in results if "error" not in r]
    all_durably_positive = len(valid) >= 2 and all(r["durably_positive"] for r in valid)

    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    for r in valid:
        status = "DURABLY POSITIVE" if r["durably_positive"] else "NOT DURABLY POSITIVE"
        print(f"  {r['symbol']:<10} net_apy={r['net_annualized_yield_pct']:>7.3f}%  "
              f"pos_periods={r['positive_period_pct']:>5.1f}%  -> {status}")

    verdict = "PASS" if all_durably_positive else "FAIL"
    print(f"\n  OVERALL VERDICT: {verdict}")
    print(
        "  (PASS requires >=2 valid symbols, each with net_annualized_yield > 0 "
        "AND >50% of periods funding-positive)"
    )

    payload = {
        "trial_number": 4001,
        "generated_at": datetime.now(UTC).isoformat(),
        "test": "funding_rate_arb_feasibility_pilot",
        "note": "Structural market-fact measurement, not a directional price-prediction test.",
        "assumed_costs_bps": {
            "spot_fee": ASSUMED_SPOT_FEE_BPS,
            "perp_fee": ASSUMED_PERP_FEE_BPS,
            "spread": ASSUMED_SPREAD_BPS,
            "one_time_round_trip_total": ROUND_TRIP_COST_BPS,
        },
        "per_symbol": results,
        "verdict": verdict,
        "verdict_criterion": ">=2 valid symbols, each net_annualized_yield>0 AND >50% periods positive",
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\n  Saved: {out_path}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
