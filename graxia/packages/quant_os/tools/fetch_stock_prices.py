"""
fetch_stock_prices.py — Download stock prices via yfinance for sentiment tickers
Insert into DuckDB market_data so sentiment_backtest.py can find matching pairs.

Usage:
    python tools/fetch_stock_prices.py              # Fetch 30 days
    python tools/fetch_stock_prices.py --days 90    # Fetch 90 days
    python tools/fetch_stock_prices.py --status     # Show current count
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "data_pipeline"))
from storage.duckdb_store import DuckDBStore

# Known non-stock tickers to skip (already in market_data or invalid)
SKIP_TICKERS = {
    "BTC-USD",  # crypto — already via ccxt
    "GC=F",  # gold — already via yfinance
    "CL=F",  # oil — not in market_data but commodity
    "^GSPC",  # S&P 500 index
    "^DJI",  # Dow Jones — already in market_data
    "^IXIC",  # Nasdaq — already in market_data
    "NASDAQ",  # index alias
    "SPX",  # index alias
    "empty",  # LLM artifact
    "",  # empty
}

# Known bad-format tickers (LLM extraction errors)
BAD_FORMAT = {
    "TROW GS",  # two tickers mashed together
    "ACCO Brands (private)",  # company name, not ticker
}

# Exclude list — identified in 2026-07-31 yfinance batch (15 tickers, no price data);
# status checked 2026-08-01 (sentiment-DB headlines + web). All are invalid symbols:
# LLM extraction errors, delisted names, or non-US lines.
SKIP_TICKERS |= {
    # Delisted / acquired (web-confirmed 2026-08-01)
    "NKLA",  # Nikola — delisted Nasdaq Feb/Mar 2025
    "GTHX",  # G1 Therapeutics — acquired by Pharmacosmos 2024
    "NBL",  # Noble Energy — acquired by Chevron 2020 (story was Newell/NWL)
    "COL",  # Rockwell Collins — acquired by UTC 2018 (story was Colgate/CL)
    # Non-US / ambiguous — prefer suffixed symbols
    "MRS.L",  # Marks & Spencer is MKS.L; no such LSE symbol
    "RST",  # Restore plc = RST.L (LSE); US RST (Rosetta Stone) long delisted
    "UMG",  # Universal Music primary = UMG.AS; US listing in progress
}
BAD_FORMAT |= {
    "AGAO",  # AngloGold Ashanti = AU
    "ESSR",  # Essex Property Trust = ESS
    "EXL",  # ExlService = EXLS (Nasdaq)
    "MIKE",  # Jersey Mike's = JMI
    "NAMT",  # Nam Tai Property = NTP
    "OHAI",  # Oppenheimer Holdings = OPY
    "STRY",  # Strategy (Saylor) = MSTR
    "RBC Bearings",  # company name; ticker = RBC (NYSE)
    "RBC Bearings (private)",  # exact DB form
}


def get_sentiment_tickers(duck: DuckDBStore) -> list[str]:
    """Extract unique stock tickers from llm_news_sentiment."""
    r = duck.conn.execute("""
        SELECT DISTINCT TRIM(t.value) as ticker
        FROM llm_news_sentiment,
        LATERAL UNNEST(string_split(tickers, ',')) AS t(value)
        WHERE tickers IS NOT NULL AND tickers != ''
        ORDER BY ticker
    """).fetchall()

    tickers = [t[0].strip() for t in r if t[0].strip()]

    # Filter out non-stock and bad-format tickers
    valid = [t for t in tickers if t not in SKIP_TICKERS and t not in BAD_FORMAT]

    print(f"Total unique tickers: {len(tickers)}")
    print(f"Valid stock tickers: {len(valid)}")
    print(f"Skipped: {len(tickers) - len(valid)} ({', '.join(sorted(set(tickers) - set(valid)))})")

    return valid


def fetch_stock_prices(tickers: list[str], days: int = 30) -> pd.DataFrame:
    """Download OHLCV via yfinance batch download."""
    print(f"\nDownloading {len(tickers)} tickers ({days}d)...")

    # yfinance batch download
    data = yf.download(tickers, period=f"{days}d", group_by="ticker", progress=False, threads=True)

    if data.empty:
        print("ERROR: No data returned")
        return pd.DataFrame()

    rows = []
    successful = []
    failed = []

    for ticker in tickers:
        try:
            ticker_data = data[ticker]
            close = ticker_data["Close"].dropna()
            if len(close) == 0:
                failed.append(ticker)
                continue

            for ts, row in ticker_data.iterrows():
                if pd.notna(row["Close"]):
                    rows.append(
                        {
                            "symbol": ticker,
                            "timestamp": ts.to_pydatetime().replace(tzinfo=None),
                            "open": float(row["Open"]) if pd.notna(row["Open"]) else None,
                            "high": float(row["High"]) if pd.notna(row["High"]) else None,
                            "low": float(row["Low"]) if pd.notna(row["Low"]) else None,
                            "close": float(row["Close"]) if pd.notna(row["Close"]) else None,
                            "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
                            "source": "yfinance_stocks",
                        }
                    )

            successful.append((ticker, len(close)))
        except (KeyError, AttributeError):
            failed.append(ticker)

    print("\nResults:")
    print(f"  Successful: {len(successful)}/{len(tickers)}")
    print(f"  Failed: {len(failed)}")
    if failed:
        print(f"  Failed tickers: {', '.join(failed[:20])}")
    if len(failed) > 20:
        print(f"  ... and {len(failed) - 20} more")

    df = pd.DataFrame(rows)
    print(f"  Total rows: {len(df)}")
    if successful:
        print(f"  Sample: {successful[0][0]} = {successful[0][1]} days")

    return df


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    parser.add_argument("--status", action="store_true", help="Show current count")
    args = parser.parse_args()

    duck = DuckDBStore()

    if args.status:
        count = duck.conn.execute("SELECT COUNT(*) FROM market_data WHERE source = 'yfinance_stocks'").fetchone()[0]
        symbols = duck.conn.execute(
            "SELECT DISTINCT symbol FROM market_data WHERE source = 'yfinance_stocks'"
        ).fetchall()
        print(f"Stock price rows: {count}")
        print(f"Stock symbols: {len(symbols)}")
        if symbols:
            print(f"  {', '.join(s[0] for s in symbols[:20])}")
        duck.close()
        return

    # Get tickers from sentiment
    tickers = get_sentiment_tickers(duck)

    if not tickers:
        print("ERROR: No valid tickers found in sentiment data")
        duck.close()
        return

    # Fetch prices
    df = fetch_stock_prices(tickers, days=args.days)

    if df.empty:
        print("ERROR: No data fetched")
        duck.close()
        return

    # Insert into DuckDB
    # Use DELETE-INSERT by source to avoid duplicates
    try:
        duck.conn.execute("DELETE FROM market_data WHERE source = 'yfinance_stocks'")
        duck.conn.execute("INSERT INTO market_data SELECT * FROM df")
        print(f"\nInserted {len(df)} rows into market_data (source='yfinance_stocks')")
    except Exception as e:
        print(f"ERROR inserting into DuckDB: {e}")
        duck.close()
        return

    # Verify
    count = duck.conn.execute("SELECT COUNT(*) FROM market_data WHERE source = 'yfinance_stocks'").fetchone()[0]
    symbols = duck.conn.execute(
        "SELECT COUNT(DISTINCT symbol) FROM market_data WHERE source = 'yfinance_stocks'"
    ).fetchone()[0]
    print(f"Verification: {count} rows, {symbols} symbols in market_data")

    duck.close()
    print("\nDone! Run 'python tools/sentiment_backtest.py' to test.")


if __name__ == "__main__":
    main()
