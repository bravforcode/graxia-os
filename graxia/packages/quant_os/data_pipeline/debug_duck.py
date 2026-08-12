import sys
sys.path.insert(0, r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline")
from storage.duckdb_store import DuckDBStore

db = DuckDBStore()
df = db.query("SELECT symbol, close, source FROM market_data WHERE source='yfinance' ORDER BY symbol")
print("=== yfinance data in DuckDB ===")
for _, r in df.iterrows():
    print(f"  {r['symbol']}: {r['close']}")
db.close()
