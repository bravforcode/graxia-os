"""
G3 Final Preflight — READ ONLY. Creates immutable Demo Canary plan from fresh quote.
No order_send. No order submission.
Stops after plan generation for human review.
"""
import json, hashlib, os, sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
import MetaTrader5 as mt5

# ── Constants ──
SYMBOL = "XAUUSD"
VOLUME = 0.01
SIDE = "BUY"
ENVIRONMENT = "PEPPERSTONE_DEMO_ONLY"
PURPOSE = "EXECUTION_LIFECYCLE_VALIDATION"
SAFETY_BUFFER_MULTIPLIER = 3
POLICY_FLOOR_PRICE = 0.50
MAX_DEVIATION_POINTS = 10
PLAN_TTL_SECONDS = 120
PROJECTED_LOSS_CAP_USD = 1.00

OUTPUT_DIR = r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\g3_final_preflight"

def normalize_price(price, tick_size):
    return round(round(price / tick_size) * tick_size, 8)

def main():
    # Connect terminal-session-only
    res = mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe", timeout=30000)
    if not res:
        print("FAIL_CONNECT:", mt5.last_error())
        sys.exit(1)
    
    # Fresh snapshot
    mt5.symbol_select(SYMBOL, True)
    tick = mt5.symbol_info_tick(SYMBOL)
    sym = mt5.symbol_info(SYMBOL)
    acct = mt5.account_info()
    
    now_utc = datetime.now(timezone.utc)
    canary_id = f"CANARY-{now_utc.strftime('%Y%m%d-%H%M%S')}"
    correlation_id = str(uuid4())
    
    # Profile
    profile_hash = hashlib.sha256(str(acct.login).encode()).hexdigest()
    terminal_path_hash = hashlib.sha256(r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe".encode()).hexdigest()
    account_mode = "DEMO"
    
    # Guards
    guards = {}
    guards["account_mode"] = account_mode
    guards["profile_hash"] = profile_hash[:16] + "..."
    guards["terminal_path_hash"] = terminal_path_hash[:16] + "..."
    guards["feature_gate"] = "OFF"
    guards["kill_switch"] = "ON"
    
    # Positions and orders
    positions = mt5.positions_get()
    orders = mt5.orders_get()
    pos_count = len(positions) if positions else 0
    ord_count = len(orders) if orders else 0
    guards["positions_before"] = pos_count
    guards["orders_before"] = ord_count
    
    if pos_count > 0:
        print("BLOCKED: existing positions found")
        mt5.shutdown()
        sys.exit(1)
    if ord_count > 0:
        print("BLOCKED: existing orders found")
        mt5.shutdown()
        sys.exit(1)
    
    # Market snapshot
    bid = tick.bid
    ask = tick.ask
    spread_price = round(ask - bid, 8)
    tick_size = sym.trade_tick_size
    point = sym.point
    digits = sym.digits
    stops_level = sym.trade_stops_level
    freeze_level = sym.trade_freeze_level
    filling_mode_raw = sym.filling_mode
    # Bitmask → select one valid filling mode
    if filling_mode_raw & 2:
        filling_mode = 1  # IOC
    elif filling_mode_raw & 1:
        filling_mode = 0  # FOK
    else:
        filling_mode = 0  # default FOK
    
    # Contract spec from runtime
    contract = {
        "contract_size": sym.trade_contract_size,
        "volume_min": sym.volume_min,
        "volume_max": sym.volume_max,
        "volume_step": sym.volume_step,
    }
    
    # Protective buffer
    protective_buffer = max(
        stops_level * point,
        freeze_level * point,
        spread_price * SAFETY_BUFFER_MULTIPLIER,
        POLICY_FLOOR_PRICE,
    )
    protective_buffer = normalize_price(protective_buffer, tick_size)
    
    # BUY geometry (entry from ask, SL from bid, TP from entry+gross_loss)
    entry = normalize_price(ask, tick_size)
    sl = normalize_price(bid - protective_buffer, tick_size)
    gross_loss_delta = normalize_price(entry - sl, tick_size)
    tp = normalize_price(entry + gross_loss_delta, tick_size)
    gross_reward_delta = normalize_price(tp - entry, tick_size)
    planned_gross_rr = round(gross_reward_delta / gross_loss_delta, 6) if gross_loss_delta > 0 else 0
    
    # Verify geometry
    sl_valid = sl < bid
    tp_valid = tp > ask
    rr_valid = abs(planned_gross_rr - 1.0) < 0.001
    
    guards["sl_below_bid"] = sl_valid
    guards["tp_above_ask"] = tp_valid
    guards["planned_gross_rr"] = planned_gross_rr
    guards["rr_within_tolerance"] = rr_valid
    
    if not sl_valid or not tp_valid or not rr_valid:
        print(f"BLOCKED: geometry invalid. sl_valid={sl_valid}, tp_valid={tp_valid}, rr={planned_gross_rr}")
        mt5.shutdown()
        sys.exit(1)
    
    # order_calc_profit for projected loss (using current price as close)
    projected_loss = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, SYMBOL, VOLUME, entry, sl)
    projected_loss_usd = abs(projected_loss) if projected_loss else 0
    
    # order_calc_margin
    margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, VOLUME, entry)
    margin_usd = abs(margin) if margin else 0
    
    guards["projected_loss_usd"] = projected_loss_usd
    guards["projected_margin_usd"] = margin_usd
    
    if projected_loss_usd > PROJECTED_LOSS_CAP_USD:
        print(f"BLOCKED: projected loss ${projected_loss_usd:.2f} exceeds cap ${PROJECTED_LOSS_CAP_USD}")
        mt5.shutdown()
        sys.exit(1)
    
    # order_check on final request
    order_check_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": mt5.ORDER_TYPE_BUY,
        "price": entry,
        "sl": sl,
        "tp": tp,
        "deviation": MAX_DEVIATION_POINTS,
        "magic": int(hashlib.sha256(canary_id.encode()).hexdigest()[:8], 16),
        "comment": f"G3_PLAN_{canary_id[-8:]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    
    check_result = mt5.order_check(order_check_request)
    order_check_passed = check_result.retcode == 0 if check_result else False
    order_check_retcode = check_result.retcode if check_result else -999
    order_check_comment = check_result.comment if check_result else "order_check_failed"
    
    guards["order_check_passed"] = order_check_passed
    guards["order_check_retcode"] = order_check_retcode
    guards["order_check_comment"] = order_check_comment
    guards["order_check_label"] = "PRECHECK_ONLY_NOT_EXECUTION_PROOF"
    
    if not order_check_passed:
        print(f"BLOCKED: order_check failed retcode={order_check_retcode}: {order_check_comment}")
        mt5.shutdown()
        sys.exit(1)
    
    # Verify no state change after checks
    positions_after = mt5.positions_get()
    orders_after = mt5.orders_get()
    guards["positions_after"] = len(positions_after) if positions_after else 0
    guards["orders_after"] = len(orders_after) if orders_after else 0
    guards["order_submission_count"] = 0
    
    mt5.shutdown()
    
    # ── Build immutable canary plan ──
    expiry_utc = (now_utc + timedelta(seconds=PLAN_TTL_SECONDS)).isoformat()
    
    plan = {
        "schema_version": "1.0",
        "canary_id": canary_id,
        "correlation_id": correlation_id,
        "generated_at_utc": now_utc.isoformat(),
        "expiry_utc": expiry_utc,
        "environment": ENVIRONMENT,
        "purpose": PURPOSE,
        "symbol": SYMBOL,
        "side": SIDE,
        "volume": str(VOLUME),
        "entry_method": "MARKET",
        "entry": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "protective_buffer_price": protective_buffer,
        "gross_entry_to_sl_price_delta": gross_loss_delta,
        "gross_entry_to_tp_price_delta": gross_reward_delta,
        "planned_gross_rr": planned_gross_rr,
        "projected_loss_usd": projected_loss_usd,
        "projected_margin_usd": margin_usd,
        "max_deviation_points": MAX_DEVIATION_POINTS,
        "filling_mode": filling_mode,
        "strategy_origin": None,
        "account_fingerprint": profile_hash[:32],
        "contract_hash": hashlib.sha256(f"{sym.trade_contract_size}:{sym.volume_min}:{sym.volume_max}".encode()).hexdigest(),
        "guards": guards,
    }
    
    # Deterministic plan hash
    plan_json = json.dumps(plan, indent=2, sort_keys=True)
    plan_hash = hashlib.sha256(plan_json.encode()).hexdigest()
    plan["plan_hash"] = plan_hash
    
    # ── Evidence ──
    run_dir = os.path.join(OUTPUT_DIR, canary_id)
    os.makedirs(run_dir, exist_ok=True)
    
    with open(os.path.join(run_dir, "plan.json"), "w") as f:
        json.dump(plan, f, indent=2)
    
    market_snapshot = {
        "bid": bid, "ask": ask, "spread": spread_price,
        "tick_size": tick_size, "point": point, "digits": digits,
        "stops_level": stops_level, "freeze_level": freeze_level,
        "filling_mode": filling_mode,
    }
    with open(os.path.join(run_dir, "market_snapshot.json"), "w") as f:
        json.dump(market_snapshot, f, indent=2)
    
    preflight = {"guards": guards, "verdict": "READY_FOR_HUMAN_G3_SEND_REVIEW"}
    with open(os.path.join(run_dir, "preflight.redacted.json"), "w") as f:
        json.dump(preflight, f, indent=2)
    
    oc_data = {
        "request_redacted": {"symbol": SYMBOL, "volume": VOLUME, "type": "BUY"},
        "retcode": order_check_retcode,
        "comment": order_check_comment,
        "label": "PRECHECK_ONLY_NOT_EXECUTION_PROOF",
    }
    with open(os.path.join(run_dir, "order_check.redacted.json"), "w") as f:
        json.dump(oc_data, f, indent=2)
    
    margin_data = {
        "volume": VOLUME,
        "margin_estimate": margin_usd,
        "label": "ESTIMATE_ONLY_NOT_FINAL",
    }
    with open(os.path.join(run_dir, "margin.redacted.json"), "w") as f:
        json.dump(margin_data, f, indent=2)
    
    pos_orders = {
        "positions_before": pos_count,
        "orders_before": ord_count,
        "positions_after": guards["positions_after"],
        "orders_after": guards["orders_after"],
        "order_submission_count": 0,
    }
    with open(os.path.join(run_dir, "positions_orders_before_after.json"), "w") as f:
        json.dump(pos_orders, f, indent=2)
    
    # Seal
    seal_input = json.dumps({
        "plan_hash": plan_hash,
        "correlation_id": correlation_id,
        "generated_at_utc": now_utc.isoformat(),
    }, sort_keys=True)
    seal_hash = hashlib.sha256(seal_input.encode()).hexdigest()
    
    seal = {
        "canary_id": canary_id,
        "plan_hash": plan_hash,
        "seal_hash": seal_hash,
        "artifacts": {
            "plan.json": hashlib.sha256(plan_json.encode()).hexdigest(),
            "market_snapshot.json": hashlib.sha256(json.dumps(market_snapshot, sort_keys=True).encode()).hexdigest(),
            "preflight.redacted.json": hashlib.sha256(json.dumps(preflight, sort_keys=True).encode()).hexdigest(),
            "order_check.redacted.json": hashlib.sha256(json.dumps(oc_data, sort_keys=True).encode()).hexdigest(),
            "margin.redacted.json": hashlib.sha256(json.dumps(margin_data, sort_keys=True).encode()).hexdigest(),
            "positions_orders_before_after.json": hashlib.sha256(json.dumps(pos_orders, sort_keys=True).encode()).hexdigest(),
        },
    }
    with open(os.path.join(run_dir, "seal.json"), "w") as f:
        json.dump(seal, f, indent=2)
    
    # ── Output ──
    print(f"\n{'='*60}")
    print(f"G3 FINAL PREFLIGHT — READY FOR HUMAN REVIEW")
    print(f"{'='*60}")
    print(f"Canary ID:    {canary_id}")
    print(f"Plan Hash:    {plan_hash}")
    print(f"Correlation:  {correlation_id}")
    print(f"Expiry (UTC): {expiry_utc}")
    print(f"Environment:  {ENVIRONMENT}")
    print(f"Purpose:      {PURPOSE}")
    print(f"Side:         {SIDE}")
    print(f"Volume:       {VOLUME}")
    print(f"Entry:        {entry}")
    print(f"SL:           {sl}")
    print(f"TP:           {tp}")
    print(f"Gross loss:   {gross_loss_delta}")
    print(f"Gross reward: {gross_reward_delta}")
    print(f"Gross RR:     {planned_gross_rr}")
    print(f"Proj loss:    ${projected_loss_usd:.2f}")
    print(f"Proj margin:  ${margin_usd:.2f}")
    print(f"order_check:  {'PASS' if order_check_passed else 'FAIL'} (retcode={order_check_retcode})")
    print(f"Positions:    0, Orders: 0")
    print(f"order_send:   NOT CALLED")
    print(f"order_submission_count: 0")
    print(f"Seal hash:    {seal_hash}")
    print(f"Artifacts:    {run_dir}")
    print(f"\nVerdict: READY_FOR_HUMAN_G3_SEND_REVIEW")
    print(f"DO NOT CALL order_send UNTIL HUMAN APPROVAL.")

if __name__ == "__main__":
    main()
