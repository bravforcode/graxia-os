"""Check DuckDB data count for audit answer."""
import duckdb, os, shutil

db = 'data/market_data.duckdb'
tmp = 'data/check_count.duckdb'

if not os.path.exists(db):
    print('DuckDB not found')
    exit()

try:
    shutil.copy2(db, tmp)
    con = duckdb.connect(tmp, read_only=True)
    
    total = con.execute('SELECT COUNT(*) FROM ticks').fetchone()[0]
    print(f'Total ticks: {total}')
    
    symbols = con.execute('SELECT symbol, COUNT(*), MIN(timestamp), MAX(timestamp) FROM ticks GROUP BY symbol').fetchall()
    for sym, cnt, first, last in symbols:
        print(f'  {sym}: {cnt} ticks | {first} -> {last}')
    
    tables = con.execute('SHOW TABLES').fetchall()
    table_names = [t[0] for t in tables]
    print(f'Tables: {table_names}')
    
    if 'ohlcv' in table_names:
        bars_1h = con.execute("SELECT COUNT(*) FROM ohlcv WHERE timeframe='1h' AND symbol='XAUUSD'").fetchone()[0]
        print(f'XAUUSD 1H bars: {bars_1h}')
    else:
        print('No ohlcv table yet')
    
    con.close()
    os.remove(tmp)
except Exception as e:
    print(f'Error: {e}')
    if os.path.exists(tmp):
        os.remove(tmp)
