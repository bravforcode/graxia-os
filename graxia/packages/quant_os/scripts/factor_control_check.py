"""Factor-Control correlation checks — verify strategy returns are not driven by common factors.

Uses numpy only (no yfinance/scipy dependency). Loads return CSVs and computes
correlation of strategy returns against factor proxies (DXY, VIX, yields, etc.).

Rule: R² > 0.30 = edge likely comes from factor exposure, not alpha.
Minimum: DXY + VIX must pass before paper trading.

Usage:
    python scripts/factor_control_check.py --strategy-returns returns.csv --factor-returns returns.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Factor-Control thresholds
R2_WARNING = 0.20
R2_REJECT = 0.30
REQUIRED_FACTORS = ["DXY", "VIX"]


def compute_r_squared(returns_a: np.ndarray, returns_b: np.ndarray) -> float:
    """R² = correlation² between two return series."""
    if len(returns_a) != len(returns_b) or len(returns_a) < 10:
        return 0.0
    mask = np.isfinite(returns_a) & np.isfinite(returns_b)
    a, b = returns_a[mask], returns_b[mask]
    if len(a) < 10 or a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1]) ** 2


def _load_csv(path: str | Path) -> dict[str, np.ndarray]:
    """Load CSV where each column is a return series."""
    path = Path(path)
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        start_col = 1 if header[0].lower() in ("date", "timestamp", "time") else 0
        cols: dict[str, list[float]] = {h.strip(): [] for h in header[start_col:]}
        for row in reader:
            if len(row) <= start_col:
                continue
            for i, name in enumerate(header[start_col:]):
                if i + start_col < len(row):
                    val = row[i + start_col].strip()
                    if val and val not in ("nan", "None"):
                        try:
                            cols[name].append(float(val))
                        except ValueError:
                            pass
    return {k: np.array(v) for k, v in cols.items() if len(v) > 0}


def run_factor_control(
    strategy_returns: dict[str, np.ndarray],
    factor_returns: dict[str, np.ndarray],
    required_factors: list[str] | None = None,
) -> dict[str, Any]:
    """Run factor-control checks on strategy returns against factor proxies."""
    required = required_factors or REQUIRED_FACTORS
    results: dict[str, Any] = {"strategies": {}, "overall_pass": True, "blocking_failures": []}

    for strat_name, strat_arr in strategy_returns.items():
        strat_result: dict[str, Any] = {"factors": {}, "pass": True, "warnings": [], "blocking": []}

        for factor_name, factor_arr in factor_returns.items():
            min_len = min(len(strat_arr), len(factor_arr))
            if min_len < 10:
                continue
            r2 = compute_r_squared(strat_arr[:min_len], factor_arr[:min_len])

            if r2 > R2_REJECT:
                verdict = "REJECT"
                strat_result["pass"] = False
                if factor_name in required:
                    strat_result["blocking"].append(factor_name)
                    results["blocking_failures"].append({"strategy": strat_name, "factor": factor_name, "r2": r2})
            elif r2 > R2_WARNING:
                verdict = "WARNING"
                strat_result["warnings"].append(factor_name)
            else:
                verdict = "PASS"

            strat_result["factors"][factor_name] = {"r2": round(r2, 4), "verdict": verdict}

        results["strategies"][strat_name] = strat_result
        if not strat_result["pass"]:
            results["overall_pass"] = False

    return results


def main():
    parser = argparse.ArgumentParser(description="Factor-Control Correlation Check")
    parser.add_argument("--strategy-returns", required=True)
    parser.add_argument("--factor-returns", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    strategy_data = _load_csv(args.strategy_returns)
    factor_data = _load_csv(args.factor_returns)
    result = run_factor_control(strategy_data, factor_data)

    for name, sr in result["strategies"].items():
        status = "PASS" if sr["pass"] else "FAIL"
        print(f"{name}: {status}")
        for fn, fd in sr["factors"].items():
            print(f"  {fn}: R²={fd['r2']:.4f} — {fd['verdict']}")

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
