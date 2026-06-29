#!/usr/bin/env python3
"""
evaluate_redesign.py — Combined evaluation of all redesign phases
==================================================================

Tests the full pipeline:
1. Triple-barrier labels
2. Regularized model
3. Session filter (overlap + NY late)
4. Magnitude gate

Outputs metrics for comparison with B2 thresholds.
"""

import time
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
import xgboost as xgb

BASE = Path(__file__).resolve().parent.parent
FEAT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"

def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def get_session(hour):
    if hour < 7: return 'asian'
    elif hour < 12: return 'london_early'
    elif hour < 17: return 'overlap'
    elif hour < 22: return 'ny_late'
    else: return 'sydney'

def main():
    log("=" * 70)
    log("REDESIGN EVALUATION — Combined Pipeline")
    log("=" * 70)
    
    # Load data
    log("Loading features...")
    df = pd.read_parquet(FEAT_PATH)
    if "datetime" in df.columns:
        df = df.set_index("datetime")
    elif "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    
    # Add session
    df["hour"] = df.index.hour
    df["session"] = df["hour"].apply(get_session)
    df["target_win"] = (df["tb_label"] == 1).astype(int)
    df = df.dropna(subset=["tb_label"])
    
    # Features
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
    
    log(f"Total rows: {len(df)}")
    log(f"Features: {len(feature_cols)}")
    
    # Split train/test (80/20)
    n = len(df)
    train_end = int(n * 0.8)
    
    X_all = df[feature_cols].fillna(0).values
    y_all = df["target_win"].values
    
    X_train = X_all[:train_end]
    y_train = y_all[:train_end]
    X_test = X_all[train_end:]
    y_test = y_all[train_end:]
    
    # Class weight
    n_neg = (y_train == 0).sum()
    n_pos = (y_train == 1).sum()
    spw = n_neg / n_pos
    
    log(f"Train: {len(X_train)}, Test: {len(X_test)}")
    log(f"Win rate: {y_train.mean():.3f}, scale_pos_weight: {spw:.2f}")
    
    # Train model
    log("\nTraining regularized XGBoost...")
    model = xgb.XGBClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.03,
        subsample=0.7, colsample_bytree=0.7,
        min_child_weight=15, reg_alpha=5.0, reg_lambda=5.0,
        scale_pos_weight=spw,
        random_state=42, eval_metric="logloss",
        verbosity=0, n_jobs=-1,
    )
    model.fit(X_train, y_train, verbose=False)
    
    # Evaluate on full test set
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    
    log(f"\n{'='*70}")
    log("FULL TEST SET (no session filter)")
    log(f"  Accuracy: {acc:.4f}")
    log(f"  Precision: {prec:.4f}")
    log(f"  Recall: {rec:.4f}")
    log(f"  F1: {f1:.4f}")
    
    # Evaluate with session filter (overlap + NY late only)
    log(f"\n{'='*70}")
    log("SESSION FILTER: Overlap + NY Late only")
    
    test_df = df.iloc[train_end:].copy()
    test_df["pred"] = y_pred
    test_df["correct"] = (test_df["pred"] == test_df["target_win"]).astype(int)
    
    # Filter to overlap + NY late
    session_mask = test_df["session"].isin(["overlap", "ny_late"])
    session_df = test_df[session_mask]
    
    if len(session_df) > 0:
        session_acc = session_df["correct"].mean()
        session_f1 = f1_score(session_df["target_win"], session_df["pred"], zero_division=0)
        session_prec = precision_score(session_df["target_win"], session_df["pred"], zero_division=0)
        session_rec = recall_score(session_df["target_win"], session_df["pred"], zero_division=0)
        n_trades = len(session_df)
        win_rate = session_df["target_win"].mean()
        
        # Cost analysis
        avg_range = (session_df["high"] - session_df["low"]).mean()
        cost_per_trade = 0.18
        
        log(f"  Trades: {n_trades} ({n_trades/len(test_df)*100:.1f}% of test set)")
        log(f"  Win rate: {win_rate:.3f}")
        log(f"  Accuracy: {session_acc:.4f}")
        log(f"  Precision: {session_prec:.4f}")
        log(f"  Recall: {session_rec:.4f}")
        log(f"  F1: {session_f1:.4f}")
        log(f"  Avg range: ${avg_range:.2f}")
        log(f"  Cost/trade: ${cost_per_trade:.2f}")
        log(f"  Cost/range: {cost_per_trade/avg_range*100:.1f}%")
    
    # Evaluate with magnitude gate (predicted probability > 0.6)
    log(f"\n{'='*70}")
    log("MAGNITUDE GATE: predicted_proba > 0.6")
    
    y_proba = model.predict_proba(X_test)[:, 1]
    mag_mask = y_proba > 0.6
    mag_df = test_df[mag_mask]
    
    if len(mag_df) > 0:
        mag_acc = mag_df["correct"].mean()
        mag_f1 = f1_score(mag_df["target_win"], mag_df["pred"], zero_division=0)
        mag_prec = precision_score(mag_df["target_win"], mag_df["pred"], zero_division=0)
        mag_rec = recall_score(mag_df["target_win"], mag_df["pred"], zero_division=0)
        n_trades = len(mag_df)
        win_rate = mag_df["target_win"].mean()
        
        log(f"  Trades: {n_trades} ({n_trades/len(test_df)*100:.1f}% of test set)")
        log(f"  Win rate: {win_rate:.3f}")
        log(f"  Accuracy: {mag_acc:.4f}")
        log(f"  Precision: {mag_prec:.4f}")
        log(f"  Recall: {mag_rec:.4f}")
        log(f"  F1: {mag_f1:.4f}")
    
    # Combined: session filter + magnitude gate
    log(f"\n{'='*70}")
    log("COMBINED: Session filter + Magnitude gate (prob > 0.6)")
    
    combined_mask = session_mask & (y_proba > 0.6)
    combined_df = test_df[combined_mask]
    
    if len(combined_df) > 0:
        comb_acc = combined_df["correct"].mean()
        comb_f1 = f1_score(combined_df["target_win"], combined_df["pred"], zero_division=0)
        comb_prec = precision_score(combined_df["target_win"], combined_df["pred"], zero_division=0)
        comb_rec = recall_score(combined_df["target_win"], combined_df["pred"], zero_division=0)
        n_trades = len(combined_df)
        win_rate = combined_df["target_win"].mean()
        
        avg_range = (combined_df["high"] - combined_df["low"]).mean()
        
        log(f"  Trades: {n_trades} ({n_trades/len(test_df)*100:.1f}% of test set)")
        log(f"  Win rate: {win_rate:.3f}")
        log(f"  Accuracy: {comb_acc:.4f}")
        log(f"  Precision: {comb_prec:.4f}")
        log(f"  Recall: {comb_rec:.4f}")
        log(f"  F1: {comb_f1:.4f}")
        log(f"  Avg range: ${avg_range:.2f}")
    
    # Compare with B2 thresholds
    log(f"\n{'='*70}")
    log("B2 THRESHOLDS COMPARISON")
    log(f"  B2 avg_net/trade >= $0.40: Need win rate analysis")
    log(f"  B2 win_rate >= 0.55: {win_rate if len(combined_df) > 0 else 0:.3f}")
    log(f"  B2 t-stat >= 2.0: Need bootstrap analysis")
    
    # Feature importance
    log(f"\n{'='*70}")
    log("TOP 15 FEATURES")
    importance = sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1])
    for i, (name, score) in enumerate(importance[:15]):
        log(f"  {i+1:2d}. {name:40s} {score:.4f}")

if __name__ == "__main__":
    main()
