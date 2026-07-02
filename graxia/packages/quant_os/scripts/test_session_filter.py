#!/usr/bin/env python3
"""
test_session_filter.py — Test model performance by session
==========================================================

Filters data by trading session and evaluates model performance.
"""

import time
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

BASE = Path(__file__).resolve().parent.parent
FEAT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"

def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def get_session(hour):
    """Assign session based on UTC hour."""
    if hour < 7:
        return 'asian'
    elif hour < 12:
        return 'london_early'
    elif hour < 17:
        return 'overlap'
    elif hour < 22:
        return 'ny_late'
    else:
        return 'sydney'

def main():
    log("Loading features...")
    df = pd.read_parquet(FEAT_PATH)

    # Handle index
    if "datetime" in df.columns:
        df = df.set_index("datetime")
    elif "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()

    # Add session labels
    df["hour"] = df.index.hour
    df["session"] = df["hour"].apply(get_session)

    # Create target
    df["target_win"] = (df["tb_label"] == 1).astype(int)
    df = df.dropna(subset=["tb_label"])

    log(f"Total rows: {len(df)}")
    log("Session distribution:")
    session_counts = df["session"].value_counts()
    for session, count in session_counts.items():
        log(f"  {session}: {count} ({count/len(df)*100:.1f}%)")

    # Feature columns
    exclude = {
        "is_long", "next_bar_return", "target", "target_return",
        "target_class", "target_win", "tb_label", "tb_win",
        "tb_tp_mult", "tb_sl_mult", "tb_max_bars",
        "fwd_ret_1bar", "fwd_ret_5bar", "fwd_ret_10bar", "fwd_ret_15bar",
        "open", "high", "low", "close", "volume", "tick_count",
        "symbol", "freq", "hour", "session",
    }
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)
                    and df[c].nunique() > 1]

    log(f"Features: {len(feature_cols)}")

    # Test each session
    sessions = ['asian', 'london_early', 'overlap', 'ny_late', 'sydney']

    import xgboost as xgb

    for session in sessions:
        session_df = df[df["session"] == session].copy()
        if len(session_df) < 100:
            log(f"\n{session}: Too few samples ({len(session_df)}), skipping")
            continue

        # Walk-forward split
        n = len(session_df)
        train_end = int(n * 0.7)

        X_train = session_df[feature_cols].fillna(0).values[:train_end]
        y_train = session_df["target_win"].values[:train_end]
        X_test = session_df[feature_cols].fillna(0).values[train_end:]
        y_test = session_df["target_win"].values[train_end:]

        # Train model
        n_neg = (y_train == 0).sum()
        n_pos = (y_train == 1).sum()
        spw = n_neg / n_pos if n_pos > 0 else 1.0

        model = xgb.XGBClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.03,
            subsample=0.7, colsample_bytree=0.7,
            min_child_weight=15, reg_alpha=5.0, reg_lambda=5.0,
            scale_pos_weight=spw,
            random_state=42, eval_metric="logloss",
            verbosity=0, n_jobs=-1,
        )
        model.fit(X_train, y_train, verbose=False)

        # Evaluate
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        win_rate = y_train.mean()

        # Cost analysis
        avg_range = (session_df["high"] - session_df["low"]).mean()
        cost_per_trade = 0.18  # $0.18 round-trip
        cost_ratio = cost_per_trade / avg_range * 100 if avg_range > 0 else 0

        log(f"\n{'='*60}")
        log(f"SESSION: {session.upper()}")
        log(f"  Samples: {len(session_df)} (train={train_end}, test={len(session_df)-train_end})")
        log(f"  Win rate (train): {win_rate:.3f}")
        log(f"  Avg range: ${avg_range:.2f}")
        log(f"  Cost/range: {cost_ratio:.1f}%")
        log(f"  Model accuracy: {acc:.4f}")
        log(f"  Precision: {prec:.4f}")
        log(f"  Recall: {rec:.4f}")
        log(f"  F1: {f1:.4f}")
        log(f"  Train/test split: {train_end}/{len(session_df)-train_end}")

if __name__ == "__main__":
    main()
