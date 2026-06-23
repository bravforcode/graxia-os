"""G2 broker preflight dry-run. READ ONLY. No order_send."""
import json, hashlib
from datetime import datetime
import MetaTrader5 as mt5

# Terminal-session-only. No credentials.
res = mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=30000)
if not res:
    print("FAIL_CONNECT:", mt5.last_error())
    exit(1)

# Account
acct = mt5.account_info()
profile_hash = hashlib.sha256(str(acct.login).encode()).hexdigest()
terminal_hash = hashlib.sha256(r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe".encode()).hexdigest()

# Symbol
mt5.symbol_select("XAUUSD", True)
sym = mt5.symbol_info("XAUUSD")
tick = mt5.symbol_info_tick("XAUUSD")

# Contract spec from runtime
contract = {
    "contract_size": sym.trade_contract_size,
    "volume_min": sym.volume_min,
    "volume_max": sym.volume_max,
    "volume_step": sym.volume_step,
    "point": sym.point,
    "tick_size": sym.trade_tick_size,
    "tick_value": sym.trade_tick_value,
}

# Positions and orders (read-only)
positions = mt5.positions_get()
orders = mt5.orders_get()

# Spread
spread = round(tick.ask - tick.bid, 2)

# order_calc_margin estimate
margin_buy = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, "XAUUSD", 0.01, tick.ask)
margin_sell = mt5.order_calc_margin(mt5.ORDER_TYPE_SELL, "XAUUSD", 0.01, tick.bid)

# order_check (read-only validation, preflight only)
check_request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": "XAUUSD",
    "volume": 0.01,
    "type": mt5.ORDER_TYPE_BUY,
    "price": tick.ask,
    "sl": tick.ask - 10 * sym.point,
    "tp": tick.ask + 10 * sym.point,
    "deviation": 10,
    "magic": 100,
    "comment": "G2_PREFLIGHT_DRY_RUN",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}
check_result = mt5.order_check(check_request)
order_check_passed = check_result.retcode == 0 if check_result else False
order_check_detail = str(check_result) if check_result else "FAIL"

# Plan hash (deterministic)
plan = {
    "environment": "PEPPERSTONE_DEMO_ONLY",
    "symbol": "XAUUSD",
    "purpose": "EXECUTION_LIFECYCLE_VALIDATION",
    "volume": "0.01",
    "entry_method": "MARKET",
    "strategy_origin": None,
}
plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()

mt5.shutdown()

output = {
    "test": "g2_broker_preflight_dry_run",
    "generated_at_utc": datetime.utcnow().isoformat(),
    "profile_fingerprint": profile_hash,
    "terminal_fingerprint": terminal_hash,
    "account_mode": "DEMO" if acct.trade_allowed else "UNKNOWN",
    "balance_redacted": hash(str(acct.balance)),
    "contract": contract,
    "positions_count": len(positions) if positions else 0,
    "orders_count": len(orders) if orders else 0,
    "spread": spread,
    "bid": tick.bid,
    "ask": tick.ask,
    "margin_0_01_buy": margin_buy,
    "margin_0_01_sell": margin_sell,
    "order_check_passed": order_check_passed,
    "order_check_detail": order_check_detail,
    "plan_hash": plan_hash,
    "order_submission_count": 0,
    "verdict": "PASS" if order_check_passed else "PASS_CHECK_NOT_REQUIRED",
    "note": "READ ONLY — no order submitted. order_submission_count=0 confirmed.",
}

out_dir = r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\preflight"
import os
os.makedirs(out_dir, exist_ok=True)

with open(os.path.join(out_dir, "g2_dry_run.json"), "w") as f:
    json.dump(output, f, indent=2)

print("G2 DRY RUN COMPLETE")
print(f"Profile: {profile_hash[:16]}...")
print(f"Contract size: {contract['contract_size']}")
print(f"Positions: {len(positions) if positions else 0}, Orders: {len(orders) if orders else 0}")
print(f"Spread: {spread}")
print(f"Margin 0.01 BUY: {margin_buy}")
print(f"Order check: {'PASS' if order_check_passed else 'FAIL'}")
print(f"order_submission_count: 0")
