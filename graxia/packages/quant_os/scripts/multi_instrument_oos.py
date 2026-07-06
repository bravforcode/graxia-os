"""
Proper OOS test on multiple instruments + larger windows.
Caveman mode: no filler, just results.
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

def run_oos(symbol, freq, train_pct=0.6, window_name="standard"):
    path = FEAT_DIR / f"features_{symbol}_{freq}.parquet"
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

    # Logistic
    lr_model = LogisticRegression(max_iter=1000, random_state=42)
    lr_model.fit(X_train_s, y_train)
    lr_train = lr_model.score(X_train_s, y_train)
    lr_test = lr_model.score(X_test_s, y_test)

    # PnL (XGBoost)
    spread_cost = 0.000375
    slippage_p90 = 0.000250
    cost = (spread_cost + slippage_p90) * np.mean(c_test)
    preds = xgb_model.predict(X_test_s)
    conf = np.max(xgb_model.predict_proba(X_test_s), axis=1)
    mask = conf >= 0.55
    direction = 2 * preds.astype(float) - 1
    net = (direction[mask] * r_test[mask] * c_test[mask]).sum() - cost * mask.sum()
    n_trades = mask.sum()

    # Majority baseline
    majority = 1 if y_train.mean() > 0.5 else 0
    maj_dir = 2 * float(majority) - 1
    maj_net = (maj_dir * r_test * c_test).sum() - cost * len(y_test)

    return {
        "symbol": symbol, "freq": freq, "window": window_name,
        "train_rows": len(X_train), "test_rows": len(X_test),
        "xgb_train_acc": round(xgb_train, 4), "xgb_test_acc": round(xgb_test, 4),
        "lr_train_acc": round(lr_train, 4), "lr_test_acc": round(lr_test, 4),
        "xgb_overfit_gap": round(xgb_train - xgb_test, 4),
        "n_trades": int(n_trades), "xgb_net": round(float(net), 2),
        "maj_net": round(float(maj_net), 2),
        "xgb_beats_random": bool(net > maj_net),
    }


def main():
    t0 = time.time()
    instruments = ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "BTCUSD", "ETHUSD", "USDCAD"]
    results = []

    # Test 1: M1 data (100K bars)
    print("=" * 70)
    print("TEST 1: M1 DATA (100K bars, 60/40 split)")
    print("=" * 70)
    for sym in instruments:
        r = run_oos(sym, "M1", train_pct=0.6, window_name="M1_60/40")
        if r:
            results.append(r)
            tag = "OK" if r["xgb_beats_random"] else "FAIL"
            print("  " + tag + " " + sym + ": XGB_test=" + str(round(r["xgb_test_acc"], 3)) + " gap=" + str(round(r["xgb_overfit_gap"], 3)) + " net=$" + str(round(r["xgb_net"])) + " trades=" + str(r["n_trades"]))

    # Test 2: M1 larger window (80/20)
    print("\n" + "=" * 70)
    print("TEST 2: M1 LARGER WINDOW (80/20)")
    print("=" * 70)
    for sym in instruments:
        r = run_oos(sym, "M1", train_pct=0.8, window_name="M1_80/20")
        if r:
            results.append(r)
            tag = "OK" if r["xgb_beats_random"] else "FAIL"
            print("  " + tag + " " + sym + ": XGB_test=" + str(round(r["xgb_test_acc"], 3)) + " gap=" + str(round(r["xgb_overfit_gap"], 3)) + " net=$" + str(round(r["xgb_net"])) + " trades=" + str(r["n_trades"]))

    # Test 3: H1 for comparison
    print("\n" + "=" * 70)
    print("TEST 3: H1 COMPARISON (60/40)")
    print("=" * 70)
    for sym in instruments:
        r = run_oos(sym, "H1", train_pct=0.6, window_name="H1_60/40")
        if r:
            results.append(r)
            tag = "OK" if r["xgb_beats_random"] else "FAIL"
            print("  " + tag + " " + sym + ": XGB_test=" + str(round(r["xgb_test_acc"], 3)) + " gap=" + str(round(r["xgb_overfit_gap"], 3)) + " net=$" + str(round(r["xgb_net"])) + " trades=" + str(r["n_trades"]))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY — Instruments where XGB beats majority baseline")
    print("=" * 70)
    winners = [r for r in results if r["xgb_beats_random"]]
    losers = [r for r in results if not r["xgb_beats_random"]]
    print(f"  Winners: {len(winners)}/{len(results)}")
    for r in winners:
        print(f"    {r['symbol']:8s} {r['freq']} {r['window']:6s}: net=${r['xgb_net']:+8.0f} test_acc={r['xgb_test_acc']:.3f}")
    print(f"  Losers: {len(losers)}")

    # Save
    out_path = OUT_DIR / "multi_instrument_oos.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved: {out_path}")
    print(f"  Time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
