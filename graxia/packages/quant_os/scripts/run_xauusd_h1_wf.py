#!/usr/bin/env python3
"""Quick walk-forward + deflated Sharpe for XAUUSD H1."""

import importlib.util
import sys
import time

import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from backtest_cost import evaluate_backtest

# Load data
df = pd.read_csv("data/XAUUSD_H1.csv")
df["time"] = pd.to_datetime(df["time"], utc=True)
df = df.set_index("time")
print(f"XAUUSD H1: {len(df)} bars, {df.index[0]} to {df.index[-1]}")

# Features
close = df["close"].values.astype(float)
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
print(f"Features: {len(features)} rows")

feature_cols = [c for c in features.columns if c not in ["target", "target_return", "close"]]
X = features[feature_cols].values.astype(np.float32)
y = features["target"].values
close_prices = features["close"].values

N_FOLDS = 5
TRAIN_RATIO = 0.7
fold_size = len(X) // N_FOLDS
train_size = int(fold_size * TRAIN_RATIO)
CONF_THRESHOLDS = [0.0, 0.55, 0.65, 0.75, 0.85]
MIN_TRADES = 10
spread_cost = 0.00005
slippage_p90 = 0.000027

print(f"\nWalk-Forward: {N_FOLDS} folds, train_ratio={TRAIN_RATIO:.1f}")

results_by_thresh: dict[float, list] = {t: [] for t in CONF_THRESHOLDS}
t0 = time.time()

for fold_idx in range(N_FOLDS):
    start = fold_idx * fold_size
    train_end = start + train_size
    test_start = train_end
    test_end = min(start + fold_size, len(X))
    if test_start >= test_end or test_end - test_start < MIN_TRADES:
        continue
    X_train, X_test = X[start:train_end], X[test_start:test_end]
    y_train, y_test = y[start:train_end], y[test_start:test_end]
    close_test = close_prices[test_start:test_end]
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)
    conf = np.max(proba, axis=1)
    for conf_thresh in CONF_THRESHOLDS:
        trade_mask = conf >= conf_thresh
        n_trades = trade_mask.sum()
        if n_trades < MIN_TRADES:
            continue
        df_test = features.iloc[test_start:test_end].reset_index(drop=True)
        df_test["close"] = close_test
        filtered = df_test[trade_mask]
        result = evaluate_backtest(
            filtered,
            model,
            feature_cols,
            pd.Series(True, index=filtered.index),
            spread_cost=spread_cost,
            slippage_p90=slippage_p90,
            lot_mult=1.0,
            min_confidence=0.0,
            min_regime=0.0,
        )
        result["fold"] = fold_idx
        result["conf_thresh"] = conf_thresh
        results_by_thresh[conf_thresh].append(result)

elapsed = time.time() - t0
print(f"Completed in {elapsed:.1f}s")

# Deflated Sharpe
spec = importlib.util.spec_from_file_location("ds", "validation/deflated_sharpe.py")
assert spec is not None and spec.loader is not None
ds_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds_mod)

print(
    "\n{:6s} | {:>7s} | {:>8s} | {:>8s} | {:>8s} | {:>7s} | {}".format(
        "Conf", "Trades", "Gross", "Cost", "Net", "Sharpe", "Fold Nets"
    )
)
print("-" * 100)

for thresh in CONF_THRESHOLDS:
    folds = results_by_thresh[thresh]
    if not folds:
        continue
    total_trades = sum(r["n_trades"] for r in folds)
    total_gross = sum(r["gross_pnl"] for r in folds)
    total_cost = sum(r["total_cost"] for r in folds)
    total_net = sum(r["net_pnl"] for r in folds)
    sharpes = [r["sharpe_ratio"] for r in folds if r["n_trades"] > 0 and r["sharpe_ratio"] != 0]
    avg_sharpe = np.mean(sharpes) if sharpes else 0
    fold_nets = [round(r["net_pnl"], 2) for r in folds]
    ds = ds_mod.dsr_from_annualized(
        avg_sharpe, N_FOLDS * len(CONF_THRESHOLDS), total_trades, annualization_factor=252
    )  # SP1: sharpe annualized per-trade by backtest_cost.evaluate_backtest (sqrt(min(trades,252))); NOT 6096 despite H1 data
    ds_sharpe = ds.deflated_sharpe
    ds_pass = ds.passes_threshold
    status = "PASS" if ds_pass else "FAIL"
    print(
        f"{thresh:6.2f} | {total_trades:7d} | ${total_gross:+7.2f} | ${total_cost:7.2f} | "
        f"${total_net:+7.2f} | {avg_sharpe:7.1f} | {fold_nets} | DS={ds_sharpe:+.1f} [{status}]"
    )
