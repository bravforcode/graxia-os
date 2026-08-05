#!/usr/bin/env python3
"""
Batch Walk-Forward Validation — 14 Instruments (13 new + XAUUSD)
Runs the canonical walk-forward pipeline on each symbol and aggregates results.

Uses:
  - validation/walk_forward.py (canonical engine with purge/embargo)
  - config/cost_calibration.json (measured Pepperstone costs)

Instruments:
  Forex:  GBPUSD, USDJPY, USDCAD, USDCHF, AUDUSD, NZDUSD
  Crypto: BTCUSD, ETHUSD
  Indices: NAS100, US30
  Metals: XAUUSD, XAGUSD, XPDUSD, XPTUSD

Usage:
    python scripts/run_multi_instrument_wf.py
    python scripts/run_multi_instrument_wf.py --timeframe H1
    python scripts/run_multi_instrument_wf.py --timeframe M15 --verbose
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from validation.walk_forward import run_walk_forward

# ── Constants ────────────────────────────────────────────────────────────
ALL_SYMBOLS = [
    "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "NZDUSD",
    "BTCUSD", "ETHUSD",
    "NAS100", "US30",
    "XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD",
]

DEFAULT_TIMEFRAME = "H1"
TRAIN_WINDOW = 500
TEST_WINDOW = 200
STEP = 200
PURGE_BARS = 14
EMBARGO_BARS = 0
MIN_CONFIDENCE = 0.65
N_ESTIMATORS = 100
MAX_DEPTH = 5
SEED = 42


# ── Data Loading ─────────────────────────────────────────────────────────
def load_data(symbol: str, timeframe: str, data_dir: Path) -> pd.DataFrame | None:
    """Load OHLCV data from CSV, then parquet, then DuckDB — matching
    the existing run_walk_forward.py pattern."""
    # Try CSV first
    csv_path = data_dir / f"{symbol}_{timeframe}.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)
            df = df.set_index("time")
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp")
        return df

    # Try parquet
    from glob import glob as glob_glob
    parquet_patterns = [
        data_dir / f"**" / f"*{symbol}_{timeframe}*.parquet",
        data_dir / f"**" / f"*{symbol}*{timeframe}*.parquet",
    ]
    for pat in parquet_patterns:
        paths = sorted(glob_glob(str(pat), recursive=True))
        if paths:
            dfs = []
            for p in paths:
                part = pd.read_parquet(p)
                time_col = "time" if "time" in part.columns else "timestamp"
                if time_col in part.columns:
                    part = part.set_index(time_col)
                part.index = pd.to_datetime(part.index, utc=True)
                keep = [c for c in ["open", "high", "low", "close", "volume"] if c in part.columns]
                dfs.append(part[keep])
            return pd.concat(dfs).sort_index().drop_duplicates()

    return None


# ── Cost Calibration ─────────────────────────────────────────────────────
def load_cost_calibration() -> dict:
    """Load measured costs from config/cost_calibration.json and convert
    round-trip bps to per-trade return units."""
    config_path = BASE / "config" / "cost_calibration.json"
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        raw = json.load(f)

    costs = {}
    symbol_map = {s: s for s in ALL_SYMBOLS}
    symbol_map["SILVER"] = "XAGUSD"  # MT5 name -> our name

    for mt5_sym, asset_data in raw.get("assets", {}).items():
        our_sym = symbol_map.get(mt5_sym, mt5_sym)
        if our_sym not in ALL_SYMBOLS:
            continue

        rt_bps = asset_data.get("round_trip_bps_measured", 0)
        # Per-trade cost = half of round-trip, in return units (bps / 10000)
        per_trade_return = (rt_bps / 2.0) / 10000.0
        costs[our_sym] = {
            "spread": per_trade_return * 0.5,
            "slippage": per_trade_return * 0.5,
            "round_trip_bps": rt_bps,
        }
    return costs


# ── Feature Engineering ──────────────────────────────────────────────────
def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical features for walk-forward validation."""
    result = df.copy()
    close = result["close"]

    # Returns
    result["return_1"] = close.pct_change(1)
    result["return_5"] = close.pct_change(5)
    result["return_10"] = close.pct_change(10)
    result["return_20"] = close.pct_change(20)

    # Volatility
    result["vol_10"] = result["return_1"].rolling(10).std()
    result["vol_20"] = result["return_1"].rolling(20).std()
    result["vol_ratio"] = result["vol_10"] / (result["vol_20"] + 1e-10)

    # ATR
    tr = pd.concat([
        result["high"] - result["low"],
        (result["high"] - close.shift(1)).abs(),
        (result["low"] - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    result["atr_14"] = tr.rolling(14).mean()
    result["atr_ratio"] = result["atr_14"] / (result["atr_14"].rolling(50).mean() + 1e-10)

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    result["rsi_14"] = 100 - (100 / (1 + rs))
    result["rsi_normalized"] = (result["rsi_14"] - 50) / 50

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    result["macd"] = ema12 - ema26
    result["macd_signal"] = result["macd"].ewm(span=9).mean()
    result["macd_hist"] = result["macd"] - result["macd_signal"]

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    result["bb_width"] = (2 * bb_std) / (bb_mid + 1e-10)
    result["bb_position"] = (close - bb_mid) / (bb_std + 1e-10)

    # Session features
    if hasattr(result.index, "hour"):
        result["hour"] = result.index.hour
        result["is_asian"] = ((result["hour"] >= 0) & (result["hour"] < 8)).astype(int)
        result["is_london"] = ((result["hour"] >= 8) & (result["hour"] < 17)).astype(int)
        result["is_ny"] = ((result["hour"] >= 13) & (result["hour"] < 22)).astype(int)

    # Target: next bar direction
    result["target"] = (close.shift(-1) > close).astype(int)
    result["target_return"] = close.pct_change(1).shift(-1)

    result = result.dropna()
    return result


# ── Walk-Forward Runner ──────────────────────────────────────────────────
def run_wf_single(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    spread_cost: float,
    slippage_p90: float,
) -> dict:
    """Run canonical walk-forward for one symbol."""
    features = compute_features(df)
    min_bars = TRAIN_WINDOW + TEST_WINDOW + PURGE_BARS + 100
    if len(features) < min_bars:
        return {"symbol": symbol, "status": "INSUFFICIENT_DATA", "bars": len(features)}

    # Feature columns (exclude target/price/metadata)
    exclude = {"target", "target_return", "close", "open", "high", "low",
               "volume", "hour", "symbol", "freq"}
    feature_cols = [c for c in features.columns if c not in exclude]

    model_params = {
        "n_estimators": N_ESTIMATORS,
        "max_depth": MAX_DEPTH,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": SEED,
        "eval_metric": "logloss",
        "verbosity": 0,
        "n_jobs": 1,
    }

    try:
        result = run_walk_forward(
            df=features,
            feature_cols=feature_cols,
            model_params=model_params,
            train_window=TRAIN_WINDOW,
            test_window=TEST_WINDOW,
            step=STEP,
            spread_cost=spread_cost,
            slippage_p90=slippage_p90,
            min_confidence=MIN_CONFIDENCE,
            min_expected_profit=0.0005,
            purge_bars=PURGE_BARS,
            embargo_bars=EMBARGO_BARS,
            label_mode="binary",
        )
    except Exception as e:
        return {"symbol": symbol, "status": f"ERROR: {e}", "bars": len(features)}

    agg = result.get("aggregate", {})
    folds = result.get("folds", [])
    params = result.get("params", {})

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "OK",
        "bars_total": len(df),
        "bars_features": len(features),
        "n_folds": agg.get("n_folds", 0),
        "total_trades": agg.get("total_trades", 0),
        "total_net_pnl": agg.get("total_net", 0),
        "positive_folds": agg.get("positive_folds", 0),
        "negative_folds": agg.get("negative_folds", 0),
        "positive_pct": round(
            agg.get("positive_folds", 0) / max(agg.get("n_folds", 1), 1) * 100, 1
        ),
        "weighted_accuracy": agg.get("weighted_accuracy", 0),
        "t_statistic": agg.get("net_stability_t", 0),
        "avg_net_per_fold": agg.get("avg_net_per_fold", 0),
        "purge_bars": params.get("purge_bars", PURGE_BARS),
        "embargo_bars": params.get("embargo_bars", EMBARGO_BARS),
        "fold_nets": [round(f.get("net_pnl", 0), 2) for f in folds],
        "fold_details": [
            {
                "fold": f.get("fold", i),
                "n_trades": f.get("n_trades", 0),
                "net_pnl": round(f.get("net_pnl", 0), 2),
                "accuracy": f.get("accuracy", 0),
                "oos_acc": f.get("oos_acc", 0),
                "sharpe_ratio": f.get("sharpe_ratio", 0),
            }
            for i, f in enumerate(folds)
        ],
    }


# ── Verdict Logic ────────────────────────────────────────────────────────
def determine_verdict(result: dict) -> tuple[str, str]:
    """Determine promotion verdict from walk-forward results."""
    if result.get("status") != "OK":
        return "SKIP", result.get("status", "Unknown")

    n_folds = result.get("n_folds", 0)
    positive_folds = result.get("positive_folds", 0)
    total_net = result.get("total_net_pnl", 0)
    t_stat = result.get("t_statistic", 0)
    positive_pct = positive_folds / max(n_folds, 1)

    if positive_pct > 0.6 and total_net > 0 and abs(t_stat) >= 1.5:
        return "PROMOTE", (
            f"Edge stable: {positive_folds}/{n_folds} folds positive "
            f"({positive_pct:.0%}), net=${total_net:+.2f}, t={t_stat:.2f}"
        )

    if positive_pct > 0.4 and total_net > 0:
        return "CONDITIONAL", (
            f"Edge emerging: {positive_folds}/{n_folds} folds positive, "
            f"net=${total_net:+.2f}, t={t_stat:.2f}. Needs more data."
        )

    if abs(t_stat) >= 2.0 and total_net < 0:
        return "REJECT", (
            f"Significant loss: net=${total_net:+.2f}, t={t_stat:.2f}. "
            f"Do not trade."
        )

    if not (abs(t_stat) >= 2.0):
        return "INCONCLUSIVE", (
            f"t={t_stat:.2f} (not significant). "
            f"Need more folds or data."
        )

    return "REJECT", f"No edge: net=${total_net:+.2f}, t={t_stat:.2f}"


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Batch Walk-Forward — 14 Instruments")
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--data-dir", default=str(BASE / "data"))
    parser.add_argument("--output-dir", default=str(BASE / "artifacts" / "wf_13_instruments"))
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.65,
        help="Model confidence threshold for taking a trade (Trial 9001 Direction H freezes 0.55; original batch used 0.65)",
    )
    parser.add_argument("--allow-default-costs", action="store_true",
                        help="Allow unmeasured default costs for missing symbols (testing only)")
    args = parser.parse_args()

    # Frozen-parameter override (Trial 9001 pre-registration): min_confidence
    # is passed explicitly so the runner constant stays backward-compatible.
    global MIN_CONFIDENCE
    MIN_CONFIDENCE = args.min_confidence

    symbols = args.symbols or ALL_SYMBOLS
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = Path(args.data_dir)

    costs = load_cost_calibration()

    print("=" * 80)
    print("  BATCH WALK-FORWARD VALIDATION — 14 INSTRUMENTS")
    print(f"  Timeframe: {args.timeframe}")
    print(f"  Symbols: {len(symbols)}")
    print(f"  WF windows: train={TRAIN_WINDOW} test={TEST_WINDOW} step={STEP}")
    print(f"  Purge: {PURGE_BARS} bars, Embargo: {EMBARGO_BARS} bars")
    print(f"  Output: {output_dir}")
    print("=" * 80)
    print()

    _DEFAULT_COSTS = {"spread": 1e-05, "slippage": 3e-05}

    all_results = []
    start_time = time.time()

    for sym in symbols:
        if sym in costs:
            sym_costs = costs[sym]
            cost_source = "calibrated"
        elif args.allow_default_costs:
            sym_costs = _DEFAULT_COSTS
            cost_source = "DEFAULT (UNMEASURED)"
            print(f"  WARNING: {sym} not in cost_calibration.json - "
                  f"using UNMEASURED defaults (spread=1e-05, slippage=3e-05). "
                  f"Results for this symbol are NOT trustworthy.")
        else:
            print(f"  ERROR: {sym} not found in cost_calibration.json. "
                  f"Run cost calibration first, or use --allow-default-costs (testing only).")
            all_results.append({"symbol": sym, "status": "NO_COST_DATA"})
            continue

        print(f"--- {sym} ---")
        print(f"  Costs: source={cost_source}, "
              f"spread={sym_costs['spread']:.2e}, "
              f"slippage={sym_costs['slippage']:.2e}, "
              f"rt_bps={sym_costs.get('round_trip_bps', 'N/A')}")

        df = load_data(sym, args.timeframe, data_dir)
        if df is None:
            print(f"  SKIP: no data found for {sym}_{args.timeframe}")
            all_results.append({"symbol": sym, "status": "NO_DATA"})
            continue

        print(f"  Data: {len(df)} bars")

        t0 = time.time()
        result = run_wf_single(
            symbol=sym,
            timeframe=args.timeframe,
            df=df,
            spread_cost=sym_costs["spread"],
            slippage_p90=sym_costs["slippage"],
        )
        elapsed = time.time() - t0

        verdict, reason = determine_verdict(result)
        result["verdict"] = verdict
        result["verdict_reason"] = reason
        result["elapsed_s"] = round(elapsed, 1)

        all_results.append(result)

        status = result.get("status", "?")
        if status == "OK":
            print(f"  Folds: {result['n_folds']}, Trades: {result['total_trades']}, "
                  f"Net: ${result['total_net_pnl']:+.2f}, "
                  f"Positive: {result['positive_folds']}/{result['n_folds']} "
                  f"({result['positive_pct']}%), "
                  f"t={result['t_statistic']:.2f}")
            print(f"  Verdict: {verdict} — {reason}")
        else:
            print(f"  Status: {status}")
        print(f"  Time: {elapsed:.1f}s")
        print()

    total_elapsed = time.time() - start_time

    # ── Summary ──
    print("=" * 80)
    print("  RESULTS SUMMARY")
    print("=" * 80)
    print(f"{'Symbol':10s} {'Status':12s} {'Trades':>7s} {'Net PnL':>10s} {'Pos%':>6s} "
          f"{'t-stat':>7s} {'Verdict':>12s}")
    print("-" * 80)

    for r in all_results:
        sym = r.get("symbol", "?")
        status = r.get("status", "?")
        if status == "OK":
            print(f"{sym:10s} {'OK':12s} {r['total_trades']:>7d} "
                  f"${r['total_net_pnl']:>+9.2f} {r['positive_pct']:>5.1f}% "
                  f"{r['t_statistic']:>7.2f} {r['verdict']:>12s}")
        else:
            print(f"{sym:10s} {status:12s} {'—':>7s} {'—':>10s} {'—':>6s} {'—':>7s} {'—':>12s}")

    print("-" * 80)

    verdicts = [r.get("verdict", "SKIP") for r in all_results]
    print(f"\nVerdicts: PROMOTE={verdicts.count('PROMOTE')}, "
          f"CONDITIONAL={verdicts.count('CONDITIONAL')}, "
          f"INCONCLUSIVE={verdicts.count('INCONCLUSIVE')}, "
          f"REJECT={verdicts.count('REJECT')}, "
          f"SKIP={verdicts.count('SKIP')}")
    print(f"Total time: {total_elapsed:.1f}s")

    # Save results
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "timeframe": args.timeframe,
        "parameters": {
            "train_window": TRAIN_WINDOW,
            "test_window": TEST_WINDOW,
            "step": STEP,
            "purge_bars": PURGE_BARS,
            "embargo_bars": EMBARGO_BARS,
            "min_confidence": MIN_CONFIDENCE,
            "n_estimators": N_ESTIMATORS,
            "max_depth": MAX_DEPTH,
            "seed": SEED,
        },
        "results": all_results,
        "summary": {
            "total_instruments": len(symbols),
            "promote": verdicts.count("PROMOTE"),
            "conditional": verdicts.count("CONDITIONAL"),
            "inconclusive": verdicts.count("INCONCLUSIVE"),
            "reject": verdicts.count("REJECT"),
            "skip": verdicts.count("SKIP"),
            "total_elapsed_s": round(total_elapsed, 1),
        },
    }

    report_path = output_dir / f"wf_batch_{args.timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
