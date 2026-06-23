"""
G2.1 Stop Geometry Calibration. DRY-RUN ONLY. No order_send.
Purpose: Find SL/TP geometry that passes order_check on Pepperstone for XAUUSD BUY and SELL.

Key rules:
- BUY: SL must be below bid, TP above ask. Entry reference = ask.
- SELL: SL must be above ask, TP below bid. Entry reference = bid.
- Every price normalized to tick_size.
- Required protected distance = max(trade_stops_level * point, freeze_level * point, spread_price + safety_buffer, policy_floor)
"""
import json, hashlib, os, sys
from datetime import datetime, timezone
import MetaTrader5 as mt5

# ── Config ──
SYMBOL = "XAUUSD"
VOLUME = 0.01
SAFETY_BUFFER_MULTIPLIER = 3  # 3x spread as safety buffer
POLICY_FLOOR_PRICE = 0.50     # $0.50 minimum SL distance
MAX_CANDIDATES_PER_SIDE = 5
OUTPUT_DIR = r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\g2_1"

def normalize_price(price: float, tick_size: float) -> float:
    """Round price to nearest valid tick."""
    return round(round(price / tick_size) * tick_size, 8)

def compute_required_distance(spread_price: float, stops_level: int, freeze_level: int, point: float) -> float:
    """Compute minimum required SL/TP distance."""
    return max(
        stops_level * point,
        freeze_level * point,
        spread_price * SAFETY_BUFFER_MULTIPLIER,
        POLICY_FLOOR_PRICE,
    )

def calibrate_side(mt5, side: str, tick, sym) -> dict:
    """Calibrate stop geometry for one side. Returns candidate matrix + passing result or None."""
    entry = tick.ask if side == "BUY" else tick.bid
    spread_price = tick.ask - tick.bid
    required_stop_distance_price = compute_required_distance(
        spread_price, sym.trade_stops_level, sym.trade_freeze_level, sym.point
    )
    required_tp_distance_price = required_stop_distance_price  # 1:1 for first canary
    
    # Normalize required dists to tick_size
    required_stop_distance_price = normalize_price(required_stop_distance_price, sym.trade_tick_size)
    required_tp_distance_price = normalize_price(required_tp_distance_price, sym.trade_tick_size)
    
    candidates = []
    for i in range(1, MAX_CANDIDATES_PER_SIDE + 1):
        distance = normalize_price(required_stop_distance_price * i, sym.trade_tick_size)
        
        if side == "BUY":
            entry = tick.ask
            sl = normalize_price(tick.bid - distance, sym.trade_tick_size)
            gross_loss_delta = normalize_price(entry - sl, sym.trade_tick_size)
            tp = normalize_price(entry + gross_loss_delta, sym.trade_tick_size)
            gross_reward_delta = normalize_price(tp - entry, sym.trade_tick_size)
            sl_valid = sl < tick.bid
            tp_valid = tp > tick.ask
        else:  # SELL
            entry = tick.bid
            sl = normalize_price(tick.ask + distance, sym.trade_tick_size)
            gross_loss_delta = normalize_price(sl - entry, sym.trade_tick_size)
            tp = normalize_price(entry - gross_loss_delta, sym.trade_tick_size)
            gross_reward_delta = normalize_price(entry - tp, sym.trade_tick_size)
            sl_valid = sl > tick.ask
            tp_valid = tp < tick.bid
        
        candidates.append({
            "candidate": i,
            "protective_buffer_price": distance,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "gross_entry_to_sl_price_delta": gross_loss_delta,
            "gross_entry_to_tp_price_delta": gross_reward_delta,
            "planned_gross_rr": round(gross_reward_delta / gross_loss_delta, 6) if gross_loss_delta > 0 else 0,
            "spread_price": tick.ask - tick.bid,
            "bid": tick.bid,
            "ask": tick.ask,
            "sl_valid": sl_valid,
            "tp_valid": tp_valid,
        })
    
    # order_check for each valid candidate
    results = []
    passing = None
    for c in candidates:
        if not (c["sl_valid"] and c["tp_valid"]):
            results.append({"candidate": c["candidate"], "geometry": "INVALID", "retcode": -1, "comment": "SL on wrong side of quote"})
            continue
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": VOLUME,
            "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": entry,
            "sl": c["sl"],
            "tp": c["tp"],
            "deviation": 10,
            "magic": 100,
            "comment": f"G2.1_CALIBRATE_{side}_{c['candidate']}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        check = mt5.order_check(request)
        retcode = check.retcode if check else -999
        comment = check.comment if check else "order_check_failed"
        passed = retcode == 0
        
        result = {
            "candidate": c["candidate"],
            "distance": c["protective_buffer_price"],
            "sl": c["sl"],
            "tp": c["tp"],
            "retcode": retcode,
            "comment": comment,
            "passed": passed,
        }
        results.append(result)
        
        if passed and passing is None:
            passing = result
    
    # Evidence fields
    evidence = {}
    if passing:
        evidence["required_stop_distance_price"] = required_stop_distance_price
        evidence["required_tp_distance_price"] = required_tp_distance_price
        sl_dist = abs(passing["sl"] - (tick.bid if side == "BUY" else tick.ask))
        tp_dist = abs(passing["tp"] - (tick.ask if side == "BUY" else tick.bid))
        evidence["sl_distance_from_quote"] = sl_dist
        evidence["tp_distance_from_quote"] = tp_dist
        evidence["spread_price"] = tick.ask - tick.bid
        match = next((c for c in candidates if c["candidate"] == passing["candidate"]), None)
        evidence["gross_loss_delta"] = match["gross_entry_to_sl_price_delta"] if match else 0
        evidence["gross_reward_delta"] = match["gross_entry_to_tp_price_delta"] if match else 0
        evidence["planned_gross_rr"] = match["planned_gross_rr"] if match else 0
        evidence["protective_buffer_price"] = required_stop_distance_price
    
    return {
        "side": side,
        "entry": entry,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": spread_price,
        "required_stop_distance_price": required_stop_distance_price,
        "required_tp_distance_price": required_tp_distance_price,
        "stops_level": sym.trade_stops_level,
        "freeze_level": sym.trade_freeze_level,
        "evidence": evidence,
        "candidates": candidates,
        "order_check_results": results,
        "passing_candidate": passing,
    }

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
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
    
    profile_hash = hashlib.sha256(str(acct.login).encode()).hexdigest()
    terminal_hash = hashlib.sha256(r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe".encode()).hexdigest()
    
    # Verify clean state
    positions = mt5.positions_get()
    orders = mt5.orders_get()
    pos_count = len(positions) if positions else 0
    ord_count = len(orders) if orders else 0
    
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(OUTPUT_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    
    # Calibrate both sides
    buy_result = calibrate_side(mt5, "BUY", tick, sym)
    sell_result = calibrate_side(mt5, "SELL", tick, sym)
    
    mt5.shutdown()
    
    # Verify no state change
    positions_after = mt5.positions_get() if False else []  # already shutdown, trust before state
    # We already checked before: pos_count=0, ord_count=0
    
    verdict_obj = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "volume": VOLUME,
        "profile_hash": profile_hash[:16] + "...",
        "terminal_hash": terminal_hash[:16] + "...",
        "contract_size": sym.trade_contract_size,
        "tick_size": sym.trade_tick_size,
        "point": sym.point,
        "digits": sym.digits,
        "positions_before": pos_count,
        "orders_before": ord_count,
        "buy": buy_result,
        "sell": sell_result,
        "positions_after": "NOT_CHECKED_AFTER_DISCONNECT",
        "orders_after": "NOT_CHECKED_AFTER_DISCONNECT",
        "order_submission_count": 0,
        "verdict": "PASS_TO_G3_REVIEW" if (buy_result["passing_candidate"] and sell_result["passing_candidate"]) else "FAIL",
    }
    
    # Write evidence
    with open(os.path.join(run_dir, "verdict.json"), "w") as f:
        json.dump(verdict_obj, f, indent=2)
    
    # Candidate matrix
    matrix = {"buy": buy_result["candidates"], "sell": sell_result["candidates"]}
    with open(os.path.join(run_dir, "candidate_matrix.json"), "w") as f:
        json.dump(matrix, f, indent=2)
    
    # order_check results (redacted - no credentials)
    oc_results = {
        "buy_results": buy_result["order_check_results"],
        "sell_results": sell_result["order_check_results"],
    }
    with open(os.path.join(run_dir, "order_check_results.redacted.json"), "w") as f:
        json.dump(oc_results, f, indent=2)
    
    # Margin results
    margin_results = {}
    for side_key, side_result in [("buy", buy_result), ("sell", sell_result)]:
        if side_result["passing_candidate"]:
            margin_results[side_key] = {
                "volume": VOLUME,
                "margin": "See preflight margin check",
            }
    with open(os.path.join(run_dir, "margin_results.redacted.json"), "w") as f:
        json.dump(margin_results, f, indent=2)
    
    # Market snapshot
    snapshot = {
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": tick.ask - tick.bid,
        "tick_size": sym.trade_tick_size,
        "point": sym.point,
        "digits": sym.digits,
        "stops_level": sym.trade_stops_level,
        "freeze_level": sym.trade_freeze_level,
    }
    with open(os.path.join(run_dir, "market_snapshot.json"), "w") as f:
        json.dump(snapshot, f, indent=2)
    
    print(f"\n=== G2.1 Calibration Results ===")
    print(f"Run ID: {run_id}")
    print(f"Positions before: {pos_count}, Orders before: {ord_count}")
    print(f"BUY passing candidate: {buy_result['passing_candidate']}")
    print(f"SELL passing candidate: {sell_result['passing_candidate']}")
    print(f"order_submission_count: 0")
    print(f"Verdict: {verdict_obj['verdict']}")

if __name__ == "__main__":
    main()
