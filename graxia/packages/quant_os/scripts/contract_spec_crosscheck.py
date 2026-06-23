"""Broker cross-check: ContractSpec vs MT5 calculators. Verifies risk/P&L/margin."""
import json, hashlib
from datetime import datetime
import MetaTrader5 as mt5

res = mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=30000)
if not res:
    print("FAIL:", mt5.last_error())
    exit(1)

profile_hash = hashlib.sha256(str(mt5.account_info().login).encode()).hexdigest()
account_currency = mt5.account_info().currency

# Test configurations
tests = []

# XAUUSD: contract_size=100, point=0.01
# CORRECT understanding: price 2000→1990 = $10 price delta = 1000 MT5 points
# 1 lot risk = 1.0 × 100 × 10.0 = $1,000
# 0.01 lot risk = 0.01 × 100 × 10.0 = $10

for sym, contract_size, point in [("XAUUSD", 100, 0.01), ("EURUSD", 100000, 0.00001)]:
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    info = mt5.symbol_info(sym)
    
    for lots in [0.01, 0.10, 1.0]:
        for direction in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
            entry = tick.ask if direction == mt5.ORDER_TYPE_BUY else tick.bid
            
            # 1000 points SL (for XAUUSD this = $10 price delta)
            mt5_points = 1000
            price_delta = mt5_points * point
            
            if direction == mt5.ORDER_TYPE_BUY:
                sl = entry - price_delta
                tp = entry + price_delta
            else:
                sl = entry + price_delta
                tp = entry - price_delta
            
            profit = mt5.order_calc_profit(direction, sym, lots, entry, tp)
            loss = mt5.order_calc_profit(direction, sym, lots, entry, sl)
            margin = mt5.order_calc_margin(direction, sym, lots, entry)
            
            # Manual calculation
            expected_risk = lots * contract_size * price_delta
            
            test = {
                "symbol": sym,
                "lots": lots,
                "direction": "BUY" if direction == mt5.ORDER_TYPE_BUY else "SELL",
                "entry": entry,
                "mt5_points": mt5_points,
                "price_delta": price_delta,
                "sl_distance_points": mt5_points,
                "sl": sl,
                "tp": tp,
                "broker_profit": profit,
                "broker_loss": loss,
                "broker_margin": margin,
                "manual_risk": expected_risk,
                "formula": f"{lots} × {contract_size} × {price_delta} = {expected_risk}",
                "profit_match": abs(profit - expected_risk) < 0.01 if profit else False,
                "loss_match": abs(loss + expected_risk) < 0.01 if loss else False,
            }
            tests.append(test)

mt5.shutdown()

output = {
    "generated_at_utc": datetime.utcnow().isoformat(),
    "profile_hash": profile_hash,
    "account_currency": account_currency,
    "cross_checks": tests,
    "summary": {
        "total_checks": len(tests),
        "profit_matches": sum(1 for t in tests if t.get("profit_match")),
        "loss_matches": sum(1 for t in tests if t.get("loss_match")),
    }
}

with open(r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\contract_spec\broker_crosscheck_results.json", "w") as f:
    json.dump(output, f, indent=2)

print(json.dumps(output["summary"], indent=2))
print(f"\nSample XAUUSD 0.01 lot: risk=${tests[0]['manual_risk']:.2f}, broker_loss=${tests[0]['broker_loss']:.2f}")
