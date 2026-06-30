"""Ingest ETH.V and BTC.V from Stooq crypto dump as ETHUSD_D1 and BTCUSD_D1."""
import csv
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def parse_stooq(filepath):
    rows = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) < 8:
                continue
            try:
                dt = datetime.strptime(row[2], '%Y%m%d').replace(tzinfo=timezone.utc)
                rows.append({
                    'time': dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'open': float(row[4]),
                    'high': float(row[5]),
                    'low': float(row[6]),
                    'close': float(row[7]),
                    'volume': float(row[8]) if len(row) > 8 and row[8] else 0.0,
                })
            except Exception:
                continue
    df = pd.DataFrame(rows)
    df.drop_duplicates(subset=['time'], keep='first', inplace=True)
    df.sort_values('time', inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

base = 'C:/Users/menum/Downloads/d_world_txt/data/daily/world/cryptocurrencies'

for symbol, stooq_file in [('ETHUSD', 'eth.v.txt'), ('BTCUSD', 'btc.v.txt')]:
    filepath = Path(base) / stooq_file
    if not filepath.exists():
        print(f'{symbol}: file not found at {filepath}')
        continue

    df = parse_stooq(filepath)
    print(f'{symbol} ({stooq_file}): {len(df)} rows, {df["time"].min()} to {df["time"].max()}')

    out_path = DATA_DIR / f'{symbol}_D1.csv'
    if out_path.exists():
        existing = pd.read_csv(out_path)
        combined = pd.concat([existing, df], ignore_index=True)
        combined.drop_duplicates(subset=['time'], keep='last', inplace=True)
        combined.sort_values('time', inplace=True)
        combined.reset_index(drop=True, inplace=True)
        combined.to_csv(out_path, index=False)
        print(f'  merged: {len(df)} new + {len(existing)} existing = {len(combined)} total')
    else:
        df.to_csv(out_path, index=False)
        print(f'  saved: {len(df)} rows')

print('Done!')
