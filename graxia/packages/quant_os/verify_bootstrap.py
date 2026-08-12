"""Verify bootstrap data."""

import re

import duckdb

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(name: str) -> str:
    """Validate identifier against safe pattern to prevent SQL injection.

    Raises ValueError if name does not match [A-Za-z_][A-Za-z0-9_]*.
    """
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


con = duckdb.connect("data/market_data.duckdb", read_only=True)
tables = con.execute("SHOW TABLES").fetchall()
print("Tables:", [t[0] for t in tables])

for t in tables:
    table_name = _safe_identifier(t[0])
    count = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    print(f"  {table_name}: {count} rows")

if "ohlcv" in [t[0] for t in tables]:
    for sym in ["XAUUSD", "EURUSD"]:
        safe_sym = _safe_identifier(sym)
        cnt = con.execute("SELECT COUNT(*) FROM ohlcv WHERE symbol=? AND timeframe='1h'", [safe_sym]).fetchone()[0]
        print(f"  {safe_sym} 1H: {cnt} bars")
        if cnt > 0:
            first = con.execute("SELECT MIN(time) FROM ohlcv WHERE symbol=? AND timeframe='1h'", [safe_sym]).fetchone()[
                0
            ]
            last = con.execute("SELECT MAX(time) FROM ohlcv WHERE symbol=? AND timeframe='1h'", [safe_sym]).fetchone()[
                0
            ]
            print(f"    Range: {first} to {last}")

con.close()
