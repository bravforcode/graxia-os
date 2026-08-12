"""Daily data quality check — run manually or via cron."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import duckdb

def check_data_quality():
    db_path = os.getenv("DUCKDB_PATH", "data/market_data.duckdb")
    if not os.path.exists(db_path):
        print("ERROR: DuckDB file not found")
        return

    con = duckdb.connect(db_path, read_only=True)

    # Total ticks
    total = con.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
    print(f"Total ticks: {total}")

    # Per symbol
    symbols = con.execute(
        "SELECT symbol, COUNT(*) as cnt, MIN(timestamp) as first, MAX(timestamp) as last "
        "FROM ticks GROUP BY symbol ORDER BY cnt DESC"
    ).fetchall()
    print("\nPer symbol:")
    for sym, cnt, first, last in symbols:
        print(f"  {sym}: {cnt} ticks | {first} -> {last}")

    # Gaps (ticks > 10s apart)
    gaps = con.execute("""
        SELECT symbol, timestamp, 
               LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_ts,
               EXTRACT(EPOCH FROM (timestamp - LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp))) as gap_sec
        FROM ticks
        HAVING gap_sec > 10
        ORDER BY gap_sec DESC
        LIMIT 5
    """).fetchall()
    if gaps:
        print("\nTop 5 gaps (>10s):")
        for sym, ts, prev, gap in gaps:
            print(f"  {sym}: {gap:.1f}s gap at {ts}")
    else:
        print("\nNo gaps >10s detected")

    # OHLCV bars
    try:
        bars = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        print(f"\nOHLCV bars: {bars}")
    except:
        print("\nNo OHLCV table yet")

    # Spread stats
    try:
        spread = con.execute("""
            SELECT symbol, 
                   AVG(spread_bps) as avg_spread,
                   MIN(spread_bps) as min_spread,
                   MAX(spread_bps) as max_spread
            FROM ticks 
            WHERE spread_bps > 0
            GROUP BY symbol
        """).fetchall()
        print("\nSpread stats:")
        for sym, avg, mn, mx in spread:
            print(f"  {sym}: avg={avg:.1f}bps min={mn:.1f}bps max={mx:.1f}bps")
    except:
        pass

    con.close()
    print("\nQuality check complete")

if __name__ == "__main__":
    check_data_quality()
