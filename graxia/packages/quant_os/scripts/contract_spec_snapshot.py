"""Capture ContractSpec from Pepperstone runtime and cross-check with MT5 calculators."""
import json, hashlib
from datetime import datetime
import MetaTrader5 as mt5

# Terminal-session-only auth
res = mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=30000)
if not res:
    print("FAIL:", mt5.last_error())
    exit(1)

profile_hash = hashlib.sha256(str(mt5.account_info().login).encode()).hexdigest()
account_mode = "DEMO"

symbols = ["XAUUSD", "EURUSD"]
results = {}

for sym in symbols:
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    
    contract_spec = {
        "symbol": sym,
        "trade_contract_size": info.trade_contract_size,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
        "point": info.point,
        "trade_tick_size": info.trade_tick_size,
        "trade_tick_value": info.trade_tick_value,
        "currency_profit": info.currency_profit,
        "currency_margin": info.currency_margin,
        "trade_stops_level": info.trade_stops_level,
        "trade_freeze_level": info.trade_freeze_level,
        "fetched_at_utc": datetime.utcnow().isoformat(),
    }
    
    # Compute hash
    fields = f"{sym}:{info.trade_contract_size}:{info.volume_min}:{info.volume_max}:{info.volume_step}:{info.point}"
    contract_spec["contract_hash"] = hashlib.sha256(fields.encode()).hexdigest()
    contract_spec["profile_hash"] = profile_hash
    
    # Cross-check with order_calc_profit for different volumes and directions
    cross_check = {}
    for volume in [0.01, 0.10, 1.0]:
        for direction in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
            price = tick.ask if direction == mt5.ORDER_TYPE_BUY else tick.bid
            sl = price - 10 * info.point if direction == mt5.ORDER_TYPE_BUY else price + 10 * info.point
            tp = price + 10 * info.point if direction == mt5.ORDER_TYPE_BUY else price - 10 * info.point
            
            profit = mt5.order_calc_profit(direction, sym, volume, price, tp)
            loss = mt5.order_calc_profit(direction, sym, volume, price, sl)
            margin = mt5.order_calc_margin(direction, sym, volume, price)
            
            key = f"{volume}_lot_{'BUY' if direction==mt5.ORDER_TYPE_BUY else 'SELL'}"
            cross_check[key] = {
                "profit_estimate": profit,
                "loss_estimate": loss,
                "margin_estimate": margin,
                "entry": price,
                "sl_distance_points": 10,
            }
    
    contract_spec["cross_check"] = cross_check
    results[sym] = contract_spec

mt5.shutdown()

# Metadata
output = {
    "generated_at_utc": datetime.utcnow().isoformat(),
    "terminal_path_fingerprint": hashlib.sha256(r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe".encode()).hexdigest(),
    "profile_fingerprint": profile_hash,
    "account_mode": account_mode,
    "contracts": results,
}

with open(r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\contract_spec\XAUUSD_contract_snapshot.json", "w") as f:
    json.dump(output, f, indent=2)

print("ContractSpec snapshot saved.")
print(f"XAUUSD contract_size: {results['XAUUSD']['trade_contract_size']}")
print(f"EURUSD contract_size: {results['EURUSD']['trade_contract_size']}")
print(f"XAUUSD 0.01 BUY P&L: {results['XAUUSD']['cross_check']['0.01_lot_BUY']['profit_estimate']}")
print(f"EURUSD 0.01 BUY P&L: {results['EURUSD']['cross_check']['0.01_lot_BUY']['profit_estimate']}")
