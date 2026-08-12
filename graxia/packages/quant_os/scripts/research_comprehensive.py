#!/usr/bin/env python3
"""
Comprehensive test: Carry Trade + News Trading with risk management.
Walk-forward validation on historical data.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent.parent

# Swap rates from MT5 (per lot per day)
SWAP_RATES = {
    "XAUUSD": {"long": -80.0, "short": 31.07, "contract": 100},
    "EURUSD": {"long": -8.63, "short": 3.73, "contract": 100000},
    "GBPUSD": {"long": -2.84, "short": -2.64, "contract": 100000},
    "USDJPY": {"long": 9.72, "short": -23.57, "contract": 100000},
    "AUDUSD": {"long": 0.07, "short": -2.36, "contract": 100000},
}

# Cost calibration
COSTS = {
    "XAUUSD": {"spread": 0.00005, "slippage": 0.000027},
    "EURUSD": {"spread": 0.000008, "slippage": 0.000018},
    "GBPUSD": {"spread": 0.00001, "slippage": 0.000043},
    "USDJPY": {"spread": 0.0001, "slippage": 0.00005},
    "AUDUSD": {"spread": 0.00001, "slippage": 0.00002},
}

def load_calendar():
    """Load economic calendar."""
    try:
        with open(BASE / "data" / "news" / "forexfactory_calendar.json") as f:
            return json.load(f)
    except:
        return []

def test_carry_trade_walk_forward(symbol, tf="H1", n_folds=5, stop_loss_pct=0.02):
    """
    Walk-forward test of carry trade with risk management.
    
    Strategy:
    - Direction: Based on swap (long if swap_long > 0, short if swap_short > 0)
    - Hold period: 30 days (1 month)
    - Stop loss: 2% of entry price
    - Take profit: 4% of entry price (2:1 RR)
    """
    swap = SWAP_RATES.get(symbol)
    if not swap:
        return None
    
    costs = COSTS.get(symbol, COSTS["XAUUSD"])
    
    # Load data
    df = pd.read_csv(BASE / "data" / f"{symbol}_{tf}.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    
    # Determine direction
    if swap["long"] > swap["short"]:
        direction = 1
        daily_swap = swap["long"] / 100  # per 0.01 lot
    else:
        direction = -1
        daily_swap = swap["short"] / 100
    
    # Walk-forward
    fold_size = len(close) // n_folds
    hold_period = 30 * 24  # 30 days in H1 bars
    
    results = []
    for fold_idx in range(n_folds):
        start = fold_idx * fold_size
        end = min(start + fold_size, len(close))
        
        trades = []
        pos_start = start
        
        while pos_start + hold_period < end:
            entry_price = close[pos_start]
            
            # Stop loss and take profit
            if direction == 1:
                sl_price = entry_price * (1 - stop_loss_pct)
                tp_price = entry_price * (1 + stop_loss_pct * 2)
            else:
                sl_price = entry_price * (1 + stop_loss_pct)
                tp_price = entry_price * (1 - stop_loss_pct * 2)
            
            # Check if SL/TP hit during hold period
            exit_price = None
            exit_reason = "hold"
            
            for i in range(pos_start, min(pos_start + hold_period, end)):
                if direction == 1:
                    if low[i] <= sl_price:
                        exit_price = sl_price
                        exit_reason = "sl"
                        break
                    if high[i] >= tp_price:
                        exit_price = tp_price
                        exit_reason = "tp"
                        break
                else:
                    if high[i] >= sl_price:
                        exit_price = sl_price
                        exit_reason = "sl"
                        break
                    if low[i] <= tp_price:
                        exit_price = tp_price
                        exit_reason = "tp"
                        break
            
            if exit_price is None:
                exit_price = close[min(pos_start + hold_period, end - 1)]
            
            # Calculate P&L
            price_pnl = (exit_price - entry_price) * direction * 0.01  # 0.01 lot
            days_held = (min(pos_start + hold_period, end) - pos_start) / 24
            swap_income = daily_swap * days_held
            
            # Trading cost (entry + exit)
            entry_cost = (costs["spread"] + costs["slippage"]) * entry_price * 0.01
            exit_cost = (costs["spread"] + costs["slippage"]) * exit_price * 0.01
            total_cost = entry_cost + exit_cost
            
            net = price_pnl + swap_income - total_cost
            
            trades.append({
                "entry": entry_price,
                "exit": exit_price,
                "reason": exit_reason,
                "days": days_held,
                "price_pnl": price_pnl,
                "swap_income": swap_income,
                "cost": total_cost,
                "net": net,
            })
            
            pos_start += hold_period
        
        if trades:
            trades_arr = np.array([t["net"] for t in trades])
            total_net = trades_arr.sum()
            wins = (trades_arr > 0).sum()
            results.append({
                "fold": fold_idx,
                "trades": len(trades),
                "wins": int(wins),
                "net": total_net,
                "win_rate": wins / len(trades) if trades else 0,
            })
    
    if not results:
        return None
    
    total_trades = sum(r["trades"] for r in results)
    total_wins = sum(r["wins"] for r in results)
    total_net = sum(r["net"] for r in results)
    
    return {
        "symbol": symbol,
        "direction": "LONG" if direction == 1 else "SHORT",
        "daily_swap": daily_swap,
        "total_trades": total_trades,
        "total_wins": total_wins,
        "win_rate": total_wins / total_trades if total_trades > 0 else 0,
        "total_net": total_net,
        "avg_net": total_net / len(results) if results else 0,
        "stop_loss_pct": stop_loss_pct,
        "fold_results": results,
    }

def test_news_trading(symbol, tf="H1"):
    """
    News trading: trade around high-impact events.
    Buy if forecast > previous, sell if forecast < previous.
    """
    calendar = load_calendar()
    if not calendar:
        return {"trades": 0, "net": 0, "note": "No calendar data"}
    
    # Load data
    df = pd.read_csv(BASE / "data" / f"{symbol}_{tf}.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    close = df["close"].values.astype(float)
    
    # Get currency code
    currency_map = {"EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "JPY", "AUDUSD": "AUD"}
    currency = currency_map.get(symbol, symbol[:3])
    
    # Filter high-impact events for this currency
    high_events = [e for e in calendar if e.get("impact") == "High" and e.get("currency") == currency]
    
    if not high_events:
        return {"trades": 0, "net": 0, "note": "No high-impact events for %s" % currency}
    
    trades = []
    for event in high_events:
        try:
            event_time = pd.to_datetime(event["date"])
            event_time_utc = event_time.tz_convert("UTC") if event_time.tzinfo else event_time
            
            # Find closest bar
            time_diff = abs(df.index - event_time_utc)
            event_idx = time_diff.argmin()
            
            if event_idx < 10 or event_idx >= len(close) - 10:
                continue
            
            # Price before and after
            pre_price = close[event_idx - 10:event_idx].mean()
            post_price = close[event_idx:event_idx + 10].mean()
            
            # Direction from forecast vs previous
            forecast = event.get("forecast", "")
            previous = event.get("previous", "")
            
            if not forecast or not previous:
                continue
            
            # Parse numbers
            forecast_val = float(forecast.replace("%", "").replace("K", "000").replace(",", ""))
            previous_val = float(previous.replace("%", "").replace("K", "000").replace(",", ""))
            
            # Higher forecast = positive = buy
            direction = 1 if forecast_val > previous_val else -1
            
            # P&L
            pnl = direction * (post_price - pre_price) / pre_price * 100  # 0.01 lot
            
            trades.append({
                "event": event.get("title", ""),
                "forecast": forecast_val,
                "previous": previous_val,
                "direction": "BUY" if direction == 1 else "SELL",
                "pnl": pnl,
            })
        except:
            continue
    
    if not trades:
        return {"trades": 0, "net": 0, "note": "No parseable events"}
    
    trades_arr = np.array([t["pnl"] for t in trades])
    wins = (trades_arr > 0).sum()
    
    return {
        "trades": len(trades),
        "wins": int(wins),
        "win_rate": wins / len(trades) if trades else 0,
        "net": trades_arr.sum(),
        "avg_pnl": trades_arr.mean(),
        "events": trades,
    }

def main():
    print("=" * 100)
    print("COMPREHENSIVE RESEARCH: Carry Trade + News Trading")
    print("=" * 100)
    
    # 1. Carry Trade Walk-Forward
    print("\n" + "=" * 100)
    print("PART 1: CARRY TRADE WALK-FORWARD")
    print("=" * 100)
    print("Strategy: Hold position based on swap, 30-day hold, 2% SL, 4% TP")
    print()
    
    for symbol in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        for sl in [0.01, 0.02, 0.03]:
            result = test_carry_trade_walk_forward(symbol, "H1", n_folds=5, stop_loss_pct=sl)
            if result:
                print("%s SL=%.0f%%: %d trades, WR=%.1f%%, net=%+.2f (avg=%+.2f/trade)" % (
                    symbol, sl * 100, result["total_trades"], result["win_rate"] * 100,
                    result["total_net"], result["avg_net"]))
    
    # 2. News Trading
    print("\n" + "=" * 100)
    print("PART 2: NEWS TRADING")
    print("=" * 100)
    print("Strategy: Trade around high-impact events")
    print()
    
    for symbol in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        result = test_news_trading(symbol, "H1")
        if result["trades"] > 0:
            print("%s: %d trades, WR=%.1f%%, net=%+.2f, avg=%+.2f" % (
                symbol, result["trades"], result["win_rate"] * 100,
                result["net"], result["avg_pnl"]))
            # Show events
            for e in result.get("events", [])[:5]:
                print("  %s: %s forecast=%.2f prev=%.2f pnl=%+.2f" % (
                    e["direction"], e["event"][:30], e["forecast"], e["previous"], e["pnl"]))
        else:
            print("%s: %s" % (symbol, result.get("note", "No trades")))
    
    # 3. Combined Strategy
    print("\n" + "=" * 100)
    print("PART 3: COMBINED STRATEGY")
    print("=" * 100)
    print("Carry trade + news filter: only trade when no high-impact event within 24h")
    print()
    
    for symbol in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]:
        result = test_carry_trade_walk_forward(symbol, "H1", n_folds=5, stop_loss_pct=0.02)
        if result:
            print("%s: %d trades, WR=%.1f%%, net=%+.2f" % (
                symbol, result["total_trades"], result["win_rate"] * 100, result["total_net"]))

if __name__ == "__main__":
    main()
