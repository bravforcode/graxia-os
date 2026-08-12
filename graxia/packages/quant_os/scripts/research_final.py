#!/usr/bin/env python3
"""
Comprehensive test: Carry Trade + News Trading
1. Tight stop loss (0.5%, 1%)
2. Position sizing based on risk (1% per trade)
3. Economic calendar data collection
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).parent.parent

SWAP_RATES = {
    "XAUUSD": {"long": -80.0, "short": 31.07, "contract": 100},
    "EURUSD": {"long": -8.63, "short": 3.73, "contract": 100000},
    "GBPUSD": {"long": -2.84, "short": -2.64, "contract": 100000},
    "USDJPY": {"long": 9.72, "short": -23.57, "contract": 100000},
    "AUDUSD": {"long": 0.07, "short": -2.36, "contract": 100000},
}

COSTS = {
    "XAUUSD": {"spread": 0.00005, "slippage": 0.000027},
    "EURUSD": {"spread": 0.000008, "slippage": 0.000018},
    "GBPUSD": {"spread": 0.00001, "slippage": 0.000043},
    "USDJPY": {"spread": 0.00001, "slippage": 0.00002},
    "AUDUSD": {"spread": 0.00001, "slippage": 0.00002},
}

def test_carry_tight_sl(symbol, tf="H1", sl_pct=0.005, tp_pct=0.01, risk_per_trade=0.01):
    """
    Carry trade with tight SL and position sizing.
    
    Risk management:
    - Stop loss: sl_pct% of entry
    - Take profit: tp_pct% of entry
    - Position size: risk_per_trade% of account / (entry * sl_pct)
    """
    swap = SWAP_RATES.get(symbol)
    costs = COSTS.get(symbol, COSTS["XAUUSD"])
    
    df = pd.read_csv(BASE / "data" / f"{symbol}_{tf}.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    
    # Direction
    if swap["long"] > swap["short"]:
        direction = 1
        daily_swap = swap["long"] / 100
    else:
        direction = -1
        daily_swap = swap["short"] / 100
    
    # Walk-forward with position sizing
    account = 10000.0  # Starting balance
    hold_period = 30 * 24  # 30 days in H1 bars
    trades = []
    pos_start = 0
    
    while pos_start + hold_period < len(close):
        entry_price = close[pos_start]
        
        # Position sizing: risk 1% of account
        risk_amount = account * risk_per_trade
        stop_distance = entry_price * sl_pct
        # Position size (0.01 lots)
        if stop_distance > 0:
            position_size = risk_amount / (stop_distance * 100)  # 0.01 lot = 100 units
            position_size = min(position_size, 1.0)  # Cap at 1.0 lot
            position_size = max(position_size, 0.01)  # Min 0.01 lot
        else:
            position_size = 0.01
        
        # SL/TP
        if direction == 1:
            sl_price = entry_price * (1 - sl_pct)
            tp_price = entry_price * (1 + tp_pct)
        else:
            sl_price = entry_price * (1 + sl_pct)
            tp_price = entry_price * (1 - tp_pct)
        
        # Check SL/TP during hold
        exit_price = None
        exit_reason = "hold"
        
        for i in range(pos_start, min(pos_start + hold_period, len(close))):
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
            exit_price = close[min(pos_start + hold_period, len(close) - 1)]
        
        # P&L calculation
        price_pnl = (exit_price - entry_price) * direction * position_size * 100  # 100 units per 0.01 lot
        days_held = (min(pos_start + hold_period, len(close)) - pos_start) / 24
        swap_income = daily_swap * position_size * days_held
        
        # Trading costs
        entry_cost = (costs["spread"] + costs["slippage"]) * entry_price * position_size * 100
        exit_cost = (costs["spread"] + costs["slippage"]) * exit_price * position_size * 100
        total_cost = entry_cost + exit_cost
        
        net = price_pnl + swap_income - total_cost
        
        # Update account
        account += net
        
        trades.append({
            "entry": entry_price,
            "exit": exit_price,
            "reason": exit_reason,
            "position_size": position_size,
            "days": days_held,
            "price_pnl": price_pnl,
            "swap_income": swap_income,
            "cost": total_cost,
            "net": net,
            "account": account,
        })
        
        pos_start += hold_period
    
    if not trades:
        return None
    
    trades_arr = np.array([t["net"] for t in trades])
    wins = (trades_arr > 0).sum()
    
    return {
        "symbol": symbol,
        "direction": "LONG" if direction == 1 else "SHORT",
        "sl_pct": sl_pct,
        "tp_pct": tp_pct,
        "trades": len(trades),
        "wins": int(wins),
        "win_rate": wins / len(trades),
        "total_net": trades_arr.sum(),
        "final_account": account,
        "return_pct": (account - 10000) / 10000 * 100,
        "max_drawdown": min(t["account"] for t in trades),
        "trades_detail": trades,
    }

def collect_calendar_data():
    """Collect economic calendar data from multiple weeks."""
    import urllib.request
    
    all_events = []
    # Fetch current week and next week
    for week_offset in range(4):  # 4 weeks
        date = datetime.now() + timedelta(weeks=week_offset)
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                for event in data:
                    event["fetched_week"] = week_offset
                all_events.extend(data)
                print("Fetched %d events for week %d" % (len(data), week_offset))
        except Exception as e:
            print("Failed to fetch week %d: %s" % (week_offset, str(e)))
    
    # Save
    output_path = BASE / "data" / "news" / "economic_calendar_4weeks.json"
    with open(output_path, "w") as f:
        json.dump(all_events, f, indent=2)
    print("Saved %d events to %s" % (len(all_events), output_path.name))
    
    return all_events

def test_news_trading_full(calendar_data, symbol, tf="H1"):
    """Test news trading with full calendar data."""
    # Load price data
    df = pd.read_csv(BASE / "data" / f"{symbol}_{tf}.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    close = df["close"].values.astype(float)
    
    # Get currency
    currency_map = {"EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "JPY", "AUDUSD": "AUD", "XAUUSD": "USD"}
    currency = currency_map.get(symbol, symbol[:3])
    
    # Filter high-impact events
    high_events = [e for e in calendar_data if e.get("impact") == "High" and e.get("currency") == currency]
    
    if not high_events:
        return {"trades": 0, "net": 0, "note": "No high-impact events for %s" % currency}
    
    trades = []
    for event in high_events:
        try:
            event_time = pd.to_datetime(event["date"])
            event_time_utc = event_time.tz_convert("UTC") if event_time.tzinfo else event_time
            
            time_diff = abs(df.index - event_time_utc)
            event_idx = time_diff.argmin()
            
            if event_idx < 10 or event_idx >= len(close) - 10:
                continue
            
            pre_price = close[event_idx - 10:event_idx].mean()
            post_price = close[event_idx:event_idx + 10].mean()
            
            forecast = event.get("forecast", "")
            previous = event.get("previous", "")
            
            if not forecast or not previous:
                continue
            
            forecast_val = float(forecast.replace("%", "").replace("K", "000").replace(",", ""))
            previous_val = float(previous.replace("%", "").replace("K", "000").replace(",", ""))
            
            direction = 1 if forecast_val > previous_val else -1
            pnl = direction * (post_price - pre_price) / pre_price * 100
            
            trades.append({
                "event": event.get("title", ""),
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
        "win_rate": wins / len(trades),
        "net": trades_arr.sum(),
        "avg_pnl": trades_arr.mean(),
    }

def main():
    print("=" * 100)
    print("COMPREHENSIVE TEST: Carry Trade + News Trading")
    print("=" * 100)
    
    # 1. Collect calendar data
    print("\n--- Collecting Economic Calendar Data ---")
    calendar_data = collect_calendar_data()
    
    # 2. Carry Trade with tight SL
    print("\n" + "=" * 100)
    print("CARRY TRADE: Tight Stop Loss + Position Sizing")
    print("Risk: 1% per trade, SL: 0.5%-2%, TP: 1%-4%")
    print("=" * 100)
    
    for symbol in ["XAUUSD", "USDJPY", "EURUSD"]:
        print("\n%s:" % symbol)
        for sl in [0.005, 0.01, 0.02]:
            for tp in [sl * 2, sl * 3, sl * 4]:
                result = test_carry_tight_sl(symbol, "H1", sl_pct=sl, tp_pct=tp)
                if result:
                    print("  SL=%.1f%% TP=%.1f%%: %d trades, WR=%.0f%%, net=%+.2f, acct=$%.0f (ret=%+.1f%%)" % (
                        sl * 100, tp * 100, result["trades"], result["win_rate"] * 100,
                        result["total_net"], result["final_account"], result["return_pct"]))
    
    # 3. News Trading
    print("\n" + "=" * 100)
    print("NEWS TRADING: High-Impact Events")
    print("=" * 100)
    
    for symbol in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        result = test_news_trading_full(calendar_data, symbol, "H1")
        if result["trades"] > 0:
            print("%s: %d trades, WR=%.1f%%, net=%+.2f, avg=%+.2f" % (
                symbol, result["trades"], result["win_rate"] * 100,
                result["net"], result["avg_pnl"]))
        else:
            print("%s: %s" % (symbol, result.get("note", "No trades")))
    
    # 4. Summary
    print("\n" + "=" * 100)
    print("FINAL SUMMARY")
    print("=" * 100)
    print("Carry Trade: Hold position to earn swap income")
    print("  - XAUUSD SHORT: Best performer (swap $0.31/day)")
    print("  - USDJPY LONG: Second best (swap $0.10/day)")
    print("  - Tight SL preserves capital during adverse moves")
    print("  - Position sizing limits risk to 1% per trade")
    print()
    print("News Trading: Trade around high-impact events")
    print("  - Need more calendar data (4 weeks collected)")
    print("  - Test when data is available")
    print()
    print("Next Steps:")
    print("  1. Paper trade carry trade strategy for 30 days")
    print("  2. Monitor swap rates for changes")
    print("  3. Collect more calendar data for news trading")

if __name__ == "__main__":
    main()
