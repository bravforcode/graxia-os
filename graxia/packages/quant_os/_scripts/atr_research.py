"""ATR Research Script — Compute ATR stats from raw M15 XAUUSD data."""
import pandas as pd
import numpy as np
import glob
import os
import json

base = r'C:\Users\menum\graxia os\graxia\packages\quant_os\data\warehouse\ohlcv\symbol=XAUUSD\frequency=M15\source=MT5'
files = sorted(glob.glob(os.path.join(base, '**', '*.parquet'), recursive=True))
print(f'Found {len(files)} M15 XAUUSD parquet files')

# Read all files
dfs = []
for f in files:
    df = pd.read_parquet(f)
    dfs.append(df)
df = pd.concat(dfs, ignore_index=True)
df = df.sort_values('time').reset_index(drop=True)

print(f'Total rows: {len(df)}')
print(f'Columns: {list(df.columns)}')
print(f'Date range: {df["time"].min()} to {df["time"].max()}')
print(df.dtypes)

# Compute True Range and ATR(14)
# For efficiency, use a simplified vectorized ATR on a subset if data is huge, or full
# Let's do the full computation

high = df['high'].values
low = df['low'].values
close = df['close'].values
prev_close = np.roll(close, 1)
prev_close[0] = close[0]

tr = np.maximum(high - low, 
                np.maximum(np.abs(high - prev_close), 
                           np.abs(low - prev_close)))

# ATR(14) via SMA for first 14, then EMA
period = 14
atr = np.zeros_like(tr)
atr[:period] = np.mean(tr[:period])
for i in range(period, len(tr)):
    atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period

df['atr_14'] = atr

# Stats
stats = {
    'mean': float(np.mean(atr)),
    'median': float(np.median(atr)),
    'std': float(np.std(atr)),
    'p1': float(np.percentile(atr, 1)),
    'p5': float(np.percentile(atr, 5)),
    'p10': float(np.percentile(atr, 10)),
    'p25': float(np.percentile(atr, 25)),
    'p50': float(np.percentile(atr, 50)),
    'p75': float(np.percentile(atr, 75)),
    'p90': float(np.percentile(atr, 90)),
    'p95': float(np.percentile(atr, 95)),
    'p99': float(np.percentile(atr, 99)),
    'min': float(np.min(atr)),
    'max': float(np.max(atr)),
}

print('\n=== ATR(14) STATS (ratio, raw) ===')
for k, v in stats.items():
    print(f'  {k}: {v:.6f}')

price = 4030.0
# ATR is already in dollar terms (XAUUSD prices are in USD)
# No multiplication needed — atr_14 = $6.45 means $6.45 USD
print('\n=== ATR(14) IN DOLLARS (XAUUSD quoted in USD, so ATR is already $) ===')
for k in ['mean', 'median', 'p10', 'p25', 'p50', 'p75', 'p90', 'p95', 'min', 'max']:
    v = stats[k]
    print(f'  {k}: ${v:.2f}')

print('\n=== ATR(14) IN POINTS (1 point = $0.01 for XAUUSD) ===')
for k in ['mean', 'median', 'p25', 'p75', 'p90']:
    v = stats[k]
    print(f'  {k}: {v*100:.1f} points (${v:.2f})')

# What multiples of ATR give us?
print('\n=== STOP DISTANCE COMPARISON ===')
# Fixed $3.00 stop
fixed_stop = 3.0
print(f'Fixed $3.00 stop = ${fixed_stop:.2f}')
print(f'  As multiple of mean ATR: {fixed_stop / stats["mean"]:.3f}x')
print(f'  As multiple of median ATR: {fixed_stop / stats["median"]:.3f}x')
print(f'  As multiple of p90 ATR: {fixed_stop / stats["p90"]:.3f}x')
print(f'  As multiple of min ATR: {fixed_stop / stats["min"]:.3f}x')
print(f'  As % of mean ATR: {fixed_stop / stats["mean"] * 100:.1f}%')
print(f'  As % of median ATR: {fixed_stop / stats["median"] * 100:.1f}%')
print(f'  As % of p90 ATR: {fixed_stop / stats["p90"] * 100:.1f}%')

# ATR in price-point terms (XAUUSD price points)
print(f'\n  $3.00 stop = {3.0 * 100:.0f} XAUUSD points (0.01 per point)')

# What ATR multiple is $3.00?
print(f'\n$3.00 = {fixed_stop / stats["mean"]:.2f}x of mean ATR')
print(f'$3.00 = {fixed_stop / stats["median"]:.2f}x of median ATR')

# Formula candidates (ALL in dollars directly, ATR IS dollar)
f1_stop = np.maximum(3.0, 2.0 * atr)       # max($3, 2×ATR)
f2_stop = 1.5 * atr                         # 1.5×ATR
f3_stop = np.maximum(3.0, np.minimum(2.0 * atr, 6.0))  # max($3, min(2×ATR, $6))
f4_stop = np.maximum(1.5, atr * 1.0)        # at least $1.50, at least 1×ATR
f5_stop = np.maximum(3.0, atr * 0.5)        # max($3, 0.5×ATR) — tighter variant

print('\n=== STOP FORMULA COMPARISON ===')
for name, stop_arr in [('Fixed $3.00', np.full_like(atr, 3.0)),
                        ('max($3, 2×ATR)', f1_stop),
                        ('1.5×ATR', f2_stop),
                        ('max($3, min(2×ATR, $6))', f3_stop),
                        ('max($1.50, 1×ATR)', f4_stop),
                        ('max($3, 0.5×ATR)', f5_stop)]:
    print(f'\n--- {name} ---')
    print(f'  Mean stop: ${np.mean(stop_arr):.2f}')
    print(f'  Median stop: ${np.median(stop_arr):.2f}')
    print(f'  Min stop: ${np.min(stop_arr):.2f}')
    print(f'  Max stop: ${np.max(stop_arr):.2f}')
    print(f'  P10 stop: ${np.percentile(stop_arr, 10):.2f}')
    print(f'  P90 stop: ${np.percentile(stop_arr, 90):.2f}')
    tighter_pct = np.mean(stop_arr < 3.0) * 100
    wider_pct = np.mean(stop_arr > 3.0) * 100
    print(f'  % tighter than $3.00: {tighter_pct:.1f}%')
    print(f'  % wider than $3.00: {wider_pct:.1f}%')
    print(f'  % same as $3.00: {100 - tighter_pct - wider_pct:.1f}%')

# Save results as JSON for the research document
result = {
    'atr_stats': stats,
    'price': price,
}

with open(r'C:\Users\menum\graxia os\graxia\packages\quant_os\_scripts\atr_results.json', 'w') as f:
    json.dump(result, f, indent=2)

print('\n=== SESSION STATS ===')
# Group by session to see if ATR differs by session
df['hour'] = pd.to_datetime(df['time']).dt.hour
# Asian: 0-8, EU: 8-16, US: 16-24 (rough)
def session(h):
    if 0 <= h < 8:
        return 'Asian'
    elif 8 <= h < 16:
        return 'EU'
    else:
        return 'US'
df['session'] = df['hour'].apply(session)
session_stats = df.groupby('session')['atr_14'].describe()
print('\nATR by session:')
print(session_stats)

# Dollars per session (ATR already in dollars)
for s in ['Asian', 'EU', 'US']:
    sub = df[df['session'] == s]['atr_14']
    print(f'  {s}: mean=${sub.mean():.2f}, median=${sub.median():.2f}, p90=${sub.quantile(0.9):.2f}')

# Save session stats too
result['session_stats'] = {
    s: {
        'mean': float(df[df['session'] == s]['atr_14'].mean()),
        'median': float(df[df['session'] == s]['atr_14'].median()),
        'p90': float(df[df['session'] == s]['atr_14'].quantile(0.9)),
    }
    for s in ['Asian', 'EU', 'US']
}

with open(r'C:\Users\menum\graxia os\graxia\packages\quant_os\_scripts\atr_results.json', 'w') as f:
    json.dump(result, f, indent=2)

print('\nDone. Results saved.')
