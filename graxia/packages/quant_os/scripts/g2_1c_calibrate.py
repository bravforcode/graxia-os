"""
G2.1c Stop Geometry Calibration. DRY-RUN ONLY. No order_send.
EXECUTION_QUOTE_SNAPSHOT: primary= symbol_info_tick() for geometry, canonical= copy_ticks_range() for audit only.
Divergences recorded as diagnostic, NOT blocking. Buffer ladder uses native prices.
Canonical freshness: 0 <= age_ms <= max_age (fail-closed, no abs).
"""
import json, os, sys
from datetime import datetime, timedelta, UTC
import MetaTrader5 as mt5

SYMBOL = "XAUUSD"
VOLUME = 0.01
SAFETY_BUFFER_MULTIPLIER = 3
POLICY_FLOOR_PRICE = 0.50
MAX_CANDIDATES_PER_SIDE = 5
MAX_CANONICAL_AGE_MS = 5000
OUTPUT_DIR = r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\g2_1c"
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

def normalize_price(price: float, tick_size: float) -> float:
    return round(round(price / tick_size) * tick_size, 8)

def sanitize_for_json(obj):
    """Recursively convert numpy int64/float64 to native Python types."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(i) for i in obj]
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
    except ImportError:
        pass
    if hasattr(obj, 'item'):
        return obj.item()
    return obj

def compute_required_distance(spread_price, stops_level, freeze_level, point):
    return max(
        stops_level * point,
        freeze_level * point,
        spread_price * SAFETY_BUFFER_MULTIPLIER,
        POLICY_FLOOR_PRICE,
    )

def fetch_canonical_tick(symbol, max_age_ms):
    """Fetch canonical tick from copy_ticks_range. Returns (tick_dict, age_ms, error)."""
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=10)
    tcks = mt5.copy_ticks_range(symbol, window_start, now, mt5.COPY_TICKS_INFO)
    if tcks is None or len(tcks) == 0:
        return None, None, "copy_ticks_range returned no ticks"
    last = tcks[-1]
    c_time = int(last["time"])
    c_time_dt = datetime.fromtimestamp(c_time, tz=UTC)
    age_ms = (now - c_time_dt).total_seconds() * 1000
    tick = {"bid": float(last["bid"]), "ask": float(last["ask"]),
            "time": last["time"], "time_msc": last["time_msc"], "flags": last["flags"]}
    return tick, age_ms, None

def calibrate_side(side, native_tick, canonical_tick, canonical_age_ms, canonical_error, sym):
    """Calibrate one side. Geometry from native tick. Canonical is audit-only."""
    entry = native_tick.ask if side == "BUY" else native_tick.bid
    spread_price = native_tick.ask - native_tick.bid
    required_stop_distance = compute_required_distance(
        spread_price, sym.trade_stops_level, sym.trade_freeze_level, sym.point
    )
    required_stop_distance = normalize_price(required_stop_distance, sym.trade_tick_size)
    required_tp_distance = normalize_price(required_stop_distance, sym.trade_tick_size)

    candidates = []
    for i in range(1, MAX_CANDIDATES_PER_SIDE + 1):
        distance = normalize_price(required_stop_distance * i, sym.trade_tick_size)

        if side == "BUY":
            entry = native_tick.ask
            sl = normalize_price(native_tick.bid - distance, sym.trade_tick_size)
            gross_loss = normalize_price(entry - sl, sym.trade_tick_size)
            tp = normalize_price(entry + gross_loss, sym.trade_tick_size)
            gross_reward = normalize_price(tp - entry, sym.trade_tick_size)
            sl_valid = sl < native_tick.bid
            tp_valid = tp > native_tick.ask
        else:
            entry = native_tick.bid
            sl = normalize_price(native_tick.ask + distance, sym.trade_tick_size)
            gross_loss = normalize_price(sl - entry, sym.trade_tick_size)
            tp = normalize_price(entry - gross_loss, sym.trade_tick_size)
            gross_reward = normalize_price(entry - tp, sym.trade_tick_size)
            sl_valid = sl > native_tick.ask
            tp_valid = tp < native_tick.bid

        candidates.append({
            "candidate": i,
            "protective_buffer_price": distance,
            "entry": entry, "sl": sl, "tp": tp,
            "gross_entry_to_sl_price_delta": gross_loss,
            "gross_entry_to_tp_price_delta": gross_reward,
            "planned_gross_rr": round(gross_reward / gross_loss, 6) if gross_loss > 0 else 0,
            "spread_price": spread_price,
            "bid": native_tick.bid, "ask": native_tick.ask,
            "sl_valid": sl_valid, "tp_valid": tp_valid,
        })

    results = []
    passing = None
    for c in candidates:
        if not (c["sl_valid"] and c["tp_valid"]):
            results.append({"candidate": c["candidate"], "geometry": "INVALID", "retcode": -1,
                            "comment": "SL on wrong side of quote"})
            continue

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": VOLUME,
            "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": c["entry"],
            "sl": c["sl"],
            "tp": c["tp"],
            "deviation": 10,
            "magic": 100,
            "comment": f"G2.1c_CALIBRATE_{side}_{c['candidate']}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        check = mt5.order_check(request)
        retcode = check.retcode if check else -999
        comment = check.comment if check else "order_check_failed"
        passed = retcode == 0

        result = {"candidate": c["candidate"], "distance": c["protective_buffer_price"],
                  "sl": c["sl"], "tp": c["tp"], "retcode": retcode, "comment": comment, "passed": passed}
        results.append(result)
        if passed and passing is None:
            passing = result

    divergences = {}
    if canonical_tick:
        bid_div = abs(native_tick.bid - canonical_tick["bid"])
        ask_div = abs(native_tick.ask - canonical_tick["ask"])
        divergences = {"bid_divergence": bid_div, "ask_divergence": ask_div,
                       "canonical_age_ms": canonical_age_ms, "canonical_tick": canonical_tick}
    else:
        divergences = {"bid_divergence": None, "ask_divergence": None,
                       "canonical_age_ms": None, "canonical_error": canonical_error}

    evidence = {}
    if passing:
        evidence["required_stop_distance_price"] = required_stop_distance
        evidence["required_tp_distance_price"] = required_tp_distance
        evidence["spread_price"] = spread_price
        match = next((c for c in candidates if c["candidate"] == passing["candidate"]), None)
        evidence["gross_loss_delta"] = match["gross_entry_to_sl_price_delta"] if match else 0
        evidence["gross_reward_delta"] = match["gross_entry_to_tp_price_delta"] if match else 0
        evidence["planned_gross_rr"] = match["planned_gross_rr"] if match else 0
        evidence["protective_buffer_price"] = required_stop_distance

    return {
        "side": side, "entry": entry, "bid": native_tick.bid, "ask": native_tick.ask,
        "spread": spread_price, "required_stop_distance_price": required_stop_distance,
        "required_tp_distance_price": required_tp_distance,
        "stops_level": sym.trade_stops_level, "freeze_level": sym.trade_freeze_level,
        "evidence": evidence, "candidates": candidates, "order_check_results": results,
        "passing_candidate": passing, "quote_divergences": divergences,
    }

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not mt5.initialize(path=TERMINAL_PATH, timeout=30000):
        print("FAIL_CONNECT:", mt5.last_error()); sys.exit(1)

    mt5.symbol_select(SYMBOL, True)
    native_tick = mt5.symbol_info_tick(SYMBOL)
    sym = mt5.symbol_info(SYMBOL)
    acct = mt5.account_info()

    if native_tick is None:
        print("FAIL: symbol_info_tick returned None"); mt5.shutdown(); sys.exit(1)

    positions = mt5.positions_get()
    orders = mt5.orders_get()
    pos_count = len(positions) if positions else 0
    ord_count = len(orders) if orders else 0

    canonical_tick, canonical_age_ms, canonical_error = fetch_canonical_tick(SYMBOL, MAX_CANONICAL_AGE_MS)

    print("--- Native tick (primary for geometry) ---")
    print(f"bid={native_tick.bid} ask={native_tick.ask} time={native_tick.time} time_msc={native_tick.time_msc} flags={native_tick.flags}")

    if canonical_tick:
        print("--- Canonical tick (audit only) ---")
        print(f"bid={canonical_tick['bid']} ask={canonical_tick['ask']} age_ms={canonical_age_ms:.1f}")
        bid_div = abs(native_tick.bid - canonical_tick["bid"])
        ask_div = abs(native_tick.ask - canonical_tick["ask"])
        print("--- Divergence (diagnostic, NOT blocking) ---")
        print(f"bid_div={bid_div:.4f} ask_div={ask_div:.4f}")
        if canonical_age_ms > MAX_CANONICAL_AGE_MS:
            print(f"WARN: canonical age {canonical_age_ms:.0f}ms > max {MAX_CANONICAL_AGE_MS}ms (non-blocking)")
    else:
        print(f"--- Canonical tick: {canonical_error} (non-blocking) ---")

    fresh = canonical_tick is not None and 0 <= canonical_age_ms <= MAX_CANONICAL_AGE_MS
    print(f"canonical_fresh: {fresh} (0 <= age_ms <= {MAX_CANONICAL_AGE_MS}, fail-closed no abs)")

    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(OUTPUT_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    buy_result = calibrate_side("BUY", native_tick, canonical_tick, canonical_age_ms, canonical_error, sym)
    sell_result = calibrate_side("SELL", native_tick, canonical_tick, canonical_age_ms, canonical_error, sym)

    mt5.shutdown()

    from hashlib import sha256
    profile_hash = sha256(str(acct.login).encode()).hexdigest()
    terminal_hash = sha256(TERMINAL_PATH.encode()).hexdigest()

    verdict_obj = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "symbol": SYMBOL,
        "volume": VOLUME,
        "profile_hash": profile_hash[:16] + "...",
        "terminal_hash": terminal_hash[:16] + "...",
        "contract_size": sym.trade_contract_size,
        "tick_size": sym.trade_tick_size,
        "point": sym.point, "digits": sym.digits,
        "positions_before": pos_count, "orders_before": ord_count,
        "quote_source": "EXECUTION_QUOTE_SNAPSHOT",
        "native_tick": {"bid": float(native_tick.bid), "ask": float(native_tick.ask),
                        "time": int(native_tick.time), "time_msc": int(native_tick.time_msc),
                        "flags": int(native_tick.flags)},
        "canonical_tick": canonical_tick,
        "canonical_age_ms": canonical_age_ms,
        "canonical_fresh": fresh,
        "buy": buy_result, "sell": sell_result,
        "positions_after": "NOT_CHECKED_AFTER_DISCONNECT",
        "orders_after": "NOT_CHECKED_AFTER_DISCONNECT",
        "order_submission_count": 0,
        "verdict": "PASS_TO_G3_REVIEW" if (buy_result["passing_candidate"] and sell_result["passing_candidate"]) else "FAIL",
    }

    verdict_obj = sanitize_for_json(verdict_obj)

    with open(os.path.join(run_dir, "verdict.json"), "w") as f:
        json.dump(verdict_obj, f, indent=2)
    with open(os.path.join(run_dir, "candidate_matrix.json"), "w") as f:
        json.dump(sanitize_for_json({"buy": buy_result["candidates"], "sell": sell_result["candidates"]}), f, indent=2)
    with open(os.path.join(run_dir, "order_check_results.redacted.json"), "w") as f:
        json.dump(sanitize_for_json({"buy": buy_result["order_check_results"], "sell": sell_result["order_check_results"]}), f, indent=2)
    with open(os.path.join(run_dir, "market_snapshot.json"), "w") as f:
        json.dump(sanitize_for_json({"bid": native_tick.bid, "ask": native_tick.ask, "spread": native_tick.ask - native_tick.bid,
                   "tick_size": sym.trade_tick_size, "point": sym.point, "digits": sym.digits,
                   "stops_level": sym.trade_stops_level, "freeze_level": sym.trade_freeze_level}), f, indent=2)

    print("\n=== G2.1c Calibration Results ===")
    print(f"Run ID: {run_id}")
    print("Quote source: EXECUTION_QUOTE_SNAPSHOT (native primary, canonical audit)")
    print(f"Positions before: {pos_count}, Orders before: {ord_count}")
    print(f"BUY passing candidate: {buy_result['passing_candidate']}")
    print(f"SELL passing candidate: {sell_result['passing_candidate']}")
    print("order_submission_count: 0")
    print(f"Verdict: {verdict_obj['verdict']}")

if __name__ == "__main__":
    main()
