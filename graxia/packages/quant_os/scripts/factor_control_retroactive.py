"""
Factor-Control Retroactive: R² of XAUUSD returns vs DXY/VIX/SPX
================================================================
Check if XAUUSD strategies have hidden factor exposure.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def load_returns(csv_path: Path) -> pd.Series:
    """Load a CSV, auto-detect date column, return daily % returns."""
    df = pd.read_csv(csv_path)
    # Auto-detect date column
    date_col = None
    for c in ["time", "date", "Date", "TIME", "DATE"]:
        if c in df.columns:
            date_col = c
            break
    if date_col is None:
        # Try first column
        date_col = df.columns[0]

    # Auto-detect close column
    close_col = None
    for c in ["close", "Close", "CLOSE", "price", "Price"]:
        if c in df.columns:
            close_col = c
            break
    if close_col is None:
        close_col = df.columns[1]  # second column usually

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)
    # Use date-only index for alignment; handle duplicates by keeping last
    df["_date"] = df[date_col].dt.date
    df = df.drop_duplicates("_date", keep="last").set_index("_date")
    # Keep only the close column, convert to numeric
    vals = pd.to_numeric(df[close_col], errors="coerce").dropna()
    returns = vals.pct_change().dropna()
    returns.name = csv_path.stem
    return returns


def compute_r2(y: pd.Series, x: pd.Series) -> float:
    """R² of y regressed on x."""
    aligned = pd.concat([y, x], axis=1).dropna()
    if len(aligned) < 30:
        return float("nan")
    y_a, x_a = aligned.iloc[:, 0], aligned.iloc[:, 1]
    corr = y_a.corr(x_a)
    return float(corr ** 2) if not np.isnan(corr) else float("nan")


def main():
    data_dir = ROOT / "data"

    # Load factor data
    factor_files = {
        "DXY": data_dir / "DXY_D1.csv",
        "VIX": data_dir / "market_data" / "yfinance" / "_VIX.csv",
        "SPX": data_dir / "market_data" / "yfinance" / "_GSPC.csv",
    }

    factors = {}
    for name, path in factor_files.items():
        if path.exists():
            try:
                ret = load_returns(path)
                factors[name] = ret
                print(f"  Loaded {name}: {len(ret)} daily returns from {ret.index.min()} to {ret.index.max()}")
            except Exception as e:
                print(f"  SKIP {name}: {e}")
        else:
            print(f"  SKIP {name}: file not found")

    if not factors:
        print("FATAL: no factor data")
        return 1

    # Load XAUUSD
    xauusd_path = data_dir / "XAUUSD_D1.csv"
    xauusd_ret = load_returns(xauusd_path)
    print(f"  Loaded XAUUSD: {len(xauusd_ret)} daily returns from {xauusd_ret.index.min()} to {xauusd_ret.index.max()}")
    print()

    # Compute R²
    print("=" * 60)
    print("  Factor-Control: XAUUSD R² vs Macro Factors")
    print("=" * 60)
    print()

    results = {}
    for factor_name, factor_ret in factors.items():
        r2 = compute_r2(xauusd_ret, factor_ret)
        corr = xauusd_ret.corr(factor_ret)
        aligned = pd.concat([xauusd_ret, factor_ret], axis=1).dropna()
        n = len(aligned)
        r2_val = round(r2, 4) if not np.isnan(r2) else None
        corr_val = round(float(corr), 4) if not np.isnan(corr) else None
        results[factor_name] = {"r2": r2_val, "correlation": corr_val, "n_obs": n}
        flag = " ** HIGH **" if r2_val is not None and r2_val > 0.30 else ""
        print(f"  {factor_name:4s}: R²={r2_val}  corr={corr_val}  n={n}{flag}")

    print()
    high = [k for k, v in results.items() if v["r2"] is not None and v["r2"] > 0.30]
    if high:
        print(f"  WARNING: High factor exposure: {', '.join(high)}")
        print("  All XAUUSD strategies inherit this. Path B cross-asset")
        print("  hypotheses using these factors need de-correlation.")
    else:
        print("  OK: No R² > 0.30. XAUUSD strategies not dominated by single factor.")

    out_path = ROOT / "reports" / "factor_control_retroactive.json"
    with open(out_path, "w") as f:
        json.dump({
            "analysis": "Factor-Control Retroactive",
            "description": "R² of XAUUSD daily returns vs DXY/VIX/SPX",
            "threshold": 0.30,
            "results": results,
            "high_exposure_factors": high,
        }, f, indent=2)
    print(f"\n  Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
