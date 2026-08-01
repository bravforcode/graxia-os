"""Cointegration existence test — XAUUSD/GDX (Direction E, Trial #5002).

Pre-registered in research/hypothesis_registry_e.json BEFORE this script ran.
Engle-Granger two-step test on log prices, full overlapping history.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.stattools import adfuller, coint

ROOT = Path(__file__).resolve().parent.parent


def load_xauusd() -> pd.Series:
    df = pd.read_csv(ROOT / "data" / "XAUUSD_D1.csv")
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").set_index("time")
    return df["close"].rename("XAUUSD")


def load_gdx() -> pd.Series:
    df = pd.read_csv(ROOT / "data" / "GDX_D1_yfinance.csv", skiprows=[1, 2])
    df.columns = ["time", "close", "high", "low", "open", "volume"]
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").set_index("time")
    return df["close"].rename("GDX")


def main() -> int:
    xau = load_xauusd()
    gdx = load_gdx()

    combined = pd.concat([xau, gdx], axis=1).dropna()
    print(f"Overlapping history: {combined.index.min()} to {combined.index.max()} ({len(combined)} days)")

    log_xau = np.log(combined["XAUUSD"])
    log_gdx = np.log(combined["GDX"])

    X = add_constant(log_gdx)
    model = OLS(log_xau, X).fit()
    hedge_ratio = model.params["GDX"]
    intercept = model.params["const"]
    spread = log_xau - hedge_ratio * log_gdx - intercept

    adf_stat, adf_p, _, _, adf_crit, _ = adfuller(spread, autolag="AIC")
    coint_stat, coint_p, coint_crit = coint(log_xau, log_gdx)

    print(f"\nHedge ratio (XAUUSD ~ GDX): {hedge_ratio:.4f}, intercept: {intercept:.4f}")
    print(f"\nEngle-Granger (manual, ADF on residual spread):")
    print(f"  ADF stat: {adf_stat:.4f}, p-value: {adf_p:.4f}")
    print(f"\nstatsmodels.tsa.stattools.coint() (frozen, pre-registered test):")
    print(f"  coint stat: {coint_stat:.4f}, p-value: {coint_p:.4f}")
    print(f"  Critical values (1%,5%,10%): {coint_crit}")

    verdict = "COINTEGRATED" if coint_p < 0.05 else "NOT_COINTEGRATED"
    print(f"\nVERDICT (threshold p<0.05, per pre-registration): {verdict}")

    payload = {
        "trial_number": 5002,
        "generated_at": datetime.now(UTC).isoformat(),
        "test": "engle_granger_cointegration",
        "pair": ["XAUUSD", "GDX"],
        "n_days": len(combined),
        "date_range": [str(combined.index.min()), str(combined.index.max())],
        "hedge_ratio": round(float(hedge_ratio), 6),
        "intercept": round(float(intercept), 6),
        "manual_adf_pvalue": round(float(adf_p), 6),
        "statsmodels_coint_pvalue": round(float(coint_p), 6),
        "critical_values_1_5_10_pct": [round(float(c), 4) for c in coint_crit],
        "verdict": verdict,
        "verdict_threshold": "p < 0.05",
    }

    out_path = ROOT / "reports" / "cointegration_gold_gdx_20260728.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
