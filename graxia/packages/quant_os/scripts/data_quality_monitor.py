"""
data_quality_monitor.py — Check data quality for all symbols
"""
import warnings, pandas as pd
from pathlib import Path
from datetime import datetime, UTC
warnings.filterwarnings('ignore')

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / 'data'
REPORT_DIR = BASE / 'reports'
REPORT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD',
           'XAGUSD', 'XPTUSD', 'XPDUSD', 'US30', 'NAS100', 'BTCUSD', 'ETHUSD']
TFs = ['M15', 'H1', 'D1']

def check_file(csv_path):
    """Check one CSV for quality issues."""
    issues = []
    
    if not csv_path.exists():
        return {'exists': False, 'issues': ['FILE_NOT_FOUND']}
    
    try:
        df = pd.read_csv(csv_path, parse_dates=['time'])
    except Exception as e:
        return {'exists': True, 'issues': [f'PARSE_ERROR: {e}']}
    
    if len(df) == 0:
        return {'exists': True, 'issues': ['EMPTY_FILE']}
    
    # Check recency
    last_time = df['time'].max()
    if hasattr(last_time, 'tzinfo') and last_time.tzinfo is None:
        last_time = last_time.tz_localize('utc')
    age_hours = (datetime.now(UTC) - last_time).total_seconds() / 3600
    if age_hours > 48:
        issues.append(f'STALE_DATA: last={last_time}, age={age_hours:.0f}h')
    
    # Check for gaps
    df_sorted = df.sort_values('time')
    time_diffs = df_sorted['time'].diff().dropna()
    if len(time_diffs) > 0:
        median_diff = time_diffs.median()
        large_gaps = (time_diffs > median_diff * 3).sum()
        if large_gaps > len(df) * 0.01:
            issues.append(f'GAPS: {large_gaps} gaps > 3x median interval')
    
    # Check OHLC integrity
    for _, row in df.iterrows():
        if row['high'] < row['low']:
            issues.append('OHLC_ERROR: high < low')
            break
        if row['close'] > row['high'] or row['close'] < row['low']:
            issues.append('OHLC_ERROR: close outside range')
            break
    
    # Check for outliers (price spikes > 5 std)
    returns = df['close'].pct_change().dropna()
    if len(returns) > 50:
        outliers = (returns.abs() > returns.std() * 5).sum()
        if outliers > 3:
            issues.append(f'OUTLIERS: {outliers} price spikes > 5 std')
    
    return {
        'exists': True,
        'bars': len(df),
        'first_time': str(df['time'].iloc[0])[:10],
        'last_time': str(df['time'].iloc[-1])[:19],
        'age_hours': round(age_hours, 1),
        'issues': issues,
        'size_kb': round(csv_path.stat().st_size / 1024, 1),
    }

def main():
    print('=== Data Quality Monitor ===')
    all_ok = True
    total_issues = 0
    
    for symbol in SYMBOLS:
        for tf in TFs:
            csv_path = DATA_DIR / f'{symbol}_{tf}.csv'
            result = check_file(csv_path)
            
            status = '✅' if not result.get('issues') else '⚠️' if result.get('exists') else '❌'
            issues = result.get('issues', [])
            if issues:
                all_ok = False
                total_issues += len(issues)
            
            bars = result.get('bars', 0)
            age = result.get('age_hours', 0)
            print(f'{status} {symbol:6s} {tf:4s}: {bars:>6,} bars, {age:4.0f}h old {issues[0] if issues else ""}')
    
    # Save report
    report = {
        'timestamp': datetime.now(UTC).isoformat(),
        'all_ok': all_ok,
        'total_issues': total_issues,
    }
    (REPORT_DIR / f'data_quality_{datetime.now().strftime("%Y%m%d")}.json').write_text(
        json.dumps(report, default=str, indent=2))
    
    print(f'\nOverall: {"✅ ALL GOOD" if all_ok else "⚠️ ISSUES FOUND"}')

if __name__ == '__main__':
    import json
    main()
