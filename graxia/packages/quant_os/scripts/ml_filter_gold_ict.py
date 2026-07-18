"""
ML Signal Filter for Gold ICT strategies on XAUUSD D1.

Uses Random Forest to filter false signals. For each gi_* strategy:
1. Run batch signal generator to get raw signals
2. Extract features at each signal (RSI, ATR, EMA, volume, etc.)
3. Label each signal as profitable (1) or not (0) based on next 5 bars
4. Train RF classifier on 80% (in-sample), evaluate on 20% (OOS)
5. Compare filtered vs unfiltered performance

Based on TanvirCCC/algo-trading approach (ICT + RF on gold → Sharpe 2.8).

Usage:
  python scripts/ml_filter_gold_ict.py
  python scripts/ml_filter_gold_ict.py --only gi_bos_choch,gi_multi_tf_align
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from graxia.packages.quant_os.paper_engine.strategies.gold_ict_batch import BATCH_REGISTRY

COST_RT_BPS = 0.30
OOS_RATIO = 0.2
FORWARD_BARS = 5  # label: profitable if price moves in signal direction within 5 bars


def load_xauusd_d1() -> pd.DataFrame:
    path = ROOT / "data" / "XAUUSD_D1.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts])
    df = df[df[ts] >= "2005-01-01"].sort_values(ts).reset_index(drop=True)
    if ts != "time":
        df = df.rename(columns={ts: "time"})
    return df


def compute_features(df: pd.DataFrame, idx: int) -> dict | None:
    """Extract features at bar idx for ML filtering."""
    if idx < 60 or idx >= len(df):
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values if "volume" in df.columns else np.ones(len(df))

    c = close[idx]
    if c <= 0:
        return None

    # RSI (14)
    deltas = np.diff(close[max(0, idx - 15):idx + 1])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else 0
    avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else 1e-10
    rsi = 100.0 - (100.0 / (1.0 + avg_gain / max(avg_loss, 1e-10)))

    # ATR (14)
    trs = []
    for j in range(max(1, idx - 14), idx + 1):
        tr = max(
            high[j] - low[j],
            abs(high[j] - close[j - 1]),
            abs(low[j] - close[j - 1]),
        )
        trs.append(tr)
    atr = np.mean(trs) if trs else 0.0

    # EMA positions
    def _ema_val(arr, period):
        if len(arr) < period:
            return np.nan
        alpha = 2.0 / (period + 1)
        ema = np.mean(arr[:period])
        for v in arr[period:]:
            ema = v * alpha + ema * (1 - alpha)
        return ema

    ema9 = _ema_val(close[max(0, idx - 60):idx + 1], 9)
    ema21 = _ema_val(close[max(0, idx - 60):idx + 1], 21)
    ema50 = _ema_val(close[max(0, idx - 60):idx + 1], 50)

    # Volume ratio
    avg_vol = np.mean(volume[max(0, idx - 20):idx]) if idx >= 20 else 1
    vol_ratio = volume[idx] / max(avg_vol, 1)

    # Price vs ATR
    atr_pct = atr / c * 100 if c > 0 else 0

    # Return features
    ret_1 = (c / close[idx - 1] - 1) * 100 if idx >= 1 and close[idx - 1] > 0 else 0
    ret_5 = (c / close[idx - 5] - 1) * 100 if idx >= 5 and close[idx - 5] > 0 else 0
    ret_20 = (c / close[idx - 20] - 1) * 100 if idx >= 20 and close[idx - 20] > 0 else 0

    return {
        "rsi": rsi,
        "atr_pct": atr_pct,
        "ema9_dist": (c / ema9 - 1) * 100 if not np.isnan(ema9) and ema9 > 0 else 0,
        "ema21_dist": (c / ema21 - 1) * 100 if not np.isnan(ema21) and ema21 > 0 else 0,
        "ema50_dist": (c / ema50 - 1) * 100 if not np.isnan(ema50) and ema50 > 0 else 0,
        "ema9_21_spread": (ema9 / ema21 - 1) * 100 if not np.isnan(ema9) and not np.isnan(ema21) and ema21 > 0 else 0,
        "vol_ratio": vol_ratio,
        "ret_1": ret_1,
        "ret_5": ret_5,
        "ret_20": ret_20,
        "high_low_pct": (high[idx] - low[idx]) / c * 100 if c > 0 else 0,
    }


FEATURE_NAMES = [
    "rsi", "atr_pct", "ema9_dist", "ema21_dist", "ema50_dist",
    "ema9_21_spread", "vol_ratio", "ret_1", "ret_5", "ret_20", "high_low_pct",
]


def label_signals(df: pd.DataFrame, directions: np.ndarray, forward_bars: int = FORWARD_BARS) -> np.ndarray:
    """Label each signal: 1 = profitable within forward_bars, 0 = not."""
    close = df["close"].values
    n = len(close)
    labels = np.zeros(n, dtype=int)

    for i in range(n):
        d = directions[i]
        if d == 0 or i + forward_bars >= n:
            continue
        future_close = close[i + forward_bars]
        current_close = close[i]
        if current_close <= 0:
            continue
        pnl_pct = (future_close / current_close - 1) * d
        labels[i] = 1 if pnl_pct > 0 else 0

    return labels


def run_ml_filter(strategy_id: str, df: pd.DataFrame) -> dict:
    """Run ML filter for a single strategy."""
    import inspect
    from graxia.packages.quant_os.paper_engine.strategies.gold_ict_batch import BATCH_REGISTRY

    fn = BATCH_REGISTRY[strategy_id]
    sig = inspect.signature(fn)
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    vol = df["volume"].values.astype(float) if "volume" in df.columns else None

    kwargs = {"close": close, "high": high, "low": low}
    if "volume" in sig.parameters and vol is not None:
        kwargs["volume"] = vol
    result = fn(**kwargs)
    dirs = result.directions

    # Extract features for signal bars only
    signal_indices = np.where(dirs != 0)[0]
    if len(signal_indices) < 50:
        return {
            "strategy": strategy_id,
            "error": f"Only {len(signal_indices)} signals (need >= 50)",
            "n_signals": len(signal_indices),
        }

    # Build feature matrix
    X_list = []
    y_list = []
    valid_indices = []
    labels = label_signals(df, dirs)

    for idx in signal_indices:
        feat = compute_features(df, int(idx))
        if feat is not None:
            X_list.append([feat[f] for f in FEATURE_NAMES])
            y_list.append(labels[idx])
            valid_indices.append(idx)

    if len(X_list) < 50:
        return {
            "strategy": strategy_id,
            "error": f"Only {len(X_list)} valid feature rows (need >= 50)",
            "n_signals": len(signal_indices),
        }

    X = np.array(X_list)
    y = np.array(y_list)

    # Split IS/OOS
    split = int(len(X) * (1 - OOS_RATIO))
    X_is, X_oos = X[:split], X[split:]
    y_is, y_oos = y[:split], y[split:]
    idx_is = valid_indices[:split]
    idx_oos = valid_indices[split:]

    # Train RF
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=6,
        min_samples_leaf=10,
        class_weight="balanced",
        random_state=42,
    )
    rf.fit(X_is, y_is)

    # Predictions
    y_pred_is = rf.predict(X_is)
    y_pred_oos = rf.predict(X_oos)

    # Unfiltered performance (all signals)
    def _bar_sharpe(indices):
        if not indices:
            return 0.0
        rets = []
        for idx in indices:
            if idx + 1 < len(close):
                bar_ret = close[idx + 1] / close[idx] - 1
                rets.append(bar_ret * dirs[idx])
        if not rets:
            return 0.0
        arr = np.array(rets)
        std = float(np.std(arr, ddof=1))
        if std <= 1e-10:
            return 0.0
        return float(np.mean(arr)) / std * math.sqrt(252)

    # Filtered performance (only RF-approved signals)
    def _filtered_sharpe(indices, predictions):
        filtered_idx = [idx for idx, pred in zip(indices, predictions) if pred == 1]
        return _bar_sharpe(filtered_idx), len(filtered_idx)

    unfiltered_sharpe_is = _bar_sharpe(idx_is)
    unfiltered_sharpe_oos = _bar_sharpe(idx_oos)
    filtered_sharpe_is, n_filtered_is = _filtered_sharpe(idx_is, y_pred_is)
    filtered_sharpe_oos, n_filtered_oos = _filtered_sharpe(idx_oos, y_pred_oos)

    # Feature importances
    importances = dict(zip(FEATURE_NAMES, [round(float(x), 4) for x in rf.feature_importances_]))
    top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "strategy": strategy_id,
        "n_signals_total": len(signal_indices),
        "n_signals_valid": len(X_list),
        "n_labels_positive": int(np.sum(y)),
        "label_rate": round(float(np.mean(y)) * 100, 1),
        "is_split": split,
        "oos_split": len(X) - split,
        "rf_accuracy_oos": round(float(accuracy_score(y_oos, y_pred_oos)) * 100, 1),
        "rf_precision_oos": round(float(precision_score(y_oos, y_pred_oos, zero_division=0)) * 100, 1),
        "rf_f1_oos": round(float(f1_score(y_oos, y_pred_oos, zero_division=0)) * 4, 2),
        "unfiltered_sharpe_is": round(unfiltered_sharpe_is, 4),
        "unfiltered_sharpe_oos": round(unfiltered_sharpe_oos, 4),
        "filtered_sharpe_is": round(filtered_sharpe_is, 4),
        "filtered_sharpe_oos": round(filtered_sharpe_oos, 4),
        "n_filtered_is": n_filtered_is,
        "n_filtered_oos": n_filtered_oos,
        "sharpe_improvement_oos": round(filtered_sharpe_oos - unfiltered_sharpe_oos, 4),
        "top_features": top_features,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ML signal filter for Gold ICT strategies")
    parser.add_argument("--only", type=str, default="")
    parser.add_argument("--out", type=str, default=str(ROOT / "reports" / "ml_filter_gold_ict_results.json"))
    args = parser.parse_args()

    print("=" * 70)
    print("  ML SIGNAL FILTER — Random Forest on Gold ICT")
    print("  XAUUSD D1 | OOS last 20%% | RF(100, depth=6)")
    print("=" * 70)

    df = load_xauusd_d1()
    print("  Data: %d D1 bars" % len(df))

    strategies = list(BATCH_REGISTRY.keys())
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        strategies = [s for s in strategies if s in wanted]

    results = []
    for strat_id in strategies:
        print("\n  %s..." % strat_id, flush=True)
        t0 = time.time()
        r = run_ml_filter(strat_id, df)
        t1 = time.time()
        results.append(r)

        if "error" in r:
            print("    SKIP: %s [%.1fs]" % (r["error"], t1 - t0))
        else:
            imp = r["sharpe_improvement_oos"]
            print(
                "    signals=%d  labels+%d%%  RF_acc=%.1f%%  "
                "unfiltered_OOS=%.3f  filtered_OOS=%.3f  improvement=%+.3f [%.1fs]" % (
                    r["n_signals_valid"], r["label_rate"],
                    r["rf_accuracy_oos"],
                    r["unfiltered_sharpe_oos"], r["filtered_sharpe_oos"],
                    imp, t1 - t0,
                )
            )

    # Summary
    valid = [r for r in results if "error" not in r]
    improved = [r for r in valid if r["sharpe_improvement_oos"] > 0]

    print("\n" + "=" * 70)
    print("  ML FILTER SUMMARY — ranked by filtered OOS Sharpe")
    print("=" * 70)
    print("  %-25s %7s %7s %7s %7s %7s" % (
        "Strategy", "Signals", "UnFilt", "Filt", "Improv", "RF_Acc"
    ))
    print("  " + "-" * 65)

    ranked = sorted(valid, key=lambda r: r["filtered_sharpe_oos"], reverse=True)
    for r in ranked:
        print(
            "  %-25s %7d %7.3f %7.3f %+7.3f %6.1f%%" % (
                r["strategy"], r["n_signals_valid"],
                r["unfiltered_sharpe_oos"], r["filtered_sharpe_oos"],
                r["sharpe_improvement_oos"], r["rf_accuracy_oos"],
            )
        )

    print("\n  Improved: %d/%d strategies" % (len(improved), len(valid)))
    if improved:
        best = max(improved, key=lambda r: r["filtered_sharpe_oos"])
        print("  Best: %s (filtered OOS Sharpe=%.3f, improvement=%+.3f)" % (
            best["strategy"], best["filtered_sharpe_oos"], best["sharpe_improvement_oos"]
        ))

    # Save
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "symbol": "XAUUSD",
        "timeframe": "D1",
        "method": "RandomForest(100, depth=6, balanced) on ICT features",
        "oos_ratio": OOS_RATIO,
        "forward_bars": FORWARD_BARS,
        "improved_count": len(improved),
        "total_valid": len(valid),
        "results": results,
        "honest_note": (
            "ML filter improvement does not equal live-ready. "
            "Must still pass label-shuffle, cost-stress, and not burn sacred holdout."
        ),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n  Saved: %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
