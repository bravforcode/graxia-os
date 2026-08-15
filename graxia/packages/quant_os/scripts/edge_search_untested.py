"""
Edge Search — 5 Untested Strategies (DK-test)
==============================================
Runs DK-test on strategies not yet fully tested in edge_search_all.py.

Strategies:
  1. COT Positioning  — XAUUSD  (single-asset, engine-based)
  2. Funding Rate Arb  — BTCUSD  (single-asset, engine-based, synthetic funding rate)
  3. FOMC Drift        — All CORE_UNIVERSE assets (multi-asset, engine-based)
  4. BTC-ETH Vol Spread — BTCUSD + ETHUSD (relative value, signal-based)
  5. ETH Vol Confirm    — ETHUSD  (single-asset, signal-based)

DK-test: Newey-West with T^(1/3) lags (same formula as edge_search_all.py).
Cost model: Pepperstone Razor spreads + commissions (same constants).
Verdict:   GO if dk_t>2.0 AND pos_sharpe>=5
           MARGINAL if dk_t>1.5 OR (dk_t>1.0 AND pos_sharpe>=4)
           else REJECT

Usage:
  python scripts/edge_search_untested.py
  python scripts/edge_search_untested.py --output reports/edge_search_untested_20260720.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Path setup — same as edge_search_all.py
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
_scripts = ROOT / "scripts"
for p in (str(GRAXIA_ROOT), str(ROOT), str(_scripts)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Reuse from edge_search_all.py (same cost model, data loaders, engine runner)
# ---------------------------------------------------------------------------
from edge_search_all import (  # noqa: E402
    CORE_UNIVERSE,
    SYMBOL_COMMISSION,
    SYMBOL_SPREAD_PIPS,
    compute_per_asset_metrics,
    extract_daily_returns,
    load_asset_data,
    run_engine_for_asset,
)

# ---------------------------------------------------------------------------
# Strategy imports (fully qualified graxia.packages.quant_os.strategies.*)
# ---------------------------------------------------------------------------
from graxia.packages.quant_os.strategies.btc_eth_vol_spread import (
    compute_bevs_signals,
)
from graxia.packages.quant_os.strategies.eth_vol_confirm import (
    compute_ethvc_signals,
)
from graxia.packages.quant_os.strategies.funding_rate_arb import (
    FundingRateArbitrage,
)
from graxia.packages.quant_os.strategies.path_b_wrappers import (
    COTPositioningStrategy,
    FOMCDriftStrategy,
)


# ===================================================================
# DK-test — identical formula to edge_search_all.py, relaxed column
# check so it also works for single-asset (1-column) return frames.
# ===================================================================

def _run_dk_test(all_returns: pd.DataFrame, total_trades: int) -> dict:
    """Newey-West DK t-test with T^(1/3) bandwidth.

    Works for >=1 asset column (original edge_search_all.py requires >=2).
    """
    if all_returns.empty:
        return {
            "dk_t_stat": 0.0,
            "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0,
            "total_assets": 0,
            "total_days": 0,
            "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    cs_mean = all_returns.mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {
            "dk_t_stat": 0.0,
            "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0,
            "total_assets": len(all_returns.columns),
            "total_days": len(cs_mean),
            "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    mu = float(cs_mean.mean())
    T = len(cs_mean)
    max_lag = max(1, int(T ** (1 / 3)))
    gamma_0 = float(cs_mean.var(ddof=1))
    nw_var = gamma_0
    for lag in range(1, max_lag + 1):
        cov = float(cs_mean.iloc[lag:].cov(cs_mean.iloc[:-lag]))
        weight = 1.0 - lag / (max_lag + 1)
        nw_var += 2 * weight * cov

    nw_se = math.sqrt(nw_var / T) if nw_var > 0 else 1e-10
    dk_t = mu / nw_se if nw_se > 0 else 0.0
    pooled_sharpe = mu / (math.sqrt(gamma_0) + 1e-10) * math.sqrt(252)

    pos_sharpe = 0
    for col in all_returns.columns:
        r = all_returns[col].dropna()
        if len(r) > 30:
            s = float(r.mean()) / (float(r.std(ddof=1)) + 1e-10) * math.sqrt(252)
            if s > 0:
                pos_sharpe += 1

    if dk_t > 2.0 and pos_sharpe >= 5:
        verdict = "GO"
    elif dk_t > 1.5 or (dk_t > 1.0 and pos_sharpe >= 4):
        verdict = "MARGINAL"
    else:
        verdict = "REJECT"

    return {
        "dk_t_stat": round(dk_t, 4),
        "pooled_sharpe": round(pooled_sharpe, 4),
        "positive_sharpe_count": pos_sharpe,
        "total_assets": len(all_returns.columns),
        "total_days": T,
        "total_trades": total_trades,
        "verdict": verdict,
    }


# ===================================================================
# Signal-based return simulation (for strategies without engine wrapper)
# ===================================================================

def _pip_value(symbol: str) -> float:
    """Price of 1 pip for spread-cost calculation."""
    if symbol in ("EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD", "XAGUSD"):
        return 0.0001
    # XAUUSD, NAS100, US30, BTCUSD, ETHUSD
    return 0.01


def _simulate_signal_returns(
    symbol: str,
    signal_series: pd.Series,
    close: pd.Series,
) -> pd.DataFrame:
    """Convert a signal series (-1/0/+1) to daily returns with transaction costs.

    Cost model matches edge_search_all.py: SYMBOL_SPREAD_PIPS spread per side.
    """
    df = pd.DataFrame({"signal": signal_series, "close": close}).dropna()
    if len(df) < 30:
        return pd.DataFrame()

    daily_ret = df["close"].pct_change()
    # Signal from previous bar determines today's position
    strat_ret = df["signal"].shift(1) * daily_ret

    # Transaction cost on every signal *change* (entry or exit)
    signal_change = df["signal"].diff().abs()
    avg_price = df["close"].iloc[-100:].mean()
    pv = _pip_value(symbol)
    spread_frac = SYMBOL_SPREAD_PIPS.get(symbol, 2.0) * pv / avg_price if avg_price > 0 else 0.0
    strat_ret = strat_ret - signal_change * spread_frac

    strat_ret = strat_ret.dropna()
    if strat_ret.empty:
        return pd.DataFrame()

    return pd.DataFrame({symbol: strat_ret})


def _simulate_bevs_returns(
    btc_symbol: str,
    eth_symbol: str,
    signal_series: pd.Series,
    btc_close: pd.Series,
    eth_close: pd.Series,
) -> pd.DataFrame:
    """Simulate BTC-ETH Vol Spread returns (relative value).

    signal=+1 → long BTC, short ETH  → return = btc_ret − eth_ret
    signal=−1 → short BTC, long ETH → return = −btc_ret + eth_ret
    """
    df = pd.DataFrame({
        "signal": signal_series,
        "btc_close": btc_close,
        "eth_close": eth_close,
    }).dropna()
    if len(df) < 30:
        return pd.DataFrame()

    btc_ret = df["btc_close"].pct_change()
    eth_ret = df["eth_close"].pct_change()
    spread_ret = btc_ret - eth_ret

    strat_ret = df["signal"].shift(1) * spread_ret

    # Transaction costs (use BTC spread as proxy for the pair)
    signal_change = df["signal"].diff().abs()
    avg_btc = df["btc_close"].iloc[-100:].mean()
    spread_frac = SYMBOL_SPREAD_PIPS.get(btc_symbol, 5000.0) * 0.01 / avg_btc if avg_btc > 0 else 0.0
    strat_ret = strat_ret - signal_change * spread_frac

    strat_ret = strat_ret.dropna()
    if strat_ret.empty:
        return pd.DataFrame()

    return pd.DataFrame({"BEVS_BTCETH": strat_ret})


# ===================================================================
# Engine-based runner (reuses run_engine_for_asset from edge_search_all)
# ===================================================================

def _run_engine_strategy(name: str, factory, universe: list[str]) -> dict:
    """Run an engine-based strategy across *universe* and return DK-test result."""
    all_returns = pd.DataFrame()
    total_trades = 0

    for sym in universe:
        print(f"  {sym}...", end=" ", flush=True)
        try:
            strategy = factory()
            results = run_engine_for_asset(sym, strategy)
            metrics = compute_per_asset_metrics(results)
            total_trades += metrics.get("n_trades", 0)
            daily_ret = extract_daily_returns(results)
            if not daily_ret.empty:
                all_returns = pd.concat([all_returns, daily_ret], axis=1)
            print(
                f"trades={metrics.get('n_trades', 0)} "
                f"sharpe={metrics.get('sharpe', 0):.3f} "
                f"maxdd={metrics.get('max_dd_pct', 0):.1f}%"
            )
        except Exception as e:
            print(f"ERROR: {e}")

    return _run_dk_test(all_returns, total_trades)


# ===================================================================
# FundingRateArb wrapper — injects synthetic funding rate from momentum
# ===================================================================

class _FundingRateArbWrapper(FundingRateArbitrage):
    """FundingRateArbitrage that generates a synthetic funding rate.

    Uses 20-day price momentum as a proxy for perpetual funding rates.
    Positive momentum → positive funding (longs pay shorts), capped ±0.1%/8h.
    """

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        if "funding_rate" not in kwargs:
            close = ohlcv_data.get("close", [])
            if len(close) >= 20 and close[-20] != 0:
                mom = close[-1] / close[-20] - 1
                kwargs["funding_rate"] = max(-0.001, min(0.001, mom * 0.01))
            else:
                kwargs["funding_rate"] = 0.0
        return super().generate_signal(symbol, ohlcv_data, indicators, regime, **kwargs)


# ===================================================================
# Per-strategy runners
# ===================================================================

def _run_cot_positioning() -> dict:
    """1. COT Positioning — XAUUSD (single-asset, contrarian COT signals)."""
    print("\n--- COT Positioning ---")
    return _run_engine_strategy("COT_Positioning", COTPositioningStrategy, ["XAUUSD"])


def _run_funding_rate_arb() -> dict:
    """2. Funding Rate Arb — BTCUSD (single-asset, crypto funding)."""
    print("\n--- Funding Rate Arb ---")
    return _run_engine_strategy("FundingRateArb", _FundingRateArbWrapper, ["BTCUSD"])


def _run_fomc_drift() -> dict:
    """3. FOMC Drift — all CORE_UNIVERSE assets (multi-asset event drift)."""
    print("\n--- FOMC Drift ---")
    return _run_engine_strategy("FOMC_Drift", FOMCDriftStrategy, list(CORE_UNIVERSE))


def _run_btc_eth_vol_spread() -> dict:
    """4. BTC-ETH Vol Spread — BTCUSD + ETHUSD (relative value)."""
    print("\n--- BTC-ETH Vol Spread ---")
    try:
        btc_df = load_asset_data("BTCUSD")
        eth_df = load_asset_data("ETHUSD")
    except Exception as e:
        print(f"  ERROR loading data: {e}")
        return _empty_result("ERROR")

    btc_vol = btc_df["volume"] if "volume" in btc_df.columns else pd.Series(0.0, index=btc_df.index)
    eth_vol = eth_df["volume"] if "volume" in eth_df.columns else pd.Series(0.0, index=eth_df.index)

    result = compute_bevs_signals(
        btc_close=btc_df["close"],
        btc_volume=btc_vol,
        eth_close=eth_df["close"],
        eth_volume=eth_vol,
    )

    daily_ret = _simulate_bevs_returns(
        "BTCUSD", "ETHUSD", result.signal, btc_df["close"], eth_df["close"],
    )
    if daily_ret.empty:
        return _empty_result("INSUFFICIENT_DATA")

    total_trades = int(result.signal.diff().abs().sum() / 2)
    return _run_dk_test(daily_ret, total_trades)


def _run_eth_vol_confirm() -> dict:
    """5. ETH Vol Confirm — ETHUSD (single-asset, volume confirmation)."""
    print("\n--- ETH Vol Confirm ---")
    try:
        df = load_asset_data("ETHUSD")
    except Exception as e:
        print(f"  ERROR loading data: {e}")
        return _empty_result("ERROR")

    vol = df["volume"] if "volume" in df.columns else pd.Series(0.0, index=df.index)

    result = compute_ethvc_signals(
        close=df["close"],
        highs=df["high"],
        lows=df["low"],
        volume=vol,
    )

    daily_ret = _simulate_signal_returns("ETHUSD", result.signal, df["close"])
    if daily_ret.empty:
        return _empty_result("INSUFFICIENT_DATA")

    total_trades = int(result.signal.diff().abs().sum() / 2)
    return _run_dk_test(daily_ret, total_trades)


def _empty_result(verdict: str = "INSUFFICIENT_DATA") -> dict:
    return {
        "dk_t_stat": 0.0,
        "pooled_sharpe": 0.0,
        "positive_sharpe_count": 0,
        "total_assets": 0,
        "total_days": 0,
        "total_trades": 0,
        "verdict": verdict,
    }


# ===================================================================
# Main
# ===================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Edge search — 5 untested strategies (DK pooled)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "reports" / "edge_search_untested_20260720.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    # Validate data availability
    data_ok: dict[str, bool] = {}
    for sym in set(CORE_UNIVERSE + ["ETHUSD"]):
        try:
            load_asset_data(sym)
            data_ok[sym] = True
        except Exception as e:
            print(f"  data SKIP {sym}: {e}")
            data_ok[sym] = False

    strategies = [
        {
            "name": "COT_Positioning",
            "assets": ["XAUUSD"],
            "runner": _run_cot_positioning,
        },
        {
            "name": "FundingRateArb",
            "assets": ["BTCUSD"],
            "runner": _run_funding_rate_arb,
        },
        {
            "name": "FOMC_Drift",
            "assets": list(CORE_UNIVERSE),
            "runner": _run_fomc_drift,
        },
        {
            "name": "BTC_ETH_Vol_Spread",
            "assets": ["BTCUSD", "ETHUSD"],
            "runner": _run_btc_eth_vol_spread,
        },
        {
            "name": "ETH_Vol_Confirm",
            "assets": ["ETHUSD"],
            "runner": _run_eth_vol_confirm,
        },
    ]

    print(f"\nEdge search (untested) start: {datetime.now(UTC).isoformat()}")
    print(f"Strategies: {len(strategies)}")
    print("GO rule: dk_t>2.0 AND pos_sharpe>=5")

    results: list[dict] = []
    for strat in strategies:
        print(f"\n{'=' * 64}")
        print(f"  Strategy: {strat['name']}")
        print(f"  Assets:   {strat['assets']}")
        print(f"{'=' * 64}")

        # Skip if required data is missing
        missing = [s for s in strat["assets"] if not data_ok.get(s, False)]
        if missing:
            print(f"  SKIP — missing data for {missing}")
            entry = {
                "name": strat["name"],
                "assets": strat["assets"],
                "dk_t": 0.0,
                "sharpe": 0.0,
                "trades": 0,
                "verdict": "MISSING_DATA",
            }
            results.append(entry)
            continue

        try:
            dk = strat["runner"]()
            entry = {
                "name": strat["name"],
                "assets": strat["assets"],
                "dk_t": dk.get("dk_t_stat", 0.0),
                "sharpe": dk.get("pooled_sharpe", 0.0),
                "trades": dk.get("total_trades", 0),
                "verdict": dk.get("verdict", "ERROR"),
            }
            print(
                f"\n  DK-t: {entry['dk_t']:.4f}  "
                f"Sharpe: {entry['sharpe']:.4f}  "
                f"Trades: {entry['trades']}  "
                f"Verdict: {entry['verdict']}"
            )
        except Exception as e:
            print(f"\n  FATAL: {e}")
            traceback.print_exc()
            entry = {
                "name": strat["name"],
                "assets": strat["assets"],
                "dk_t": 0.0,
                "sharpe": 0.0,
                "trades": 0,
                "verdict": "ERROR",
                "error": str(e),
            }
        results.append(entry)

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print("  EDGE SEARCH (UNTESTED) SUMMARY — ranked by DK t-stat")
    print(f"{'=' * 72}")
    results_sorted = sorted(results, key=lambda r: r["dk_t"], reverse=True)
    print(f"  {'Strategy':<28} {'Trades':>7} {'DK-t':>8} {'Sharpe':>8} {'Verdict':<12}")
    print(f"  {'-' * 65}")
    for r in results_sorted:
        print(
            f"  {r['name']:<28} {r['trades']:>7} "
            f"{r['dk_t']:>8.4f} {r['sharpe']:>8.4f} {r['verdict']:<12}"
        )

    go = [r["name"] for r in results_sorted if r["verdict"] == "GO"]
    marginal = [r["name"] for r in results_sorted if r["verdict"] == "MARGINAL"]
    print(f"\n  GO:       {go or 'NONE'}")
    print(f"  MARGINAL: {marginal or 'NONE'}")

    # ------------------------------------------------------------------
    # Output JSON
    # ------------------------------------------------------------------
    payload = {
        "strategies": results_sorted,
        "timestamp": datetime.now(UTC).isoformat(),
        "honest_note": (
            "GO does not equal live-ready. Must still pass label-shuffle, "
            "cost-stress, and not burn sacred holdout until single "
            "pre-committed hypothesis."
        ),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\n  Saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
