"""
backtest_suite.py — Multi-strategy backtest engine for all symbols
Tests: Momentum, Mean Reversion, ML Breakout, Trend Following, Volatility Breakout
"""
import json, warnings, numpy as np, pandas as pd
from pathlib import Path
from datetime import datetime

# Canonical return calculation — single source of truth
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.returns import compute_returns

warnings.filterwarnings('ignore')

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / 'data'
RESULTS_DIR = BASE / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'US30', 'NAS100', 'BTCUSD']

def backtest_momentum(df, lookback=12, hold=5):
    """Momentum: buy if price > MA(lookback), sell if <"""
    df = df.copy()
    df['ma'] = df['close'].rolling(lookback).mean()
    df['signal'] = 0
    df.loc[df['close'] > df['ma'], 'signal'] = 1
    df.loc[df['close'] < df['ma'], 'signal'] = -1
    df['returns'] = compute_returns(df['close'])
    df['strat_ret'] = df['signal'].shift(1) * df['returns']
    return calc_metrics(df, 'Momentum')

def backtest_mean_reversion(df, window=20, entry_z=2.0):
    """Mean reversion: buy when price < MA - 2*std, sell when > MA + 2*std"""
    df = df.copy()
    df['ma'] = df['close'].rolling(window).mean()
    df['std'] = df['close'].rolling(window).std()
    df['z'] = (df['close'] - df['ma']) / df['std']
    df['signal'] = 0
    df.loc[df['z'] < -entry_z, 'signal'] = 1
    df.loc[df['z'] > entry_z, 'signal'] = -1
    df['returns'] = compute_returns(df['close'])
    df['strat_ret'] = df['signal'].shift(1) * df['returns']
    return calc_metrics(df, 'MeanReversion')

def backtest_trend_follow(df, fast=10, slow=30):
    """Trend following: MA crossover"""
    df = df.copy()
    df['ma_fast'] = df['close'].rolling(fast).mean()
    df['ma_slow'] = df['close'].rolling(slow).mean()
    df['signal'] = 0
    df.loc[df['ma_fast'] > df['ma_slow'], 'signal'] = 1
    df.loc[df['ma_fast'] < df['ma_slow'], 'signal'] = -1
    df['returns'] = compute_returns(df['close'])
    df['strat_ret'] = df['signal'].shift(1) * df['returns']
    return calc_metrics(df, 'TrendFollow')

def backtest_volatility_breakout(df, lookback=20, mult=1.5):
    """Volatility breakout: buy when price breaks above high + ATR*mult"""
    df = df.copy()
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    df['atr'] = tr.rolling(lookback).mean()
    df['upper'] = df['high'].rolling(lookback).max()
    df['lower'] = df['low'].rolling(lookback).min()
    df['signal'] = 0
    df.loc[df['close'] > df['upper'], 'signal'] = 1
    df.loc[df['close'] < df['lower'], 'signal'] = -1
    df['returns'] = compute_returns(df['close'])
    df['strat_ret'] = df['signal'].shift(1) * df['returns']
    return calc_metrics(df, 'VolBreakout')

def backtest_rsi_strategy(df, period=14, oversold=30, overbought=70):
    """RSI: buy when oversold, sell when overbought"""
    df = df.copy()
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['signal'] = 0
    df.loc[df['rsi'] < oversold, 'signal'] = 1
    df.loc[df['rsi'] > overbought, 'signal'] = -1
    df['returns'] = compute_returns(df['close'])
    df['strat_ret'] = df['signal'].shift(1) * df['returns']
    return calc_metrics(df, 'RSI')

def calc_metrics(df, name):
    """Calculate performance metrics."""
    strat = df['strat_ret'].dropna()
    if len(strat) < 20:
        return {'strategy': name, 'error': 'insufficient data'}
    
    total_ret = float(strat.sum())
    sharpe = float(np.sqrt(252*96) * strat.mean() / strat.std()) if strat.std() > 0 else 0.0
    win_rate = float((strat > 0).mean())
    max_dd = float((strat.cumsum().cummax() - strat.cumsum()).max())
    profit_factor = float(abs(strat[strat > 0].sum() / strat[strat < 0].sum())) if strat[strat < 0].sum() != 0 else float('inf')
    
    return {
        'strategy': name,
        'total_return_pct': round(total_ret * 100, 2),
        'sharpe': round(sharpe, 2),
        'win_rate_pct': round(win_rate * 100, 1),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'profit_factor': round(profit_factor, 2),
        'n_trades': int(len(strat)),
    }

def detect_regime(df):
    """Detect market regime: trending vs ranging"""
    df = df.copy()
    df['ret'] = compute_returns(df['close'])
    df['ma_50'] = df['close'].rolling(50).mean()
    df['ma_200'] = df['close'].rolling(200).mean()
    
    # Trend strength: ratio of trend to noise
    trend = (df['ma_50'] - df['ma_50'].shift(50)).abs().iloc[-1] if len(df) > 250 else 0
    noise = df['ret'].std() * np.sqrt(50)
    
    if noise > 0:
        trend_strength = min(trend / noise, 5.0)
    else:
        trend_strength = 0.0
    
    # Volatility regime
    current_vol = df['ret'].iloc[-20:].std()
    hist_vol = df['ret'].iloc[-100:].std()
    vol_ratio = current_vol / hist_vol if hist_vol > 0 else 1.0
    
    regime = 'trending' if trend_strength > 1.5 else 'ranging'
    vol_regime = 'high_vol' if vol_ratio > 1.3 else 'low_vol' if vol_ratio < 0.7 else 'normal'
    
    return {
        'regime': regime,
        'trend_strength': round(float(trend_strength), 2),
        'vol_regime': vol_regime,
        'vol_ratio': round(float(vol_ratio), 2),
        'current_price': float(df['close'].iloc[-1]),
        'ma_50': float(df['ma_50'].iloc[-1]) if not pd.isna(df['ma_50'].iloc[-1]) else 0,
        'ma_200': float(df['ma_200'].iloc[-1]) if not pd.isna(df['ma_200'].iloc[-1]) else 0,
    }

def main():
    print('=== Backtest Suite ===')
    
    strategies = [backtest_momentum, backtest_mean_reversion, backtest_trend_follow,
                  backtest_volatility_breakout, backtest_rsi_strategy]
    
    all_results = {}
    
    for symbol in SYMBOLS:
        csv_path = DATA_DIR / f'{symbol}_M15.csv'
        if not csv_path.exists():
            csv_path = DATA_DIR / f'{symbol}_H1.csv'
        if not csv_path.exists():
            print(f'{symbol}: no data, skipping')
            continue
        
        df = pd.read_csv(csv_path, parse_dates=['time'])
        df = df.sort_values('time').dropna()
        print(f'\n{symbol}: {len(df):,} bars ({str(df["time"].iloc[0])[:10]} -> {str(df["time"].iloc[-1])[:10]})')
        
        # Detect regime
        regime = detect_regime(df)
        print(f'  Regime: {regime["regime"]} | Vol: {regime["vol_regime"]} | Trend: {regime["trend_strength"]}')
        
        symbol_results = {'regime': regime, 'strategies': {}}
        
        for strat_fn in strategies:
            try:
                result = strat_fn(df)
                if 'error' in result:
                    print(f'  {result["strategy"]:15s}: ERROR - {result["error"]}')
                else:
                    symbol_results['strategies'][result['strategy']] = result
                    sharpe_str = f'{result["sharpe"]:.2f}'
                    wr_str = f'{result["win_rate_pct"]:.1f}%'
                    pf_str = f'{result["profit_factor"]:.2f}'
                    print(f'  {result["strategy"]:15s}: Sharpe={sharpe_str} WR={wr_str} PF={pf_str} Ret={result["total_return_pct"]:.1f}%')
            except Exception as e:
                print(f'  {strat_fn.__name__}: EXCEPTION {e}')
        
        all_results[symbol] = symbol_results
    
    # Save
    output = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M UTC'),
        'symbols_tested': len(all_results),
        'results': all_results
    }
    
    path = RESULTS_DIR / f'backtest_suite_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f'\nResults saved: {path}')
    
    # Find best strategy per symbol
    print('\n=== Best Strategy Per Symbol ===')
    for sym, sr in all_results.items():
        best = None
        best_sharpe = -999
        for sname, sdata in sr.get('strategies', {}).items():
            if sdata.get('sharpe', -999) > best_sharpe:
                best_sharpe = sdata['sharpe']
                best = sname
        regime = sr.get('regime', {})
        print(f'{sym:7s}: best={best:15s} Sharpe={best_sharpe:.2f} | Regime={regime.get("regime","?")}/{regime.get("vol_regime","?")}')

if __name__ == '__main__':
    main()
