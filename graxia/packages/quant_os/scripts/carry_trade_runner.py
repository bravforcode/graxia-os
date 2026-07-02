#!/usr/bin/env python3
"""
Carry Trade Paper Runner — Automated demo trading.
Strategy: USDJPY LONG (earn swap), XAUUSD SHORT (earn swap)
Risk: 1% per trade, SL=2%, TP=6%, max 3 positions
"""
import csv
import json
import time
from datetime import datetime
from pathlib import Path

import MetaTrader5 as mt5

BASE = Path(__file__).parent.parent
LOG_DIR = BASE / "logs" / "carry_trade"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Config
STRATEGIES = [
    {"symbol": "USDJPY", "direction": "BUY", "sl_pct": 0.02, "tp_pct": 0.06, "lot": 0.01},
    {"symbol": "XAUUSD", "direction": "SELL", "sl_pct": 0.02, "tp_pct": 0.06, "lot": 0.01},
]
MAX_POSITIONS = 3
RISK_PER_TRADE = 0.01  # 1% of account
CHECK_INTERVAL = 3600  # Check every hour

TRADE_LOG = LOG_DIR / "trades.csv"
STATUS_FILE = LOG_DIR / "status.json"

def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg))

def ensure_mt5():
    if not mt5.initialize():
        raise RuntimeError("MT5 init failed: %s" % str(mt5.last_error()))
    info = mt5.account_info()
    if info and "demo" not in info.server.lower() and "practice" not in info.server.lower():
        raise RuntimeError("LIVE ACCOUNT: %s" % info.server)
    log("Connected: %s (Balance: $%.2f)" % (info.server, info.balance))
    return info

def log_trade(trade_data):
    file_exists = TRADE_LOG.exists()
    with open(TRADE_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=trade_data.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(trade_data)

def save_status(status):
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2, default=str)

def get_positions(mt5, symbol):
    positions = mt5.positions_get(symbol=symbol)
    return positions if positions else []

def calculate_position_size(balance, sl_pct, entry_price):
    """Calculate position size based on risk."""
    risk_amount = balance * RISK_PER_TRADE
    stop_distance = entry_price * sl_pct
    if stop_distance > 0:
        # For forex: 1 lot = 100,000 units, 1 pip = $10
        # For XAUUSD: 1 lot = 100 oz, 1 point = $1
        if "XAU" in str(entry_price):
            size = risk_amount / (stop_distance * 100)  # XAUUSD
        else:
            size = risk_amount / (stop_distance * 100000)  # Forex
        size = min(size, 1.0)  # Cap
        size = max(size, 0.01)  # Min
        return round(size, 2)
    return 0.01

def main():
    log("Starting Carry Trade Paper Runner...")
    info = ensure_mt5()
    
    cycle = 0
    while True:
        cycle += 1
        try:
            account_info = mt5.account_info()
            balance = account_info.balance
            
            # Check all positions
            total_positions = 0
            for strat in STRATEGIES:
                positions = get_positions(mt5, strat["symbol"])
                total_positions += len(positions)
            
            if total_positions >= MAX_POSITIONS:
                if cycle % 10 == 0:
                    log("Positions full (%d/%d)" % (total_positions, MAX_POSITIONS))
                time.sleep(CHECK_INTERVAL)
                continue
            
            # Check each strategy
            for strat in STRATEGIES:
                symbol = strat["symbol"]
                direction = strat["direction"]
                
                # Skip if already have position
                positions = get_positions(mt5, symbol)
                if positions:
                    continue
                
                # Get current price
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    continue
                
                price = tick.ask if direction == "BUY" else tick.bid
                
                # Calculate SL/TP
                sl_pct = strat["sl_pct"]
                tp_pct = strat["tp_pct"]
                
                if direction == "BUY":
                    sl = price * (1 - sl_pct)
                    tp = price * (1 + tp_pct)
                else:
                    sl = price * (1 + sl_pct)
                    tp = price * (1 - tp_pct)
                
                # Position sizing
                lot = calculate_position_size(balance, sl_pct, price)
                
                # Place order
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": lot,
                    "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
                    "price": price,
                    "sl": sl,
                    "tp": tp,
                    "deviation": 10,
                    "magic": 789012,
                    "comment": "CARRY_TRADE",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    side = "LONG" if direction == "BUY" else "SHORT"
                    log("OPEN %s %s @ %.2f SL=%.2f TP=%.2f lot=%.2f ticket=%d" % (
                        side, symbol, price, sl, tp, lot, result.order))
                    
                    trade = {
                        "open_time": datetime.utcnow().isoformat(),
                        "symbol": symbol,
                        "side": side,
                        "entry_price": price,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "lot": lot,
                        "ticket": result.order,
                        "status": "OPEN",
                    }
                    log_trade(trade)
                else:
                    err = result.comment if result else "no response"
                    log("ORDER FAILED %s: %s" % (symbol, err))
            
            # Save status
            save_status({
                "last_check": datetime.utcnow().isoformat(),
                "balance": balance,
                "total_positions": total_positions,
                "cycle": cycle,
            })
            
            if cycle % 10 == 0:
                log("Check #%d: Balance=$%.2f, Positions=%d" % (cycle, balance, total_positions))
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log("Stopped")
            break
        except Exception as e:
            log("Error: %s" % str(e))
            time.sleep(60)
    
    mt5.shutdown()
    log("Done")

if __name__ == "__main__":
    main()
