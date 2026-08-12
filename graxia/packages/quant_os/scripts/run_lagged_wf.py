#!/usr/bin/env python3
"""
Walk-forward with LAGGED features only (no data leakage).
Tests XAUUSD/EURUSD/GBPUSD across H1/M15.
"""
import pandas as pd
import numpy as np
import xgboost as xgb
import time

COSTS = {
    "XAUUSD": {"spread": 5e-05, "slippage": 2.7e-05},
    "EURUSD": {"spread": 8e-06, "slippage": 1.8e-05},
    "GBPUSD": {"spread": 1e-05, "slippage": 4.3e-05},
}

def compute_features_lagged(df):
    """Compute features using ONLY lagged data (no leakage)."""
    close = df["close"].values.astype(float)
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    
    # Target: NEXT bar's return direction
    target = np.concatenate([returns[1:], [0]])
    
    # Features: ALL lagged by at least 1 bar
    r1_lag = np.concatenate([[0], returns[:-1]])  # lagged 1
    r5_lag = pd.Series(returns).rolling(5).mean().shift(1).values  # lagged 5
    r10_lag = pd.Series(returns).rolling(10).mean().shift(1).values
    r20_lag = pd.Series(returns).rolling(20).mean().shift(1).values
    v10_lag = pd.Series(returns).rolling(10).std().shift(1).values
    v20_lag = pd.Series(returns).rolling(20).std().shift(1).values
    vr_lag = v10_lag / (v20_lag + 1e-10)
    
    # Momentum features (lagged)
    mom5_lag = pd.Series(returns).rolling(5).sum().shift(1).values
    mom10_lag = pd.Series(returns).rolling(10).sum().shift(1).values
    
    features = np.column_stack([
        r1_lag, r5_lag, r10_lag, r20_lag,
        v10_lag, v20_lag, vr_lag,
        mom5_lag, mom10_lag,
    ])
    
    valid = ~np.isnan(features).any(axis=1)
    X = features[valid].astype(np.float32)
    y = ((target > 0)).astype(int)[valid]
    
    return X, y

def run_walk_forward(symbol, tf, n_folds=5):
    """Run walk-forward with lagged features."""
    path = "data/%s_%s.csv" % (symbol, tf)
    try:
        df = pd.read_csv(path)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    except:
        return None
    
    X, y = compute_features_lagged(df)
    if len(X) < 500:
        return None
    
    costs = COSTS.get(symbol, COSTS["XAUUSD"])
    spread = costs["spread"]
    slip = costs["slippage"]
    
    fold_size = len(X) // n_folds
    train_size = int(fold_size * 0.7)
    
    results = {}
    for ct in [0.0, 0.55, 0.65, 0.75, 0.85]:
        fold_nets = []
        for fold_idx in range(n_folds):
            start = fold_idx * fold_size
            train_end = start + train_size
            test_start = train_end
            test_end = min(start + fold_size, len(X))
            
            if test_start >= test_end or test_end - test_start < 10:
                continue
            
            X_train, X_test = X[start:train_end], X[test_start:test_end]
            y_train, y_test = y[start:train_end], y[test_start:test_end]
            
            m = xgb.XGBClassifier(
                n_estimators=50, max_depth=3, learning_rate=0.1,
                subsample=0.8, colsample_bytree=0.8,
                random_state=42, eval_metric="logloss", verbosity=0, n_jobs=-1,
            )
            m.fit(X_train, y_train)
            proba = m.predict_proba(X_test)
            conf = np.max(proba, axis=1)
            preds = m.predict(X_test)
            
            trade_mask = conf >= ct
            n_trades = trade_mask.sum()
            if n_trades < 5:
                continue
            
            correct = (preds == y_test)[trade_mask]
            wins = correct.sum()
            losses = (~correct).sum()
            
            # P&L: win = +0.0001, loss = -0.00005
            gross = (wins * 0.0001 - losses * 0.00005) * 2350.0
            cost = (spread + slip) * 2350.0 * n_trades
            net = gross - cost
            
            fold_nets.append({"trades": n_trades, "wins": int(wins), "losses": int(losses), "net": net})
        
        if fold_nets:
            total_trades = sum(f["trades"] for f in fold_nets)
            total_wins = sum(f["wins"] for f in fold_nets)
            total_losses = sum(f["losses"] for f in fold_nets)
            total_net = sum(f["net"] for f in fold_nets)
            avg_net = total_net / len(fold_nets)
            
            # Deflated Sharpe
            win_rate = total_wins / total_trades if total_trades > 0 else 0
            avg_win = 0.0001 * 2350.0 if total_wins > 0 else 0
            avg_loss = -0.00005 * 2350.0 if total_losses > 0 else 0
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
            
            results[ct] = {
                "trades": total_trades,
                "wins": total_wins,
                "losses": total_losses,
                "win_rate": win_rate,
                "total_net": total_net,
                "avg_net_per_fold": avg_net,
                "expectancy": expectancy,
            }
    
    return {"symbol": symbol, "tf": tf, "bars": len(df), "results": results}

def main():
    configs = [
        ("XAUUSD", "H1"), ("XAUUSD", "M15"),
        ("EURUSD", "H1"), ("EURUSD", "M15"),
        ("GBPUSD", "H1"), ("GBPUSD", "M15"),
    ]
    
    print("=" * 100)
    print("WALK-FORWARD WITH LAGGED FEATURES (NO DATA LEAKAGE)")
    print("Features: lagged returns, lagged volatility, lagged momentum")
    print("Target: NEXT bar's return direction")
    print("=" * 100)
    
    all_results = []
    for symbol, tf in configs:
        t0 = time.time()
        result = run_walk_forward(symbol, tf)
        elapsed = time.time() - t0
        
        if result is None:
            print("\n%s %s: SKIP (no data)" % (symbol, tf))
            continue
        
        print("\n%s %s (%d bars, %.1fs)" % (symbol, tf, result["bars"], elapsed))
        print("  %6s | %6s | %5s | %5s | %8s | %8s | %8s | %10s" % (
            "Conf", "Trades", "Wins", "Losses", "WinRate", "TotalNet", "AvgNet", "Expectancy"))
        print("  " + "-" * 80)
        
        for ct in [0.0, 0.55, 0.65, 0.75, 0.85]:
            if ct in result["results"]:
                r = result["results"][ct]
                print("  %6.2f | %6d | %5d | %5d | %6.1f%% | %+7.2f | %+7.2f | %+8.4f" % (
                    ct, r["trades"], r["wins"], r["losses"],
                    r["win_rate"] * 100, r["total_net"], r["avg_net_per_fold"], r["expectancy"]))
        
        all_results.append(result)
    
    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print("%-10s %-4s %6s %6s %6s %7s %8s" % ("Symbol", "TF", "Trades", "Wins", "Losses", "WinRate", "Net"))
    print("-" * 70)
    for r in all_results:
        # Find best threshold
        best_ct = 0
        best_net = -999999
        for ct, data in r["results"].items():
            if data["total_net"] > best_net and data["trades"] >= 10:
                best_net = data["total_net"]
                best_ct = ct
        if best_ct in r["results"]:
            d = r["results"][best_ct]
            print("%-10s %-4s %6d %6d %6d %6.1f%% %+7.2f" % (
                r["symbol"], r["tf"], d["trades"], d["wins"], d["losses"],
                d["win_rate"] * 100, d["total_net"]))

if __name__ == "__main__":
    main()
