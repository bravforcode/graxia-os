#!/usr/bin/env python3
"""
Research Measurement Dashboard — All Strategies
"""
import csv
import json
from pathlib import Path

BASE = Path(__file__).parent.parent

def load_csv(path):
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))

def main():
    print("=" * 70)
    print("RESEARCH MEASUREMENT DASHBOARD")
    print("=" * 70)
    
    # Carry Trade
    print("\n--- CARRY TRADE ---")
    trades = load_csv(BASE / "logs" / "carry_trade" / "trades.csv")
    print("Trades logged: %d" % len(trades))
    if trades:
        open_trades = sum(1 for t in trades if t.get("status") == "OPEN")
        print("Open positions: %d" % open_trades)
    
    # Calendar
    print("\n--- ECONOMIC CALENDAR ---")
    cal_path = BASE / "data" / "news" / "fair_economy_calendar.json"
    if cal_path.exists():
        with open(cal_path) as f:
            cal = json.load(f)
        print("Events collected: %d" % len(cal))
    else:
        print("No calendar data yet")
    
    # Instructions
    print("\n--- HOW TO USE ---")
    print("1. Start carry_trade_runner.py (runs 24/7)")
    print("2. Run collect_calendar.py daily")
    print("3. Check this dashboard periodically")
    print("4. After 30 days, evaluate:")
    print("   - USDJPY LONG: Did swap income exceed price loss?")
    print("   - Win rate > 50%?")
    print("   - Account grew?")
    print()
    print("Files:")
    print("  carry_trade_runner.py — Main bot")
    print("  collect_calendar.py — Calendar collector")
    print("  logs/carry_trade/trades.csv — Trade log")
    print("  data/news/fair_economy_calendar.json — Calendar data")

if __name__ == "__main__":
    main()
