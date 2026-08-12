#!/usr/bin/env python3
"""Simple XAUUSD H1 analysis with buy-and-hold baseline."""
import pandas as pd
import numpy as np
import xgboost as xgb
import time

print("Loading XAUUSD H1...")
df = pd.read_csv("data/XAUUSD_H1.csv")
df["time"] = pd.to_datetime(df["time"], utc=True)
df = df.set_index("time")
close = df["close"].values.astype(float)
print("Loaded %d bars, %s to %s" % (len(df), df.index[0], df.index[-1]))

returns = np.diff(close) / close[:-1]
returns = np.concatenate([[0], returns])
bh = close[-1] - close[0]
print("Buy-and-Hold: %+.2f" % bh)

# Features
r5 = pd.Series(returns).rolling(5).mean().values
r10 = pd.Series(returns).rolling(10).mean().values
v10 = pd.Series(returns).rolling(10).std().values
v20 = pd.Series(returns).rolling(20).std().values
vr = v10 / (v20 + 1e-10)

X = np.column_stack([returns, r5, r10, v10, v20, vr])
valid = ~np.isnan(X).any(axis=1)
X = X[valid].astype(np.float32)
y = ((X[:, 0] > 0)).astype(int)
idx = np.where(valid)[0]
cp = close[1:][idx[1:] - 1]

min_len = min(len(X), len(cp))
X, y, cp = X[:min_len], y[:min_len], cp[:min_len]
ret = returns[1:][idx[:min_len] - 1]

split = int(min_len * 0.7)
print("Train: %d, Test: %d" % (split, min_len - split))

spread = 0.00005
slip = 0.000027

print()
print("Conf  Trades     Gross      Cost       Net    Sharpe  Edge vs BH")
print("-" * 70)

for ct in [0.0, 0.55, 0.65, 0.75, 0.85]:
    t0 = time.time()
    m = xgb.XGBClassifier(n_estimators=50, max_depth=3, verbosity=0, random_state=42)
    m.fit(X[:split], y[:split])
    proba = m.predict_proba(X[split:])
    conf = np.max(proba, axis=1)
    preds = m.predict(X[split:])
    
    correct = preds == y[split:]
    trade_mask = conf >= ct
    n_trades = trade_mask.sum()
    
    if n_trades < 10:
        print("%5.2f   -- not enough trades --" % ct)
        continue
    
    trade_ret = ret[split:][trade_mask]
    trade_correct = correct[trade_mask]
    pnls = np.where(trade_correct, trade_ret, -trade_ret * 0.5)
    
    avg_price = cp[split:split+len(pnls)].mean()
    # 0.01 lot = 1 oz, cost = return_units * price
    gross = pnls.sum() * avg_price
    cost_per = (spread + slip) * avg_price
    total_cost = cost_per * n_trades
    net = gross - total_cost
    
    if pnls.std() > 0:
        sharpe = pnls.mean() / pnls.std() * np.sqrt(min(n_trades, 252))
    else:
        sharpe = 0
    
    edge = net - bh
    elapsed = time.time() - t0
    print("%5.2f %6d %+10.2f %+9.2f %+9.2f %+7.1f %+10.2f  (%.1fs)" % (
        ct, n_trades, gross, total_cost, net, sharpe, edge, elapsed))

print()
print("Conclusion:")
print("  BH return = %+.2f (from $%.2f to $%.2f)" % (bh, close[-n], close[-1]))
print("  Any positive Net after costs = edge over BH")
print("  Any negative Net = no edge, BH wins")
