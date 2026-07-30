"""
Test script for Regime-Adaptive Multi-Asset Strategy (Trial #1029)
=================================================================

Usage:
    python scripts/test_ram_strategy.py

This script:
1. Loads all 7 D1 data files
2. Runs the regime-adaptive multi-asset strategy
3. Computes performance metrics
4. Validates against gates
5. Outputs results to reports/
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import directly to avoid package __init__.py relative imports
import importlib.util  # noqa: E402

from provenance import require_cost_calibrated  # noqa: E402

module_name = "regime_adaptive_multi_asset"
spec = importlib.util.spec_from_file_location(
    module_name,
    str(project_root / "strategies" / "regime_adaptive_multi_asset.py"),
)
assert spec is not None and spec.loader is not None, f"Could not load spec for {module_name}"
ram_module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = ram_module  # Register before exec to avoid dataclass error
spec.loader.exec_module(ram_module)

RAMConfig = ram_module.RAMConfig
compute_ram_signals = ram_module.compute_ram_signals
compute_ram_metrics = ram_module.compute_ram_metrics


def load_data(data_dir: str, universe: tuple[str, ...]) -> pd.DataFrame:
    """Load D1 data for all assets in universe.

    Args:
        data_dir: Path to data directory
        universe: Tuple of asset symbols

    Returns:
        DataFrame of daily close prices, DatetimeIndex
    """
    prices = {}

    for asset in universe:
        file_path = os.path.join(data_dir, f"{asset}_D1.csv")
        if not os.path.exists(file_path):
            print(f"WARNING: {file_path} not found, skipping {asset}")
            continue

        df = pd.read_csv(file_path)

        # Parse time column
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
        elif "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")

        # Use close price
        if "close" in df.columns:
            prices[asset] = df["close"]
        elif "Close" in df.columns:
            prices[asset] = df["Close"]
        else:
            print(f"WARNING: No close column in {file_path}, skipping {asset}")

    if not prices:
        raise ValueError("No data loaded")

    # Combine into DataFrame
    prices_df = pd.DataFrame(prices)

    # Forward-fill then drop remaining NaN
    prices_df = prices_df.ffill().dropna()

    print(f"Loaded {len(prices_df)} rows for {len(prices_df.columns)} assets")
    print(f"Date range: {prices_df.index[0]} to {prices_df.index[-1]}")
    print(f"Assets: {list(prices_df.columns)}")

    return prices_df


def run_backtest(prices: pd.DataFrame, config: Any) -> dict:
    """Run backtest and compute metrics.

    Args:
        prices: DataFrame of daily close prices
        config: RAMConfig

    Returns:
        Dictionary of results
    """
    print("\n--- Running Regime-Adaptive Multi-Asset Strategy ---")
    print(f"Universe: {config.universe}")
    print(f"Vol lookback: {config.vol_lookback_short} (short) / {config.vol_lookback_long} (long)")
    print(f"Vol thresholds: {config.vol_low_threshold} (low) / {config.vol_high_threshold} (high)")

    # Compute signals
    result = compute_ram_signals(prices, config)

    # Print regime summary
    regime_counts = result.regime.value_counts()
    print("\nRegime distribution:")
    for regime, count in regime_counts.items():
        pct = count / len(result.regime) * 100
        print(f"  {regime}: {count} days ({pct:.1f}%)")

    # Compute returns
    returns = prices.pct_change().dropna()

    # Compute metrics
    metrics = compute_ram_metrics(result.portfolio, returns, config)

    print("\n--- Performance Metrics ---")
    print(f"Total return: {metrics['total_return']:.2%}")
    print(f"Annual return: {metrics['annual_return']:.2%}")
    print(f"Annual volatility: {metrics['annual_vol']:.2%}")
    print(f"Sharpe ratio: {metrics['sharpe']:.3f}")
    print(f"Max drawdown: {metrics['max_drawdown']:.2%}")
    print(f"Win rate: {metrics['win_rate']:.2%}")
    print(f"Profit factor: {metrics['profit_factor']:.3f}")
    print(f"Trade count: {metrics['trade_count']}")
    print(f"Observations: {metrics['n_observations']}")

    return {
        "config": {
            "universe": config.universe,
            "vol_lookback_short": config.vol_lookback_short,
            "vol_lookback_long": config.vol_lookback_long,
            "vol_low_threshold": config.vol_low_threshold,
            "vol_high_threshold": config.vol_high_threshold,
            "mom_lookback": config.mom_lookback,
            "mom_entry_z": config.mom_entry_z,
            "mr_lookback": config.mr_lookback,
            "mr_entry_z": config.mr_entry_z,
        },
        "regime_distribution": regime_counts.to_dict(),
        "metrics": metrics,
        "signals_shape": result.signals.shape,
        "portfolio_shape": result.portfolio.shape,
    }


def validate_gates(metrics: dict) -> dict:
    """Validate performance against gates.

    Args:
        metrics: Dictionary of performance metrics

    Returns:
        Dictionary of gate results
    """
    gates = {
        "sharpe_gt_1.0": metrics["sharpe"] > 1.0,
        "max_dd_lt_25pct": metrics["max_drawdown"] > -0.25,
        "win_rate_gt_50pct": metrics["win_rate"] > 0.50,
        "profit_factor_gt_1.1": metrics["profit_factor"] > 1.1,
        "trade_count_gt_100": metrics["trade_count"] > 100,
    }

    passed = sum(gates.values())
    total = len(gates)

    print("\n--- Gate Validation ---")
    for gate, result in gates.items():
        status = "PASS" if result else "FAIL"
        print(f"  {gate}: {status}")

    print(f"\nGates passed: {passed}/{total}")

    return gates


def main():
    """Main entry point."""
    # Configuration
    data_dir = project_root / "data"
    reports_dir = project_root / "reports"
    reports_dir.mkdir(exist_ok=True)

    # Load data
    config = RAMConfig()

    # 2026-07-30: compute_ram_metrics has zero cost/spread/slippage handling
    # (same root gap as validate_ram_strategy.py / trial #1030). Gate on real
    # per-asset cost calibration so this file cannot silently produce a
    # cost-free verdict against an uncalibrated symbol.
    for asset in config.universe:
        require_cost_calibrated(asset)

    prices = load_data(str(data_dir), config.universe)

    # Run backtest
    results = run_backtest(prices, config)

    # Validate gates
    gates = validate_gates(results["metrics"])
    results["gates"] = gates
    results["gates_passed"] = sum(gates.values())
    results["gates_total"] = len(gates)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = reports_dir / f"ram_trial_1029_{timestamp}.json"

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_file}")

    # Also save to standard location
    standard_file = reports_dir / "ram_trial_1029.json"
    with open(standard_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"Results saved to: {standard_file}")

    return results


if __name__ == "__main__":
    main()
