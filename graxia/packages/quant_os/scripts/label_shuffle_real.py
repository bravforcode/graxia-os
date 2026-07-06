"""Label shuffling null test on REAL features (not synthetic).
Permutes forward returns 100x, reruns simple XGBoost, checks if real Sharpe
falls inside null distribution."""

import warnings

warnings.filterwarnings("ignore")
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT_DIR = os.path.join(BASE, "artifacts", "features_v2")
OUT_DIR = os.path.join(BASE, "artifacts", "walk_forward_v4")
os.makedirs(OUT_DIR, exist_ok=True)

N_SHUFFLES = 100
SYMBOL = "XAUUSD"
FREQ = "1H"

# Load real features
path = os.path.join(FEAT_DIR, f"features_v2_{SYMBOL}_{FREQ}.parquet")
df = pd.read_parquet(path)
if "timestamp" in df.columns:
    df = df.set_index("timestamp")
df.index = pd.to_datetime(df.index, utc=True)
if df["target"].dtype in (np.float64, np.float32):
    df["target"] = df["target"].astype(int)

exclude = {
    "target",
    "target_return",
    "target_3class",
    "symbol",
    "freq",
    "tb_label",
    "tb_bar_hit",
    "tb_side",
    "tb_ret",
    "tb_k_upper",
    "tb_k_lower",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "tick_count",
}
feature_cols = [
    c for c in df.columns if c not in exclude and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)
]

X = df[feature_cols].fillna(0).values
y_real = df["target"].values
returns = df["target_return"].values
close = df["close"].values

print(f"Data: {len(df)} rows, {len(feature_cols)} features")
print(f"Target distribution: up={y_real.mean():.3f}, down={1-y_real.mean():.3f}")

# --- Real model (no shuffle) ---
n = len(X)
train_end = int(n * 0.7)
X_train, X_test = X[:train_end], X[train_end:]
y_train, y_test = y_real[:train_end], y_real[train_end:]
ret_test = returns[train_end:]
close_test = close[train_end:]

model = xgb.XGBClassifier(
    n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42, eval_metric="logloss", verbosity=0
)
model.fit(X_train, y_train)
preds = model.predict(X_test)
proba = model.predict_proba(X_test)
conf = np.max(proba, axis=1)

# Trade selection: conf >= 0.55 (lower threshold since accuracy is ~50%)
mask = conf >= 0.55
direction = 2 * preds.astype(float) - 1
dir_mask = direction[mask]
rets_masked = ret_test[mask]
closes_masked = close_test[mask]

# Dollar PnL per trade
pnl = dir_mask * rets_masked * closes_masked
cost_per = 0.00012 * np.mean(closes_masked)  # ~1.2 bps round-trip
net_pnl = pnl - cost_per

real_accuracy = (dir_mask * rets_masked > 0).mean()
real_net = net_pnl.sum()
real_sharpe = net_pnl.mean() / net_pnl.std() * np.sqrt(252 * 24) if net_pnl.std() > 1e-10 else 0.0

print("\n=== REAL MODEL (no shuffle) ===")
print(f"OOS accuracy: {real_accuracy*100:.1f}%")
print(f"Trades: {mask.sum()}")
print(f"Net PnL: ${real_net:,.2f}")
print(f"Annualized Sharpe: {real_sharpe:.3f}")

# --- Null distribution via label shuffling ---
null_sharpes = []
null_accs = []
null_nets = []

for i in range(N_SHUFFLES):
    # Shuffle target (break label-feature alignment)
    y_shuffled = np.random.permutation(y_real)
    y_train_s = y_shuffled[:train_end]
    y_test_s = y_shuffled[train_end:]

    m = xgb.XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42 + i, eval_metric="logloss", verbosity=0
    )
    m.fit(X_train, y_train_s)
    p = m.predict(X_test)
    pr = m.predict_proba(X_test)
    c = np.max(pr, axis=1)

    mask_s = c >= 0.55
    d = 2 * p.astype(float) - 1
    dm = d[mask_s]
    rm = ret_test[mask_s]
    cm = close_test[mask_s]

    pnl_s = dm * rm * cm
    net_s = pnl_s - cost_per * mask_s.sum()

    acc_s = (dm * rm > 0).mean() if mask_s.sum() > 0 else 0.5
    sr_s = net_s.mean() / net_s.std() * np.sqrt(252 * 24) if mask_s.sum() > 1 and net_s.std() > 1e-10 else 0.0

    null_sharpes.append(sr_s)
    null_accs.append(acc_s)
    null_nets.append(float(net_s.sum()))

    if (i + 1) % 20 == 0:
        print(f"  Shuffle {i+1}/{N_SHUFFLES}: acc={acc_s*100:.1f}%, net=${net_s.sum():,.2f}, sr={sr_s:.3f}")

null_sharpes = np.array(null_sharpes)
null_accs = np.array(null_accs)
null_nets = np.array(null_nets)

# P-value: fraction of null >= real
p_sharpe = (null_sharpes >= real_sharpe).mean()
p_acc = (null_accs >= real_accuracy).mean()
p_net = (null_nets >= real_net).mean()

print("\n=== NULL DISTRIBUTION (100 shuffles) ===")
print(f"Null accuracy:  mean={null_accs.mean()*100:.1f}%, std={null_accs.std()*100:.1f}%")
print(f"Null net PnL:   mean=${null_nets.mean():,.2f}, std=${null_nets.std():,.2f}")
print(f"Null Sharpe:    mean={null_sharpes.mean():.3f}, std={null_sharpes.std():.3f}")

print("\n=== P-VALUES ===")
print(f"P(Sharpe >= real): {p_sharpe:.3f} {'*** NOT SIGNIFICANT' if p_sharpe > 0.05 else '*** SIGNIFICANT'}")
print(f"P(Accuracy >= real): {p_acc:.3f} {'*** NOT SIGNIFICANT' if p_acc > 0.05 else '*** SIGNIFICANT'}")
print(f"P(NetPnL >= real): {p_net:.3f} {'*** NOT SIGNIFICANT' if p_net > 0.05 else '*** SIGNIFICANT'}")

print("\n=== VERDICT ===")
if p_sharpe > 0.05:
    print("REJECT: Real model edge is indistinguishable from random. NO TRADEABLE EDGE.")
elif p_sharpe < 0.01:
    print("ACCEPT: Real model has statistically significant edge (p < 0.01).")
else:
    print("MARGINAL: Real model edge is weakly significant (0.01 < p < 0.05). Need more data.")

result = {
    "real": {"accuracy": real_accuracy, "net_pnl": real_net, "sharpe": real_sharpe, "n_trades": int(mask.sum())},
    "null": {
        "accuracy_mean": null_accs.mean(),
        "accuracy_std": null_accs.std(),
        "net_mean": null_nets.mean(),
        "net_std": null_nets.std(),
        "sharpe_mean": null_sharpes.mean(),
        "sharpe_std": null_sharpes.std(),
    },
    "p_values": {"sharpe": p_sharpe, "accuracy": p_acc, "net_pnl": p_net},
    "n_shuffles": N_SHUFFLES,
    "symbol": SYMBOL,
    "freq": FREQ,
}
with open(os.path.join(OUT_DIR, f"label_shuffle_{SYMBOL}_{FREQ}.json"), "w") as f:
    json.dump(result, f, indent=2)
print(f"\nSaved: {OUT_DIR}/label_shuffle_{SYMBOL}_{FREQ}.json")
