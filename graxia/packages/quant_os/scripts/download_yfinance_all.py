"""Download ALL yfinance data for XAUUSD gold trading analysis."""

from pathlib import Path

import yfinance as yf
import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "market_data" / "yfinance"
START_DATE = "2016-01-01"
END_DATE = "2026-06-26"

TICKERS = [
    # Primary
    "GC=F", "GLD", "IAU", "SI=F", "SLV", "CL=F", "BZ=F", "NG=F",
    "DX-Y.NYB", "^VIX", "^TNX", "^FVX", "^TYX", "TLT", "IEF", "SHY",
    "^GSPC", "^DJI", "^IXIC", "^RUT",
    "EURUSD=X", "GBPUSD=X", "USDJPY=X",
    "BTC-USD", "ETH-USD",
    "DBA", "UUP", "UDN",
]


def download_ticker(ticker: str) -> dict:
    safe_name = ticker.replace("=", "_").replace("^", "_").replace("/", "_")
    csv_path = OUTPUT_DIR / f"{safe_name}.csv"

    try:
        df = yf.download(ticker, start=START_DATE, end=END_DATE, auto_adjust=True, progress=False)
        if df.empty:
            return {"ticker": ticker, "rows": 0, "start": None, "end": None, "missing_pct": 100.0, "error": "empty"}

        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.to_csv(csv_path)

        total_trading_days = len(df)
        nulls = df[["Open", "High", "Low", "Close", "Volume"]].isnull().any(axis=1).sum()
        missing_pct = round(100 * nulls / total_trading_days, 2) if total_trading_days else 100.0

        return {
            "ticker": ticker,
            "rows": total_trading_days,
            "start": str(df.index.min().date()),
            "end": str(df.index.max().date()),
            "missing_pct": missing_pct,
            "error": None,
        }
    except Exception as e:
        return {"ticker": ticker, "rows": 0, "start": None, "end": None, "missing_pct": 100.0, "error": str(e)}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(TICKERS)} tickers ({START_DATE} to {END_DATE})...")
    print(f"Output: {OUTPUT_DIR}\n")

    results = []
    for i, ticker in enumerate(TICKERS, 1):
        print(f"[{i:2d}/{len(TICKERS)}] {ticker:12s} ... ", end="", flush=True)
        r = download_ticker(ticker)
        results.append(r)
        if r["error"]:
            print(f"ERROR: {r['error']}")
        else:
            print(f"{r['rows']:>5d} rows  ({r['start']} to {r['end']})  missing={r['missing_pct']:.1f}%")

    # Summary CSV
    summary_path = OUTPUT_DIR / "_summary.csv"
    df_summary = pd.DataFrame(results)
    df_summary.to_csv(summary_path, index=False)

    print(f"\nDone. Summary: {summary_path}")
    print(f"Files saved: {len([r for r in results if not r['error']])}/{len(TICKERS)}")


if __name__ == "__main__":
    main()
