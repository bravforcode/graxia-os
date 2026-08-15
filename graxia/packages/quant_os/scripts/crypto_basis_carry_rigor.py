"""Crypto Basis/Carry — Dated Futures Rigor Pass (Direction F, Trial #6001).

Pre-registered in research/hypothesis_registry_f.json BEFORE this script was run.

Tests a mechanism DISTINCT from Direction D's perpetual funding-rate carry
(Trial #4003, FAIL_RIGOR): the basis between a FIXED-EXPIRY quarterly
BTC/ETH future and spot. A dated future must converge to spot at expiry, so
a long-spot/short-future cash-and-carry position captures that convergence
as a delta-neutral "carry" return, driven by time-to-expiry decay rather
than a funding payment schedule.

Methodological note (the reason this script does NOT simply reuse Direction
D's "NW test on the raw rate level" approach): a dated future's basis level
is a near-unit-root series that mechanically decays toward zero as expiry
approaches. Running Newey-West on that level series produces a spuriously
large t-statistic (high autocorrelation that HAC with T^(1/3) lags does not
rehabilitate) — the opposite of the funding-rate case, where the rate itself
is a genuinely mixing series around a positive constant. The valid,
STATIONARY quantity for a significance test here is the daily delta-neutral
P&L return: r_t = spot_return_t - future_return_t. This script reports BOTH
the valid returns-based NW test (decision-relevant) and the naive level-based
NW test (comparison-only, explicitly NOT used to decide PASS/FAIL) so the
divergence between them is visible in the artifact.

Reuses scripts/funding_rate_arb_rigor.py's newey_west_t_test() (verbatim),
cost_stress() (verbatim), and the TBILL_ANNUAL_YIELD_PCT_ASSUMED / note
constants (verbatim) for consistency with the already-established rigor
convention in this project.

No API keys, no order execution, no capital at risk. Public ccxt endpoints only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import ccxt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from funding_rate_arb_rigor import (  # noqa: E402
    BASE_ROUND_TRIP_COST_BPS,
    TBILL_ANNUAL_YIELD_PCT_ASSUMED,
    TBILL_SOURCE_NOTE,
    cost_stress,
    newey_west_t_test,
)

RECENT_WINDOW_DAYS = 33

# Same quarterly expiry listed on both Binance and Deribit as of this analysis,
# which is what makes a genuine same-contract-tenor cross-exchange comparison
# possible without conflating "different exchange" with "different expiry".
EXPIRY_DATE = date(2026, 9, 25)

INSTRUMENTS = {
    "BTC": {
        "spot": ("binance_spot", "BTC/USDT"),
        "binance_future": ("binance_future", "BTC/USDT:USDT-260925"),
        "deribit_future": ("deribit", "BTC/USD:BTC-260925"),
    },
    "ETH": {
        "spot": ("binance_spot", "ETH/USDT"),
        "binance_future": ("binance_future", "ETH/USDT:USDT-260925"),
        "deribit_future": ("deribit", "ETH/USD:ETH-260925"),
    },
}

EXCHANGE_FACTORIES = {
    "binance_spot": lambda: ccxt.binance(),
    "binance_future": lambda: ccxt.binance({"options": {"defaultType": "future"}}),
    "deribit": lambda: ccxt.deribit(),
}


def fetch_daily_closes(exchange_key: str, symbol: str, limit: int = 400) -> dict[str, float]:
    """Return {ISO-date-string: close_price} for the last `limit` daily candles."""
    exchange = EXCHANGE_FACTORIES[exchange_key]()
    exchange.load_markets()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=limit)
    out = {}
    for ts, _o, _h, _l, c, _v in ohlcv:
        d = datetime.fromtimestamp(ts / 1000, UTC).date().isoformat()
        out[d] = c
    return out


def align(spot_closes: dict[str, float], fut_closes: dict[str, float]) -> list[tuple[str, float, float]]:
    common_dates = sorted(set(spot_closes) & set(fut_closes))
    return [(d, spot_closes[d], fut_closes[d]) for d in common_dates]


def daily_returns(series: list[float]) -> list[float]:
    return [(series[i] - series[i - 1]) / series[i - 1] for i in range(1, len(series))]


def days_to_expiry(iso_date: str) -> int:
    d = date.fromisoformat(iso_date)
    return max((EXPIRY_DATE - d).days, 1)


def analyze_window(aligned: list[tuple[str, float, float]], label: str) -> dict:
    """aligned = sorted list of (date, spot_close, fut_close) for the window."""
    if len(aligned) < 5:
        return {"window": label, "error": f"insufficient aligned observations ({len(aligned)})"}

    dates = [a[0] for a in aligned]
    spot = [a[1] for a in aligned]
    fut = [a[2] for a in aligned]

    r_spot = daily_returns(spot)
    r_fut = daily_returns(fut)
    r_carry = [rs - rf for rs, rf in zip(r_spot, r_fut, strict=True)]

    returns_nw = newey_west_t_test(r_carry)
    mean_daily_carry = returns_nw.get("mean_rate", 0.0)
    realized_annualized_carry_pct = round(mean_daily_carry * 365 * 100, 4)

    # Naive level-based test -- comparison only, NOT used to decide the verdict.
    level_series = []
    for d, s, f in aligned:
        raw_basis = (f - s) / s
        annualized_level = raw_basis * 365 / days_to_expiry(d)
        level_series.append(annualized_level)
    level_nw = newey_west_t_test(level_series)

    window_days = max((date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days, 1)
    stress = cost_stress(realized_annualized_carry_pct * 100, window_days, [1.0, 1.2, 1.5])
    base_net_pct = stress["1.0x"]["net_annualized_yield_pct"]
    tbill = {
        "net_apy_pct": base_net_pct,
        "tbill_apy_pct_assumed": TBILL_ANNUAL_YIELD_PCT_ASSUMED,
        "excess_over_tbill_pct": round(base_net_pct - TBILL_ANNUAL_YIELD_PCT_ASSUMED, 3),
        "beats_tbill": bool(base_net_pct > TBILL_ANNUAL_YIELD_PCT_ASSUMED),
    }

    return {
        "window": label,
        "date_range": [dates[0], dates[-1]],
        "n_days_spanned": window_days,
        "n_return_observations": len(r_carry),
        "returns_based_nw_significance_PRIMARY": returns_nw,
        "realized_annualized_carry_pct_raw": realized_annualized_carry_pct,
        "cost_stress": stress,
        "tbill_comparison": tbill,
        "naive_level_based_nw_significance_COMPARISON_ONLY_DO_NOT_DECIDE_ON": {
            **level_nw,
            "warning": (
                "This NW test runs on the raw annualized-basis LEVEL series, which is "
                "near-unit-root (basis mechanically decays toward 0 at expiry). HAC with "
                "T^(1/3) lags does not fully correct for this; a large/significant t-stat "
                "here is expected and should NOT be treated as evidence of a real edge. "
                "The returns_based_nw_significance_PRIMARY field above is the valid test."
            ),
        },
    }


def snapshot_hold_to_expiry(aligned: list[tuple[str, float, float]]) -> dict:
    last_date, last_spot, last_fut = aligned[-1]
    raw_basis = (last_fut - last_spot) / last_spot
    dte = days_to_expiry(last_date)
    annualized_pct = round(raw_basis * 365 / dte * 100, 4)
    stress = cost_stress(annualized_pct * 100, dte, [1.0, 1.2, 1.5])
    base_net_pct = stress["1.0x"]["net_annualized_yield_pct"]
    tbill = {
        "net_apy_pct": base_net_pct,
        "tbill_apy_pct_assumed": TBILL_ANNUAL_YIELD_PCT_ASSUMED,
        "excess_over_tbill_pct": round(base_net_pct - TBILL_ANNUAL_YIELD_PCT_ASSUMED, 3),
        "beats_tbill": bool(base_net_pct > TBILL_ANNUAL_YIELD_PCT_ASSUMED),
    }
    return {
        "as_of_date": last_date,
        "days_to_expiry": dte,
        "spot_price": last_spot,
        "future_price": last_fut,
        "raw_basis_pct": round(raw_basis * 100, 4),
        "annualized_basis_pct_if_held_to_expiry": annualized_pct,
        "cost_stress": stress,
        "tbill_comparison": tbill,
    }


def largest_drawdown_day_color(aligned: list[tuple[str, float, float]]) -> dict | None:
    """Informal color only -- NOT an equivalent to a real historical crash-window
    stress test (dated futures contracts don't persist back to 2020/2022 --
    see Trial #4003 for the best available crypto-derivatives crash evidence).
    """
    spot = [a[1] for a in aligned]
    if len(spot) < 3:
        return None
    worst_idx, worst_ret = None, 0.0
    for i in range(1, len(spot)):
        ret = (spot[i] - spot[i - 1]) / spot[i - 1]
        if ret < worst_ret:
            worst_ret, worst_idx = ret, i
    if worst_idx is None:
        return None
    d, s, f = aligned[worst_idx]
    raw_basis_that_day = round((f - s) / s * 100, 4)
    return {
        "note": (
            "INFORMAL COLOR ONLY, not a substitute for a real crash-window stress test "
            "(this contract's history does not reach 2020/2022 -- see Trial #4003 "
            "funding-rate results for the best available crypto-derivatives crash evidence)."
        ),
        "date": d,
        "spot_1day_return_pct": round(worst_ret * 100, 3),
        "basis_pct_that_day": raw_basis_that_day,
    }


def analyze_pair(symbol: str, spot_closes: dict[str, float], fut_closes: dict[str, float], future_label: str) -> dict:
    aligned = align(spot_closes, fut_closes)
    if len(aligned) < 5:
        return {"symbol": symbol, "future_leg": future_label, "error": "insufficient aligned data"}

    recent_cutoff_count = min(RECENT_WINDOW_DAYS + 1, len(aligned))
    recent_aligned = aligned[-recent_cutoff_count:]

    result = {
        "symbol": symbol,
        "future_leg": future_label,
        "expiry_date": EXPIRY_DATE.isoformat(),
        "full_window": analyze_window(aligned, "full_available_history"),
        "recent_33d_window": analyze_window(recent_aligned, f"recent_{RECENT_WINDOW_DAYS}d"),
        "snapshot_hold_to_expiry": snapshot_hold_to_expiry(aligned),
        "largest_drawdown_day_color_only": largest_drawdown_day_color(aligned),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Crypto basis/carry rigor pass (Direction F, Trial #6001)")
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    if not args.output:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        args.output = str(ROOT / "reports" / f"crypto_basis_carry_rigor_{date_str}.json")

    print("=" * 70)
    print("  CRYPTO BASIS/CARRY — DATED FUTURES RIGOR PASS (Direction F, Trial #6001)")
    print("=" * 70)

    all_results = []
    for symbol, legs in INSTRUMENTS.items():
        spot_key, spot_symbol = legs["spot"]
        print(f"\n[{symbol}] fetching spot ({spot_key}:{spot_symbol})...")
        try:
            spot_closes = fetch_daily_closes(spot_key, spot_symbol)
        except Exception as e:
            print(f"  ERROR fetching spot: {e}")
            continue

        for leg_name in ("binance_future", "deribit_future"):
            exch_key, fut_symbol = legs[leg_name]
            print(f"[{symbol}] fetching future ({exch_key}:{fut_symbol})...")
            try:
                fut_closes = fetch_daily_closes(exch_key, fut_symbol)
            except Exception as e:
                print(f"  ERROR fetching future {exch_key}/{fut_symbol}: {e}")
                all_results.append({"symbol": symbol, "future_leg": leg_name, "error": str(e)})
                continue

            r = analyze_pair(symbol, spot_closes, fut_closes, leg_name)
            all_results.append(r)

            if "error" in r:
                print(f"  ERROR: {r['error']}")
                continue

            fw = r["full_window"]
            rw = r["recent_33d_window"]
            snap = r["snapshot_hold_to_expiry"]
            print(f"  full-window   [{fw['date_range'][0]} .. {fw['date_range'][1]}] "
                  f"realized_carry_apy={fw['realized_annualized_carry_pct_raw']:.3f}%  "
                  f"returns_NW_sig@5%={fw['returns_based_nw_significance_PRIMARY'].get('significant_p05')}  "
                  f"net(1.0x)_beats_tbill={fw['tbill_comparison']['beats_tbill']}")
            print(f"  recent-33d    [{rw['date_range'][0]} .. {rw['date_range'][1]}] "
                  f"realized_carry_apy={rw['realized_annualized_carry_pct_raw']:.3f}%  "
                  f"returns_NW_sig@5%={rw['returns_based_nw_significance_PRIMARY'].get('significant_p05')}  "
                  f"net(1.0x)_beats_tbill={rw['tbill_comparison']['beats_tbill']}")
            print(f"  snapshot->exp as_of={snap['as_of_date']} dte={snap['days_to_expiry']} "
                  f"annualized_if_held={snap['annualized_basis_pct_if_held_to_expiry']:.3f}%  "
                  f"net(1.0x)_beats_tbill={snap['tbill_comparison']['beats_tbill']}")

    payload = {
        "trial_number": 6001,
        "generated_at": datetime.now(UTC).isoformat(),
        "test": "crypto_basis_carry_rigor_pass",
        "expiry_date_used": EXPIRY_DATE.isoformat(),
        "assumed_costs_bps_1x": BASE_ROUND_TRIP_COST_BPS,
        "tbill_assumption": TBILL_SOURCE_NOTE,
        "methodology_note": (
            "Primary significance test is Newey-West HAC on the STATIONARY daily "
            "delta-neutral return series (spot_return - future_return), not on the "
            "basis level (which is near-unit-root for a dated future and would give "
            "spurious significance). The naive level-based NW test is also reported "
            "per-window for transparency/comparison only."
        ),
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
