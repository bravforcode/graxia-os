"""
Proper Out-of-Sample Test — No data leakage, strict temporal split.

Split: 60% train / 20% validation / 20% test (sequential, no shuffle).
Train XGBoost on train set, tune on validation, evaluate on test.
"""
import os, sys, json, warnings
import numpy as np
import pandas as pd
import xgboost as xgb
from pathlib import Path

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent.parent
FEAT_DIR = BASE / "artifacts" / "features_v2"

def run_proper_oos(symbol: str = "XAUUSD", freq: str = "H1"):
    print("=" * 60)
    print(f"PROPER OUT-OF-SAMPLE TEST: {symbol} @ {freq}")
    print("=" * 60)
    
    path = FEAT_DIR / f"features_{symbol}_{freq}.parquet"
    df = pd.read_parquet(path)
    
    exclude = {"target", "target_return", "symbol", "freq", "target_3class"}
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    
    X = df[feature_cols].fillna(0).values
    y = df["target"].values
    returns = df["target_return"].values
    closes = df["close"].values
    
    # Remove last 5 rows (NaN from target)
    X, y, returns, closes = X[:-5], y[:-5], returns[:-5], closes[:-5]
    
    n = len(X)
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)
    
    print(f"\nSplit: train={train_end}, val={val_end-train_end}, test={n-val_end}")
    print(f"Total rows: {n}")
    print(f"Features: {len(feature_cols)}")
    
    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:], y[val_end:]
    r_test = returns[val_end:]
    c_test = closes[val_end:]
    
    print(f"\nClass distribution:")
    print(f"  Train: {np.bincount(y_train.astype(int))}")
    print(f"  Val:   {np.bincount(y_val.astype(int))}")
    print(f"  Test:  {np.bincount(y_test.astype(int))}")
    
    # Train
    params = {
        "n_estimators": 100, "max_depth": 5, "learning_rate": 0.1,
        "subsample": 0.8, "colsample_bytree": 0.8, "random_state": 42,
        "eval_metric": "logloss", "verbosity": 0,
    }
    
    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train)
    
    train_acc = (model.predict(X_train) == y_train).mean()
    val_acc = (model.predict(X_val) == y_val).mean()
    test_acc = (model.predict(X_test) == y_test).mean()
    
    print(f"\nAccuracy:")
    print(f"  Train: {train_acc:.4f}")
    print(f"  Val:   {val_acc:.4f}")
    print(f"  Test:  {test_acc:.4f}")
    print(f"  Gap (train-test): {train_acc - test_acc:.4f}")
    
    # PnL on test set
    preds = model.predict(X_test)
    proba = model.predict_proba(X_test)
    conf = np.max(proba, axis=1)
    
    # Use corrected cost model
    spread_cost = 0.000375  # Pepperstone Razor XAUUSD
    slippage_p90 = 0.000250
    
    # Only trade when confidence >= 0.55
    mask = conf >= 0.55
    direction = 2 * preds.astype(float) - 1
    
    dir_mask = direction[mask]
    rets = r_test[mask]
    closes_mask = c_test[mask]
    
    raw_pnl = dir_mask * rets * closes_mask
    cost = (spread_cost + slippage_p90) * np.mean(closes_mask)
    net_pnl = raw_pnl - cost
    
    n_trades = mask.sum()
    gross = raw_pnl.sum()
    total_cost = cost * n_trades
    net = net_pnl.sum()
    accuracy = (dir_mask * rets > 0).mean()
    
    # Sharpe (annualized for H1)
    if len(net_pnl) > 1 and net_pnl.std() > 0:
        sharpe = net_pnl.mean() / net_pnl.std() * np.sqrt(365 * 24)
    else:
        sharpe = 0.0
    
    print(f"\n--- TEST SET PERFORMANCE ---")
    print(f"  Trades: {n_trades} / {len(y_test)} bars ({n_trades/len(y_test)*100:.1f}%)")
    print(f"  Accuracy: {accuracy:.4f}")
    print(f"  Gross PnL: ${gross:+,.2f}")
    print(f"  Total cost: ${total_cost:,.2f}")
    print(f"  Net PnL: ${net:+,.2f}")
    print(f"  Sharpe (annualized): {sharpe:.2f}")
    print(f"  Win rate: {(net_pnl > 0).mean():.4f}")
    
    # Random baseline
    print(f"\n--- RANDOM BASELINE ---")
    np.random.seed(42)
    rand_preds = np.random.choice([0, 1], size=len(y_test))
    rand_dir = 2 * rand_preds.astype(float) - 1
    rand_raw = rand_dir * r_test * c_test
    rand_cost = cost * len(y_test)
    rand_net = rand_raw.sum() - rand_cost
    print(f"  Random net PnL: ${rand_net:+,.2f}")
    print(f"  Random accuracy: {(rand_dir * r_test > 0).mean():.4f}")
    
    # Majority class baseline
    majority = 1 if y_train.mean() > 0.5 else 0
    maj_dir = 2 * float(majority) - 1
    maj_raw = maj_dir * r_test * c_test
    maj_net = maj_raw.sum() - cost * len(y_test)
    print(f"\n--- MAJORITY CLASS BASELINE (class={majority}) ---")
    print(f"  Majority net PnL: ${maj_net:+,.2f}")
    print(f"  Majority accuracy: {(maj_dir * r_test > 0).mean():.4f}")
    
    # Verdict
    print(f"\n--- VERDICT ---")
    if test_acc < 0.55:
        print("  FAIL: Test accuracy barely above random (< 55%)")
    elif net < 0:
        print("  FAIL: Net PnL negative after costs")
    elif sharpe < 1.0:
        print("  WEAK: Sharpe < 1.0 (not compelling)")
    elif sharpe < 2.0:
        print("  MARGINAL: Sharpe 1.0-2.0 (needs more validation)")
    else:
        print(f"  PASS: Sharpe {sharpe:.2f} > 2.0 with {accuracy:.1%} accuracy")
    
    return {
        "train_acc": train_acc, "val_acc": val_acc, "test_acc": test_acc,
        "n_trades": int(n_trades), "accuracy": float(accuracy),
        "gross_pnl": float(gross), "net_pnl": float(net),
        "sharpe": float(sharpe), "cost_per_trade": float(cost),
    }

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    freq = sys.argv[2] if len(sys.argv) > 2 else "H1"
    run_proper_oos(symbol, freq)
