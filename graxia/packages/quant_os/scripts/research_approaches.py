#!/usr/bin/env python3
"""
Research: Test 5 promising forex edge approaches.
1. Mean reversion (fade extreme moves)
2. Momentum (follow trend after consolidation)
3. Volatility breakout
4. Session patterns (London/NY open)
5. Multi-timeframe confirmation
"""
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent.parent

def load_data(symbol, tf):
    path = BASE / "data" / f"{symbol}_{tf}.csv"
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    return df

def test_mean_reversion(df, lookback=20, threshold=2.0):
    """Fade extreme moves - buy when price drops below mean, sell when above."""
    close = df["close"].values.astype(float)
    mean = pd.Series(close).rolling(lookback).mean().values
    std = pd.Series(close).rolling(lookback).std().values
    zscore = (close - mean) / (std + 1e-10)
    
    # Signal: buy when zscore < -threshold, sell when zscore > threshold
    signal = np.zeros(len(close))
    signal[zscore < -threshold] = 1  # buy
    signal[zscore > threshold] = -1  # sell
    
    # P&L
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    
    trades = []
    position = 0
    for i in range(1, len(signal)):
        if signal[i] != 0 and signal[i] != position:
            # Close existing position
            if position != 0:
                pnl = position * returns[i]
                trades.append(pnl)
            # Open new position
            position = signal[i]
        elif position != 0:
            pnl = position * returns[i]
            trades.append(pnl)
    
    if not trades:
        return {"trades": 0, "win_rate": 0, "net": 0, "sharpe": 0}
    
    trades = np.array(trades)
    wins = (trades > 0).sum()
    return {
        "trades": len(trades),
        "win_rate": wins / len(trades),
        "net": trades.sum() * 2350,  # convert to dollars
        "sharpe": trades.mean() / trades.std() * np.sqrt(min(len(trades), 252)) if trades.std() > 0 else 0,
    }

def test_momentum(df, lookback=20, hold=5):
    """Follow trend after consolidation - buy when price breaks above recent high."""
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    
    recent_high = pd.Series(high).rolling(lookback).max().values
    recent_low = pd.Series(low).rolling(lookback).min().values
    
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    
    trades = []
    position = 0
    hold_count = 0
    
    for i in range(lookback + 1, len(close)):
        if position == 0:
            # Entry signals
            if close[i] > recent_high[i-1]:
                position = 1  # buy
                hold_count = 0
            elif close[i] < recent_low[i-1]:
                position = -1  # sell
                hold_count = 0
        else:
            hold_count += 1
            pnl = position * returns[i]
            trades.append(pnl)
            if hold_count >= hold:
                position = 0
    
    if not trades:
        return {"trades": 0, "win_rate": 0, "net": 0, "sharpe": 0}
    
    trades = np.array(trades)
    wins = (trades > 0).sum()
    return {
        "trades": len(trades),
        "win_rate": wins / len(trades),
        "net": trades.sum() * 2350,
        "sharpe": trades.mean() / trades.std() * np.sqrt(min(len(trades), 252)) if trades.std() > 0 else 0,
    }

def test_volatility_breakout(df, lookback=20, mult=1.5):
    """Trade when volatility expands - buy on breakout up, sell on breakout down."""
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    
    # ATR
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    tr = np.concatenate([[high[0] - low[0]], tr])
    atr = pd.Series(tr).rolling(lookback).mean().values
    
    # Breakout
    upper = close + atr * mult
    lower = close - atr * mult
    
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    
    trades = []
    position = 0
    
    for i in range(lookback + 1, len(close)):
        if position == 0:
            if close[i] > upper[i-1]:
                position = 1
            elif close[i] < lower[i-1]:
                position = -1
        else:
            pnl = position * returns[i]
            trades.append(pnl)
            # Exit on opposite signal
            if (position == 1 and close[i] < lower[i-1]) or (position == -1 and close[i] > upper[i-1]):
                position = 0
    
    if not trades:
        return {"trades": 0, "win_rate": 0, "net": 0, "sharpe": 0}
    
    trades = np.array(trades)
    wins = (trades > 0).sum()
    return {
        "trades": len(trades),
        "win_rate": wins / len(trades),
        "net": trades.sum() * 2350,
        "sharpe": trades.mean() / trades.std() * np.sqrt(min(len(trades), 252)) if trades.std() > 0 else 0,
    }

def test_session_pattern(df):
    """Trade specific hours - London open (7-9 UTC), NY open (12-14 UTC)."""
    close = df["close"].values.astype(float)
    hour = df.index.hour.values
    
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    
    # Trade during London open (7-9 UTC)
    trades_london = []
    for i in range(1, len(close)):
        if 7 <= hour[i] < 9:
            # Simple: buy if price went up last bar, sell if down
            if returns[i-1] > 0:
                trades_london.append(returns[i])  # buy
            else:
                trades_london.append(-returns[i])  # sell
    
    # Trade during NY open (12-14 UTC)
    trades_ny = []
    for i in range(1, len(close)):
        if 12 <= hour[i] < 14:
            if returns[i-1] > 0:
                trades_ny.append(returns[i])
            else:
                trades_ny.append(-returns[i])
    
    results = {}
    for name, trades in [("london", trades_london), ("ny", trades_ny)]:
        if not trades:
            results[name] = {"trades": 0, "win_rate": 0, "net": 0, "sharpe": 0}
            continue
        trades = np.array(trades)
        wins = (trades > 0).sum()
        results[name] = {
            "trades": len(trades),
            "win_rate": wins / len(trades),
            "net": trades.sum() * 2350,
            "sharpe": trades.mean() / trades.std() * np.sqrt(min(len(trades), 252)) if trades.std() > 0 else 0,
        }
    return results

def main():
    symbols = ["XAUUSD", "EURUSD", "GBPUSD"]
    timeframes = ["H1", "M15"]
    
    print("=" * 100)
    print("RESEARCH: Testing 5 Forex Edge Approaches")
    print("=" * 100)
    
    all_results = []
    
    for symbol in symbols:
        for tf in timeframes:
            print("\n--- %s %s ---" % (symbol, tf))
            df = load_data(symbol, tf)
            print("Data: %d bars, %s to %s" % (len(df), df.index[0], df.index[-1]))
            
            # Test each approach
            r1 = test_mean_reversion(df, lookback=20, threshold=2.0)
            r2 = test_momentum(df, lookback=20, hold=5)
            r3 = test_volatility_breakout(df, lookback=20, mult=1.5)
            r4 = test_session_pattern(df)
            
            print("  Mean Reversion:  %3d trades, WR=%.1f%%, Net=%+.2f, Sharpe=%+.1f" % (
                r1["trades"], r1["win_rate"]*100, r1["net"], r1["sharpe"]))
            print("  Momentum:        %3d trades, WR=%.1f%%, Net=%+.2f, Sharpe=%+.1f" % (
                r2["trades"], r2["win_rate"]*100, r2["net"], r2["sharpe"]))
            print("  Vol Breakout:    %3d trades, WR=%.1f%%, Net=%+.2f, Sharpe=%+.1f" % (
                r3["trades"], r3["win_rate"]*100, r3["net"], r3["sharpe"]))
            print("  Session London:  %3d trades, WR=%.1f%%, Net=%+.2f, Sharpe=%+.1f" % (
                r4["london"]["trades"], r4["london"]["win_rate"]*100, r4["london"]["net"], r4["london"]["sharpe"]))
            print("  Session NY:      %3d trades, WR=%.1f%%, Net=%+.2f, Sharpe=%+.1f" % (
                r4["ny"]["trades"], r4["ny"]["win_rate"]*100, r4["ny"]["net"], r4["ny"]["sharpe"]))
            
            all_results.append({"symbol": symbol, "tf": tf, "mean_rev": r1, "momentum": r2, "vol_break": r3, "session": r4})
    
    # Find best
    print("\n" + "=" * 100)
    print("BEST OPPORTUNITIES")
    print("=" * 100)
    
    best = []
    for r in all_results:
        for name, data in [("MeanRev", r["mean_rev"]), ("Momentum", r["momentum"]), ("VolBreak", r["vol_break"]),
                           ("Session-London", r["session"]["london"]), ("Session-NY", r["session"]["ny"])]:
            if data["net"] > 0 and data["trades"] >= 10:
                best.append({"symbol": r["symbol"], "tf": r["tf"], "approach": name, **data})
    
    best.sort(key=lambda x: x["net"], reverse=True)
    
    print("%-10s %-4s %-15s %6s %6s %8s %7s" % ("Symbol", "TF", "Approach", "Trades", "Win%", "Net", "Sharpe"))
    print("-" * 70)
    for b in best[:10]:
        print("%-10s %-4s %-15s %6d %5.1f%% %+7.2f %+7.1f" % (
            b["symbol"], b["tf"], b["approach"], b["trades"], b["win_rate"]*100, b["net"], b["sharpe"]))

if __name__ == "__main__":
    main()
