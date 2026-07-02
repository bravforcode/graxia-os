#!/usr/bin/env python3
"""
Multi-symbol walk-forward backtest with deflated Sharpe.
Runs on EURUSD/GBPUSD/XAUUSD across M15/H1 with corrected cost model.
"""
import json, sys, time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE / "scripts"))
sys.path.insert(0, str(BASE))

from scripts.backtest_cost import evaluate_backtest

# ── Config ──
SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]
TIMEFRAMES = ["M15", "H1"]
N_FOLDS = 5
TRAIN_RATIO = 0.7
RANDOM_STATE = 42
MIN_TRADES = 10

# Cost calibration (return units) from config/cost_calibration.json
COSTS = {
    "EURUSD":  {"spread": 8e-06, "slippage": 1.8e-05},
    "GBPUSD":  {"spread": 1e-05, "slippage": 4.3e-05},
    "XAUUSD":  {"spread": 5e-05, "slippage": 2.7e-05},
}

def load_data(symbol, tf):
    """Load CSV data from data/ directory."""
    path = BASE / "data" / f"{symbol}_{tf}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    return df

def walk_forward_split(n, n_folds=5, train_ratio=0.7):
    """Generate walk-forward train/test splits."""
    fold_size = n // n_folds
    train_size = int(fold_size * train_ratio)
    splits = []
    for i in range(n_folds):
        start = i * fold_size
        train_end = start + train_size
        test_start = train_end
        test_end = min(start + fold_size, n)
        if test_start < test_end and test_end - test_start >= MIN_TRADES:
            splits.append((start, train_end, test_start, test_end))
    return splits

def compute_features(df, close_col="close"):
    """Compute simple features for walk-forward."""
    close = df[close_col].values.astype(float)
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    
    features = pd.DataFrame(index=df.index)
    features["return_1"] = returns
    features["return_5"] = pd.Series(returns).rolling(5).mean().values
    features["return_10"] = pd.Series(returns).rolling(10).mean().values
    features["return_20"] = pd.Series(returns).rolling(20).mean().values
    features["vol_10"] = pd.Series(returns).rolling(10).std().values
    features["vol_20"] = pd.Series(returns).rolling(20).std().values
    features["vol_ratio"] = features["vol_10"] / (features["vol_20"] + 1e-10)
    features["close"] = close
    features["target"] = (returns > 0).astype(int)
    features["target_return"] = returns
    features = features.dropna()
    return features

def run_walk_forward(df, symbol, tf):
    """Run walk-forward backtest with deflated Sharpe."""
    features = compute_features(df)
    if len(features) < 500:
        return None
    
    close_col = "close"
    feature_cols = [c for c in features.columns if c not in ["target", "target_return", close_col]]
    X = features[feature_cols].values.astype(np.float32)
    y = features["target"].values
    close_prices = features[close_col].values
    returns = features["target_return"].values
    
    costs = COSTS.get(symbol, COSTS["XAUUSD"])
    spread_cost = costs["spread"]
    slippage_p90 = costs["slippage"]
    
    splits = walk_forward_split(len(X), N_FOLDS, TRAIN_RATIO)
    if not splits:
        return None
    
    # Only evaluate at confidence thresholds that filter trades
    CONF_THRESHOLDS = [0.0, 0.55, 0.65, 0.75, 0.85]
    
    fold_results = []
    for fold_idx, (train_start, train_end, test_start, test_end) in enumerate(splits):
        X_train, X_test = X[train_start:test_start], X[test_start:test_end]
        y_train, y_test = y[train_start:test_start], y[test_start:test_end]
        close_test = close_prices[test_start:test_end]
        returns_test = returns[test_start:test_end]
        
        if len(X_train) < 50 or len(X_test) < MIN_TRADES:
            continue
        
        model = xgb.XGBClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=RANDOM_STATE, eval_metric="logloss",
            verbosity=0, n_jobs=-1,
        )
        model.fit(X_train, y_train)
        
        # Get confidence scores
        proba = model.predict_proba(X_test)
        conf = np.max(proba, axis=1)
        preds = model.predict(X_test)
        
        # Evaluate at multiple thresholds
        for conf_thresh in CONF_THRESHOLDS:
            trade_mask = conf >= conf_thresh
            n_trades = trade_mask.sum()
            if n_trades < MIN_TRADES:
                continue
            
            # Create filtered dataframe
            df_test = features.iloc[test_start:test_end].reset_index(drop=True)
            df_test["close"] = close_test
            filtered = df_test[trade_mask]
            filtered_preds = preds[trade_mask]
            
            result = evaluate_backtest(
                filtered, model, feature_cols,
                pd.Series(True, index=filtered.index),
                spread_cost=spread_cost, slippage_p90=slippage_p90, lot_mult=1.0,
                min_confidence=0.0, min_regime=0.0,
            )
            result["fold"] = fold_idx
            result["conf_thresh"] = conf_thresh
            fold_results.append(result)
    
    if not fold_results:
        return None
    
    # Find best threshold across folds
    best_thresh = 0
    best_net = -999
    for thresh in CONF_THRESHOLDS:
        thresh_folds = [r for r in fold_results if r["conf_thresh"] == thresh]
        if thresh_folds:
            avg_net = np.mean([r["net_pnl"] for r in thresh_folds])
            if avg_net > best_net:
                best_net = avg_net
                best_thresh = thresh
    
    best_folds = [r for r in fold_results if r["conf_thresh"] == best_thresh]
    total_trades = sum(r["n_trades"] for r in best_folds)
    total_gross = sum(r["gross_pnl"] for r in best_folds)
    total_cost = sum(r["total_cost"] for r in best_folds)
    total_net = sum(r["net_pnl"] for r in best_folds)
    
    # Deflated Sharpe
    sharpes = [r["sharpe_ratio"] for r in best_folds if r["n_trades"] > 0 and r["sharpe_ratio"] != 0]
    avg_sharpe = np.mean(sharpes) if sharpes else 0
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ds", str(BASE / "validation" / "deflated_sharpe.py"))
        ds_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ds_mod)
        ds_result = ds_mod.deflated_sharpe_ratio(
            observed_sharpe=avg_sharpe,
            n_trials=N_FOLDS * len(CONF_THRESHOLDS),
            n_observations=total_trades,
        )
        deflated_sharpe = ds_result.deflated_sharpe
        ds_pass = ds_result.passes_threshold
    except Exception:
        deflated_sharpe = avg_sharpe
        ds_pass = False
    
    return {
        "symbol": symbol,
        "timeframe": tf,
        "best_conf_thresh": best_thresh,
        "total_trades": total_trades,
        "total_gross": round(total_gross, 2),
        "total_cost": round(total_cost, 2),
        "total_net": round(total_net, 2),
        "avg_sharpe": round(avg_sharpe, 2),
        "deflated_sharpe": round(deflated_sharpe, 2),
        "ds_pass": ds_pass,
        "n_folds": len(best_folds),
        "fold_nets": [round(r["net_pnl"], 2) for r in best_folds],
    }

def main():
    print("=" * 70)
    print("MULTI-SYMBOL WALK-FORWARD + DEFLATED SHARPE")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Timeframes: {TIMEFRAMES}")
    print(f"  Folds: {N_FOLDS}, Train ratio: {TRAIN_RATIO}")
    print("=" * 70)
    
    results = []
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"\n--- {sym} {tf} ---")
            df = load_data(sym, tf)
            if df is None:
                print("  SKIP: no data")
                continue
            print(f"  Data: {len(df)} bars")
            
            t0 = time.time()
            result = run_walk_forward(df, sym, tf)
            elapsed = time.time() - t0
            
            if result:
                results.append(result)
                status = "PASS" if result["ds_pass"] else "FAIL"
                print(f"  Trades: {result['total_trades']}, Net: ${result['total_net']:+.2f}, "
                      f"Sharpe: {result['avg_sharpe']:.1f}, Deflated: {result['deflated_sharpe']:.1f} [{status}]")
                print(f"  Fold nets: {result['fold_nets']}")
            else:
                print("  SKIP: insufficient data")
            print(f"  Time: {elapsed:.1f}s")
    
    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"{'Symbol':10s} {'TF':5s} {'Trades':>7s} {'Gross':>8s} {'Cost':>8s} {'Net':>8s} {'Sharpe':>7s} {'Deflated':>9s} {'DS?':>4s}")
    print("-" * 80)
    for r in results:
        ds = "PASS" if r["ds_pass"] else "FAIL"
        print(f"{r['symbol']:10s} {r['timeframe']:5s} {r['total_trades']:>7d} "
              f"${r['total_gross']:>+7.2f} ${r['total_cost']:>7.2f} ${r['total_net']:>+7.2f} "
              f"{r['avg_sharpe']:>7.1f} {r['deflated_sharpe']:>9.1f} {ds:>4s}")
    
    # Save
    out_path = BASE / "artifacts" / "walk_forward" / "multi_symbol_wf.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out_path}")

if __name__ == "__main__":
    main()
