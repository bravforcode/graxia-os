#!/usr/bin/env python3
"""
Research: Carry Trade + News Trading approaches.
Uses real swap rates from MT5 and economic calendar data.
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

def load_calendar():
    """Load economic calendar from FairEconomy API."""
    try:
        with open(BASE / "data" / "news" / "forexfactory_calendar.json") as f:
            data = json.load(f)
        # Filter for high-impact events
        high_impact = [e for e in data if e.get("impact") == "High"]
        return high_impact
    except:
        return []

def test_carry_trade(symbol, tf="H1"):
    """
    Carry Trade: Hold position to earn swap.
    Long high-yield currency, short low-yield currency.
    """
    swap = SWAP_RATES.get(symbol)
    if not swap:
        return None
    
    # Load data
    df = pd.read_csv(BASE / "data" / f"{symbol}_{tf}.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    
    close = df["close"].values.astype(float)
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    
    # Determine direction based on swap
    # Long if swap_long > 0 (earn interest), Short if swap_short > 0
    if swap["long"] > swap["short"]:
        direction = 1  # Long
        daily_swap = swap["long"]
    else:
        direction = -1  # Short
        daily_swap = swap["short"]
    
    # Calculate returns
    trade_returns = direction * returns
    
    # Calculate swap income (per 0.01 lot)
    # swap is per lot per day, so per 0.01 lot = swap / 100
    swap_per_day = daily_swap / 100
    
    # Total P&L = price returns + swap income
    days_held = len(close) / 24  # H1 bars to days
    total_swap = swap_per_day * days_held
    total_price_pnl = trade_returns.sum() * close.mean() * 0.01  # 0.01 lot
    
    net = total_price_pnl + total_swap
    
    # Sharpe
    if trade_returns.std() > 0:
        sharpe = trade_returns.mean() / trade_returns.std() * np.sqrt(min(len(trade_returns), 252))
    else:
        sharpe = 0
    
    return {
        "symbol": symbol,
        "direction": "LONG" if direction == 1 else "SHORT",
        "swap_per_day": swap_per_day,
        "days_held": days_held,
        "total_swap": total_swap,
        "total_price_pnl": total_price_pnl,
        "net": net,
        "sharpe": sharpe,
    }

def test_news_trading(symbol, tf="H1"):
    """
    News Trading: Trade around high-impact economic events.
    Buy before positive news, sell before negative news.
    """
    # Load calendar
    calendar = load_calendar()
    if not calendar:
        return {"trades": 0, "net": 0, "note": "No calendar data"}
    
    # Load price data
    df = pd.read_csv(BASE / "data" / f"{symbol}_{tf}.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    
    close = df["close"].values.astype(float)
    
    # Parse calendar events for this symbol
    currency = symbol[:3]  # EUR, GBP, USD
    events = [e for e in calendar if e.get("currency") == currency or 
              (currency == "USD" and e.get("currency") == "USD")]
    
    if not events:
        return {"trades": 0, "net": 0, "note": "No events for this symbol"}
    
    # For each event, check price movement before/after
    trades = []
    for event in events:
        try:
            event_time = pd.to_datetime(event["date"])
            event_time_utc = event_time.tz_convert("UTC") if event_time.tzinfo else event_time
            
            # Find bars around event
            time_diff = abs(df.index - event_time_utc)
            event_idx = time_diff.argmin()
            
            if event_idx < 10 or event_idx >= len(close) - 10:
                continue
            
            # Price before event (10 bars before)
            pre_price = close[event_idx - 10:event_idx].mean()
            # Price after event (10 bars after)
            post_price = close[event_idx:event_idx + 10].mean()
            
            # Direction based on forecast vs previous
            forecast = event.get("forecast", "")
            previous = event.get("previous", "")
            
            if forecast and previous:
                try:
                    forecast_val = float(forecast.replace("%", "").replace("K", "000"))
                    previous_val = float(previous.replace("%", "").replace("K", "000"))
                    
                    # Positive surprise = buy, negative = sell
                    if forecast_val > previous_val:
                        direction = 1  # Buy
                    else:
                        direction = -1  # Sell
                    
                    pnl = direction * (post_price - pre_price) / pre_price
                    trades.append({
                        "event": event.get("title", ""),
                        "impact": event.get("impact", ""),
                        "direction": "BUY" if direction == 1 else "SELL",
                        "pnl_pct": pnl,
                        "pnl_usd": pnl * 100,  # 0.01 lot
                    })
                except:
                    pass
        except:
            continue
    
    if not trades:
        return {"trades": 0, "net": 0, "note": "No parseable events"}
    
    trades_df = pd.DataFrame(trades)
    wins = (trades_df["pnl_usd"] > 0).sum()
    total = len(trades_df)
    
    return {
        "trades": total,
        "wins": wins,
        "win_rate": wins / total if total > 0 else 0,
        "net": trades_df["pnl_usd"].sum(),
        "avg_pnl": trades_df["pnl_usd"].mean(),
    }

def main():
    print("=" * 80)
    print("RESEARCH: Carry Trade + News Trading")
    print("=" * 80)
    
    # Test carry trade
    print("\n--- CARRY TRADE ---")
    print("Strategy: Hold position to earn swap income")
    print()
    
    for symbol in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        result = test_carry_trade(symbol, "H1")
        if result:
            print("%s: %s, swap/day=$%.2f, days=%.0f, swap=$%.2f, price=$%.2f, net=$%.2f, sharpe=%.1f" % (
                symbol, result["direction"], result["swap_per_day"],
                result["days_held"], result["total_swap"],
                result["total_price_pnl"], result["net"], result["sharpe"]))
    
    # Test news trading
    print("\n--- NEWS TRADING ---")
    print("Strategy: Trade around high-impact economic events")
    print()
    
    for symbol in ["EURUSD", "GBPUSD", "USDJPY"]:
        result = test_news_trading(symbol, "H1")
        print("%s: %d trades, WR=%.1f%%, net=$%.2f, avg=$%.2f (%s)" % (
            symbol, result["trades"], result.get("win_rate", 0) * 100,
            result["net"], result.get("avg_pnl", 0), result.get("note", "")))
    
    # Summary
    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    print("Carry Trade: Earn swap income by holding positions")
    print("  - Positive swap = earn interest")
    print("  - Negative swap = pay interest")
    print("  - Price risk still applies")
    print()
    print("News Trading: Trade around economic events")
    print("  - High-impact events cause volatility")
    print("  - Need to predict direction correctly")
    print("  - Cost of slippage during news is high")

if __name__ == "__main__":
    main()
