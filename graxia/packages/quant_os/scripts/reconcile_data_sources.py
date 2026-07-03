"""Cross-source reconciliation: Dukascopy vs Pepperstone MT5."""
import argparse
import sys
from pathlib import Path

import pandas as pd

_QUANT_OS = Path(__file__).resolve().parent.parent
if str(_QUANT_OS.parent) not in sys.path:
    sys.path.insert(0, str(_QUANT_OS.parent))


def fetch_pepperstone_m15(symbol: str, start, end) -> pd.DataFrame:
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise ConnectionError(f"MT5 initialize failed: {mt5.last_error()}")

    start_dt = pd.Timestamp(start).to_pydatetime()
    end_dt = pd.Timestamp(end).to_pydatetime()

    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_dt, end_dt)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise ValueError(f"No M15 data returned for {symbol} [{start} → {end}]")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("time")[["open", "high", "low", "close"]]


def reconcile(dukascopy_df: pd.DataFrame, pepperstone_df: pd.DataFrame) -> dict:
    aligned = dukascopy_df.join(pepperstone_df, how="inner", lsuffix="_duka", rsuffix="_pep")
    close_diff = (aligned["close_duka"] - aligned["close_pep"]).abs()
    pct_diff = close_diff / aligned["close_pep"]

    report = {
        "n_bars_compared": len(aligned),
        "mean_abs_diff_usd": close_diff.mean(),
        "max_abs_diff_usd": close_diff.max(),
        "pct_bars_diff_gt_0.5usd": (close_diff > 0.5).mean(),
        "pct_bars_diff_gt_1pct": (pct_diff > 0.01).mean(),
    }

    print("\n=== CROSS-SOURCE RECONCILIATION (Dukascopy vs Pepperstone MT5) ===")
    for k, v in report.items():
        if isinstance(v, float):
            print(f"  {k:<28} {v:>12.6f}")
        else:
            print(f"  {k:<28} {v:>12}")

    if report["pct_bars_diff_gt_0.5usd"] > 0.02:
        print(
            "\u26a0\ufe0f  >2% of bars differ by >$0.50 between sources "
            "- investigate before trusting backtest EV on live data."
        )
    return report


def main():
    parser = argparse.ArgumentParser(description="Cross-source reconciliation Dukascopy vs Pepperstone")
    parser.add_argument("--dukascopy", required=True, help="Path to Dukascopy M15 parquet file")
    parser.add_argument("--symbol", default="XAUUSD", help="MT5 symbol (default: XAUUSD)")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2024-12-31", help="End date YYYY-MM-DD")
    args = parser.parse_args()

    duka_path = Path(args.dukascopy)
    if not duka_path.exists():
        print(f"Error: Dukascopy file not found: {duka_path}")
        sys.exit(1)

    duka_df = pd.read_parquet(duka_path)
    duka_df.index = pd.to_datetime(duka_df.index)

    try:
        pep_df = fetch_pepperstone_m15(args.symbol, args.start, args.end)
    except (ConnectionError, ValueError) as e:
        print(f"MT5 fetch failed (non-fatal): {e}")
        sys.exit(1)

    reconcile(duka_df, pep_df)


if __name__ == "__main__":
    main()
