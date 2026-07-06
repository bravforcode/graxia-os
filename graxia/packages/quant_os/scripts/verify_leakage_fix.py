"""Verify target_3class leakage fix."""

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit

df = pd.read_parquet("artifacts/features_v2/features_v2_XAUUSD_1H.parquet")
if "timestamp" in df.columns:
    df = df.set_index("timestamp")
df.index = pd.to_datetime(df.index, utc=True)
if "target" in df.columns and df["target"].dtype in (np.float64, np.float32):
    df["target"] = df["target"].astype(int)

exclude_base = {
    "target",
    "target_return",
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
feature_cols_old = [
    c for c in df.columns if c not in exclude_base and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)
]

exclude_new = exclude_base | {"target_3class"}
feature_cols_new = [
    c for c in df.columns if c not in exclude_new and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)
]

print(f"Old feature count: {len(feature_cols_old)}")
print(f"New feature count: {len(feature_cols_new)}")
has_leak_old = "target_3class" in feature_cols_old
has_leak_new = "target_3class" in feature_cols_new
print(f"target_3class in old features: {has_leak_old}")
print(f"target_3class in new features: {has_leak_new}")

X_old = df[feature_cols_old].values
X_new = df[feature_cols_new].values
y = df["target"].values

tscv = TimeSeriesSplit(n_splits=5)
acc_old, acc_new = [], []
for train_idx, test_idx in tscv.split(X_old):
    m_old = xgb.XGBClassifier(n_estimators=50, max_depth=4, random_state=42, eval_metric="logloss")
    m_old.fit(X_old[train_idx], y[train_idx])
    acc_old.append(accuracy_score(y[test_idx], m_old.predict(X_old[test_idx])))

    m_new = xgb.XGBClassifier(n_estimators=50, max_depth=4, random_state=42, eval_metric="logloss")
    m_new.fit(X_new[train_idx], y[train_idx])
    acc_new.append(accuracy_score(y[test_idx], m_new.predict(X_new[test_idx])))

print(f"\nWith leakage (target_3class): OOS accuracy = {np.mean(acc_old)*100:.1f}%")
print(f"Without leakage (fixed):       OOS accuracy = {np.mean(acc_new)*100:.1f}%")
print("Realistic baseline expected:    ~50-55%")
