"""
M1 OOS Test — Proper out-of-sample on MT5 M1 data.
"""
import os, sys, json, time, warnings
import numpy as np
import pandas as pd
import xgboost as xgb
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent.parent
FEAT_DIR = BASE / "artifacts" / "features_v2"
OUT_DIR = BASE / "artifacts" / "walk_forward"

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

    # XGBoost
    xgb_model = xgb.XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1,
                                    subsample=0.8, colsample_bytree=0.8, random_state=42,
                                    eval_metric="logloss", verbosity=0)
    xgb_model.fit(X_train_s, y_train)
    xgb_train = (xgb_model.predict(X_train_s) == y_train).mean()
    xgb_test = (xgb_model.predict(X_test_s) == y_test).mean()

    # PnL — Pepperstone Razor M1 costs (in price points, not %)
    # EURUSD spread: 0.1 pips = 0.00001; slippage: 0.05 pips = 0.000005
    # XAUUSD spread: 1.5 points = 0.015; slippage: 0.5 points = 0.005
    avg_price = np.mean(c_test)
    if avg_price > 1000:  # XAUUSD, NAS100, US30
        spread_pts = 0.015
        slippage_pts = 0.005
    else:  # Forex
        spread_pts = 0.00001
        slippage_pts = 0.000005
    cost_per_trade = spread_pts + slippage_pts
    preds = xgb_model.predict(X_test_s)
    conf = np.max(xgb_model.predict_proba(X_test_s), axis=1)
    mask = conf >= 0.55
    direction = 2 * preds.astype(float) - 1
    net = (direction[mask] * r_test[mask] * c_test[mask]).sum() - cost_per_trade * mask.sum()

    # Majority baseline
    majority = 1 if y_train.mean() > 0.5 else 0
    maj_dir = 2 * float(majority) - 1
    maj_net = (maj_dir * r_test * c_test).sum() - cost_per_trade * len(y_test)

    return {
        "symbol": symbol, "freq": freq,
        "train_rows": len(X_train), "test_rows": len(X_test),
        "xgb_train_acc": round(xgb_train, 4),
        "xgb_test_acc": round(xgb_test, 4),
        "xgb_overfit_gap": round(xgb_train - xgb_test, 4),
        "n_trades": int(mask.sum()),
        "xgb_net": round(float(net), 2),
        "maj_net": round(float(maj_net), 2),
        "xgb_beats_random": bool(net > maj_net),
    }


def main():
    t0 = time.time()
    instruments = ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "NAS100", "US30"]
    results = []

    # M1 data (100K bars each)
    print("=" * 70)
    print("M1 DATA — 60/40 SPLIT")
    print("=" * 70)
    for sym in instruments:
        r = run_oos(sym, "M1", train_pct=0.6)
        if r:
            results.append(r)
            tag = "WIN" if r["xgb_beats_random"] else "LOSE"
            print("  " + tag + " " + sym + " M1: test=" + str(round(r["xgb_test_acc"], 3)) + " gap=" + str(round(r["xgb_overfit_gap"], 3)) + " net=$" + str(round(r["xgb_net"])) + " trades=" + str(r["n_trades"]))

    # M1 80/20 split
    print("\n" + "=" * 70)
    print("M1 DATA — 80/20 SPLIT")
    print("=" * 70)
    for sym in instruments:
        r = run_oos(sym, "M1", train_pct=0.8)
        if r:
            results.append(r)
            tag = "WIN" if r["xgb_beats_random"] else "LOSE"
            print("  " + tag + " " + sym + " M1: test=" + str(round(r["xgb_test_acc"], 3)) + " gap=" + str(round(r["xgb_overfit_gap"], 3)) + " net=$" + str(round(r["xgb_net"])) + " trades=" + str(r["n_trades"]))

    # Summary
    winners = [r for r in results if r["xgb_beats_random"]]
    print("\n" + "=" * 70)
    print("SUMMARY: " + str(len(winners)) + "/" + str(len(results)) + " beat majority")
    print("=" * 70)
    for r in winners:
        print("  " + r["symbol"] + " " + r["freq"] + ": test=" + str(r["xgb_test_acc"]) + " net=$" + str(r["xgb_net"]))

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "m1_oos_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nTime: " + str(round(time.time() - t0)) + "s")


if __name__ == "__main__":
    main()
