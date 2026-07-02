"""Run Triple-Barrier labeling on XAUUSD 1H bars."""
import sys
sys.path.insert(0, '.')
from ml.labeling import prepare_labeled_dataset
import duckdb

con = duckdb.connect('data/market_data.duckdb', read_only=True)
df = con.execute(
    "SELECT time, open, high, low, close, symbol "
    "FROM ohlcv WHERE symbol='XAUUSD' AND timeframe='1h' ORDER BY time"
).fetchdf()
con.close()

print(f'Loaded {len(df)} bars')

df = prepare_labeled_dataset(df)

print(f'After labeling: {len(df)} rows')
print()
print('Label distribution:')
print(df['label'].value_counts().sort_index())

win = (df['label'] == 1).sum()
loss = (df['label'] == -1).sum()
timeout = (df['label'] == 0).sum()
total = len(df)

print(f'Win: {win} ({win/total*100:.1f}%)')
print(f'Loss: {loss} ({loss/total*100:.1f}%)')
print(f'Timeout: {timeout} ({timeout/total*100:.1f}%)')
if loss > 0:
    print(f'Payoff Ratio (Win/Loss count): {win/loss:.2f}')
