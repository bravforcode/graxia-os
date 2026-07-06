"""
Final Validation — DSR + Shuffle + NAS100/US30 test
Fast version with logistic regression for null distribution.
"""
import os, sys, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent.parent
FEAT_DIR = BASE / "artifacts" / "features_v2"
WF_DIR = BASE / "artifacts" / "walk_forward"

# Import DSR
import importlib.util
spec = importlib.util.spec_from_file_location("ds", str(BASE / "validation" / "deflated_sharpe.py"))
ds_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds_mod)

def run_oos(symbol, freq, train_pct=0.6):
    path = FEAT_DIR / ("features_" + symbol + "_" + freq + ".parquet")
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    exclude = {"target", "target_return", "symbol", "freq", "target_3class"}
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    X = df[feature_cols].fillna(0).values
    y = df["target"].values
    returns = df["target_return"].values
    closes = df["close"].values
    X, y, returns, closes = X[:-5], y[:-5], returns[:-5], closes[:-5]
    
    split = int(len(X) * train_pct)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    r_test = returns[split:]
    c_test = closes[split:]
    
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_train_s, y_train)
    test_acc = model.score(X_test_s, y_test)
    
    # PnL
    avg_price = np.mean(c_test)
    if avg_price > 1000:
        cost_per_trade = 0.02  # 1.5 points spread + 0.5 points slippage
    else:
        cost_per_trade = 0.000015
    
    preds = model.predict(X_test_s)
    conf = np.max(model.predict_proba(X_test_s), axis=1)
    mask = conf >= 0.55
    direction = 2 * preds.astype(float) - 1
    net = (direction[mask] * r_test[mask] * c_test[mask]).sum() - cost_per_trade * mask.sum()
    
    majority = 1 if y_train.mean() > 0.5 else 0
    maj_dir = 2 * float(majority) - 1
    maj_net = (maj_dir * r_test * c_test).sum() - cost_per_trade * len(y_test)
    
    return {
        "symbol": symbol, "freq": freq,
        "test_acc": round(test_acc, 4),
        "n_trades": int(mask.sum()),
        "net": round(float(net), 2),
        "maj_net": round(float(maj_net), 2),
        "beats_random": bool(net > maj_net),
    }

def main():
    t0 = time.time()
    
    # 1. DSR on walk-forward results
    print("=" * 60)
    print("DSR/PBO ANALYSIS — XAUUSD M1")
    print("=" * 60)
    wf_path = WF_DIR / "wf_XAUUSD_M1_50000w_10000t_conf0.55.json"
    if wf_path.exists():
        with open(wf_path) as f:
            wf = json.load(f)
        fold_sharpes = [fold["sharpe_ratio"] for fold in wf["folds"]]
        observed_sharpe = np.mean(fold_sharpes)
        n_obs = sum(fold["n_trades"] for fold in wf["folds"])
    else:
        observed_sharpe = 0.0
        n_obs = 40000
    
    dsr = ds_mod.deflated_sharpe_ratio(observed_sharpe, 100, n_obs)
    min_btl = ds_mod.min_backtest_length(observed_sharpe, 100, current_observations=n_obs)
    
    print("  Observed Sharpe: " + str(round(observed_sharpe, 2)))
    print("  Prob alpha: " + str(round(dsr.probability_alpha, 4)))
    print("  Passes: " + str(dsr.passes_threshold))
    print("  Min observations: " + str(min_btl.min_observations))
    print("  Current observations: " + str(n_obs))
    print("  Sufficient: " + str(min_btl.sufficient))
    
    # 2. Label shuffling (1000 perms)
    print("\n" + "=" * 60)
    print("LABEL SHUFFLING — XAUUSD M1 (1000 perms)")
    print("=" * 60)
    
    path = FEAT_DIR / "features_XAUUSD_M1.parquet"
    df = pd.read_parquet(path)
    exclude = {"target", "target_return", "symbol", "freq", "target_3class"}
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    X = df[feature_cols].fillna(0).values
    y = df["target"].values
    returns = df["target_return"].values
    closes = df["close"].values
    X, y, returns, closes = X[:-5], y[:-5], returns[:-5], closes[:-5]
    
    split = int(len(X) * 0.6)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    r_test = returns[split:]
    c_test = closes[split:]
    
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    real_model = LogisticRegression(max_iter=1000, random_state=42)
    real_model.fit(X_train_s, y_train)
    real_preds = real_model.predict(X_test_s)
    real_conf = np.max(real_model.predict_proba(X_test_s), axis=1)
    mask = real_conf >= 0.55
    direction = 2 * real_preds.astype(float) - 1
    real_net = (direction[mask] * r_test[mask] * c_test[mask]).sum() - 0.02 * mask.sum()
    
    print("  Real net: $" + str(round(real_net, 2)))
    
    np.random.seed(42)
    null_nets = np.zeros(1000)
    for i in range(1000):
        shuffled_y = np.random.permutation(y_train)
        null_model = LogisticRegression(max_iter=500, random_state=42)
        null_model.fit(X_train_s, shuffled_y)
        null_preds = null_model.predict(X_test_s)
        null_conf = np.max(null_model.predict_proba(X_test_s), axis=1)
        null_mask = null_conf >= 0.55
        null_dir = 2 * null_preds.astype(float) - 1
        null_nets[i] = (null_dir[null_mask] * r_test[null_mask] * c_test[null_mask]).sum() - 0.02 * null_mask.sum()
        if (i + 1) % 200 == 0:
            print("  Permutation " + str(i+1) + "/1000...")
    
    p_value = (null_nets >= real_net).mean()
    print("  p-value: " + str(round(p_value, 4)))
    
    # 3. NAS100/US30 OOS
    print("\n" + "=" * 60)
    print("OOS TEST — NAS100/US30 M1")
    print("=" * 60)
    
    for sym in ["NAS100", "US30"]:
        r = run_oos(sym, "M1", train_pct=0.6)
        if r:
            tag = "WIN" if r["beats_random"] else "LOSE"
            print("  " + tag + " " + sym + ": test=" + str(r["test_acc"]) + " net=$" + str(r["net"]) + " trades=" + str(r["n_trades"]))
    
    # Summary
    print("\n" + "=" * 60)
    print("FINAL VERDICT")
    print("=" * 60)
    print("  DSR passes: " + str(dsr.passes_threshold))
    print("  Shuffle p-value: " + str(round(p_value, 4)))
    if dsr.passes_threshold and p_value < 0.05:
        print("  >>> EDGE CONFIRMED <<<")
    elif p_value < 0.10:
        print("  >>> EDGE MARGINAL <<<")
    else:
        print("  >>> NO CONFIRMED EDGE <<<")
    print("  Time: " + str(round(time.time() - t0)) + "s")

if __name__ == "__main__":
    main()
