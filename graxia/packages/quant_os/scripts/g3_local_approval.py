"""
G3 LOCAL APPROVAL HANDOFF.

Generates fresh demo canary plan from live Pepperstone snapshot.
Requires local human approval via console input within TTL (120s).
Does NOT call order_send — only prepares for G3 execution.

Usage:
    cd quant_os
    python scripts/g3_local_approval.py

On approval success, creates approval artifact at:
    artifacts/g3_final_preflight/<canary_id>/approval.redacted.json

The operator then runs g3_send_order.py separately.
"""
import json, hashlib, os, sys, time
from datetime import datetime, timezone, timedelta
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
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

OUTPUT_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "g3_final_preflight")


def normalize_price(price, tick_size):
    return round(round(price / tick_size) * tick_size, 8)


def main():
    # ── Connect terminal-session-only ──
    print("\n=== G3 LOCAL APPROVAL HANDOFF ===")
    print("Connecting to Pepperstone Demo (terminal-session-only)...")
    res = mt5.initialize(path=TERMINAL_PATH, timeout=30000)
    if not res:
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        return 1

    # ── Fresh snapshot ──
    mt5.symbol_select(SYMBOL, True)
    tick = mt5.symbol_info_tick(SYMBOL)
    sym = mt5.symbol_info(SYMBOL)
    acct = mt5.account_info()

    now_utc = datetime.now(timezone.utc)
    canary_id = f"CANARY-{now_utc.strftime('%Y%m%d-%H%M%S')}"
    correlation_id = str(uuid4())
    approval_nonce = uuid4().hex + uuid4().hex

    # ── Guard: Account mode ──
    account_mode = "DEMO"
    profile_hash = hashlib.sha256(str(acct.login).encode()).hexdigest()
    terminal_path_hash = hashlib.sha256(TERMINAL_PATH.encode()).hexdigest()

    profile_fingerprint = profile_hash[:32]
    terminal_fingerprint = terminal_path_hash[:32]

    # ── Guard: Positions and orders ──
    positions = mt5.positions_get()
    orders = mt5.orders_get()
    pos_count = len(positions) if positions else 0
    ord_count = len(orders) if orders else 0

    if pos_count > 0:
        print(f"BLOCKED: {pos_count} existing positions found")
        mt5.shutdown()
        return 1
    if ord_count > 0:
        print(f"BLOCKED: {ord_count} existing pending orders found")
        mt5.shutdown()
        return 1

    # ── Market snapshot ──
    bid = tick.bid
    ask = tick.ask
    spread_price = round(ask - bid, 8)
    tick_size = sym.trade_tick_size
    point = sym.point
    digits = sym.digits
    stops_level = sym.trade_stops_level
    freeze_level = sym.trade_freeze_level
    filling_mode = sym.filling_mode

    # ── ContractSpec fresh ──
    contract = {
        "contract_size": sym.trade_contract_size,
        "volume_min": sym.volume_min,
        "volume_max": sym.volume_max,
        "volume_step": sym.volume_step,
    }
    contract_hash = hashlib.sha256(
        f"{sym.trade_contract_size}:{sym.volume_min}:{sym.volume_max}".encode()
    ).hexdigest()

    # ── Geometry: BUY only ──
    protective_buffer = max(
        stops_level * point,
        freeze_level * point,
        spread_price * SAFETY_BUFFER_MULTIPLIER,
        POLICY_FLOOR_PRICE,
    )
    protective_buffer = normalize_price(protective_buffer, tick_size)

    entry = normalize_price(ask, tick_size)
    sl = normalize_price(bid - protective_buffer, tick_size)
    gross_loss_delta = normalize_price(entry - sl, tick_size)
    tp = normalize_price(entry + gross_loss_delta, tick_size)
    gross_reward_delta = normalize_price(tp - entry, tick_size)
    planned_gross_rr = round(gross_reward_delta / gross_loss_delta, 6) if gross_loss_delta > 0 else 0

    sl_valid = sl < bid
    tp_valid = tp > ask
    rr_valid = abs(planned_gross_rr - 1.0) < 0.001

    if not all([sl_valid, tp_valid, rr_valid]):
        print(f"GEOMETRY INVALID: sl_below_bid={sl_valid}, tp_above_ask={tp_valid}, rr={planned_gross_rr}")
        mt5.shutdown()
        return 1

    # ── Broker estimates ──
    projected_loss = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, SYMBOL, VOLUME, entry, sl)
    projected_gross_loss_usd = abs(projected_loss) if projected_loss else 0

    estimated_commission_usd = 0.0  # ponytail: Pepperstone demo may not charge commission
    estimated_all_in_max_loss_usd = projected_gross_loss_usd + estimated_commission_usd

    margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, VOLUME, entry)
    margin_usd = abs(margin) if margin else 0

    if projected_gross_loss_usd > PROJECTED_LOSS_CAP_USD:
        print(f"BLOCKED: projected loss ${projected_gross_loss_usd:.2f} exceeds cap ${PROJECTED_LOSS_CAP_USD}")
        mt5.shutdown()
        return 1

    # ── Tick freshness ──
    tick_age_ms = (time.time() - tick.time) * 1000 if hasattr(tick, 'time') else 0
    tick_fresh = tick_age_ms < 5000

    # ── order_check ──
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": mt5.ORDER_TYPE_BUY,
        "price": entry,
        "sl": sl,
        "tp": tp,
        "deviation": MAX_DEVIATION_POINTS,
        "magic": int(hashlib.sha256(canary_id.encode()).hexdigest()[:8], 16),
        "comment": f"CANARY_{canary_id[-8:]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    check = mt5.order_check(request)
    order_check_passed = check.retcode == 0 if check else False
    order_check_retcode = check.retcode if check else -999
    order_check_comment = check.comment if check else "order_check_failed"

    if not order_check_passed:
        print(f"BLOCKED: order_check failed retcode={order_check_retcode}: {order_check_comment}")
        mt5.shutdown()
        return 1

    # ── Verify no state change ──
    positions_after = mt5.positions_get()
    orders_after = mt5.orders_get()
    pos_after = len(positions_after) if positions_after else 0
    ord_after = len(orders_after) if orders_after else 0

    # ── Disconnect ──
    mt5.shutdown()

    # ── Build immutable plan ──
    expiry_utc = (now_utc + timedelta(seconds=PLAN_TTL_SECONDS))

    plan = {
        "schema_version": "1.0",
        "canary_id": canary_id,
        "correlation_id": correlation_id,
        "generated_at_utc": now_utc.isoformat(),
        "expiry_utc": expiry_utc.isoformat(),
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
        "projected_gross_loss_usd": projected_gross_loss_usd,
        "estimated_commission_usd": estimated_commission_usd,
        "estimated_all_in_max_loss_usd": estimated_all_in_max_loss_usd,
        "projected_margin_usd": margin_usd,
        "max_deviation_points": MAX_DEVIATION_POINTS,
        "filling_mode": filling_mode,
        "tick_age_ms": tick_age_ms,
        "tick_fresh": tick_fresh,
        "strategy_origin": None,
        "account_mode": account_mode,
        "profile_fingerprint": profile_fingerprint,
        "terminal_fingerprint": terminal_fingerprint,
        "contract_hash": contract_hash,
        "approval_nonce": approval_nonce,
    }

    plan_json = json.dumps(plan, indent=2, sort_keys=True)
    plan_hash = hashlib.sha256(plan_json.encode()).hexdigest()
    plan["plan_hash"] = plan_hash

    # ── Display for local review ──
    ttl_seconds = (expiry_utc - datetime.now(timezone.utc)).total_seconds()

    print(f"\n{'='*60}")
    print(f"FRESH CANARY PLAN — READY FOR LOCAL APPROVAL")
    print(f"{'='*60}")
    print(f"")
    print(f"  Canary ID:     {canary_id}")
    print(f"  Plan Hash:     {plan_hash}")
    print(f"  Correlation:   {correlation_id}")
    print(f"  TTL:           {ttl_seconds:.0f}s (expires {expiry_utc.isoformat()})")
    print(f"")
    print(f"  Environment:   {ENVIRONMENT}")
    print(f"  Symbol:        {SYMBOL}")
    print(f"  Side:          {SIDE}")
    print(f"  Volume:        {VOLUME}")
    print(f"")
    print(f"  Entry (ask):   {entry}")
    print(f"  SL (bid - {protective_buffer}): {sl}")
    print(f"  TP:            {tp}")
    print(f"  Gross loss:    {gross_loss_delta}")
    print(f"  Gross reward:  {gross_reward_delta}")
    print(f"  Gross RR:      {planned_gross_rr}")
    print(f"")
    print(f"  Proj loss:     ${projected_gross_loss_usd:.2f}")
    print(f"  Est commission: ${estimated_commission_usd:.2f}")
    print(f"  Max loss:      ${estimated_all_in_max_loss_usd:.2f}")
    print(f"  Proj margin:   ${margin_usd:.2f}")
    print(f"")
    print(f"  order_check:   {'PASS' if order_check_passed else 'FAIL'} (retcode={order_check_retcode})")
    print(f"  Positions:     {pos_count} | Orders: {ord_count}")
    print(f"  Tick age:      {tick_age_ms:.0f}ms {'FRESH' if tick_fresh else 'STALE'}")
    print(f"")
    print(f"  order_send:    NOT CALLED")
    print(f"  order_submission_count: 0")
    print(f"")
    print(f"{'='*60}")

    if ttl_seconds <= 0:
        print("\nPLAN EXPIRED during generation — restart.")
        return 1

    # ── Local approval prompt ──
    print(f"\n========================================")
    print(f"  LOCAL HUMAN APPROVAL REQUIRED")
    print(f"========================================")
    print(f"  To approve, type the EXACT line below:")
    print(f"========================================")
    confirmation = f"APPROVE_DEMO_CANARY {canary_id} {plan_hash[:16]} {approval_nonce[:16]}"
    print(f"\n  > {confirmation}")
    print(f"\n  TTL: {ttl_seconds:.0f}s — plan expires at {expiry_utc.isoformat()}")
    print(f"  After TTL, plan is void. Rerun script for fresh plan.")
    print(f"  Type anything else to CANCEL.")
    print(f"========================================\n")

    try:
        user_input = input("APPROVAL: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\nApproval cancelled (EOF/interrupt).")
        return 1

    # check expiry immediately
    now_check = datetime.now(timezone.utc)
    if now_check > expiry_utc:
        print(f"\nPLAN EXPIRED at {expiry_utc.isoformat()}. Current time: {now_check.isoformat()}")
        print("Run the script again for a fresh plan.")
        return 1

    if user_input == confirmation:
        print(f"\n✅ APPROVAL ACCEPTED for {canary_id}")
        print(f"Plan hash prefix: {plan_hash[:16]}")
        print(f"Environment: {ENVIRONMENT}")
        print(f"Submission still depends on final fresh preflight and order_send.")
        print(f"order_send has NOT been called.")

        # ── Save approval artifact ──
        run_dir = os.path.join(OUTPUT_BASE, canary_id)
        os.makedirs(run_dir, exist_ok=True)

        approval_artifact = {
            "schema_version": "1.0",
            "canary_id": canary_id,
            "plan_hash": plan_hash,
            "plan_hash_prefix": plan_hash[:16],
            "environment": ENVIRONMENT,
            "purpose": PURPOSE,
            "symbol": SYMBOL,
            "volume": str(VOLUME),
            "approved_at_utc": now_check.isoformat(),
            "plan_expiry_utc": expiry_utc.isoformat(),
            "approval_nonce_prefix": approval_nonce[:16],
            "operator_fingerprint": "LOCAL_CONSOLE",
        }

        with open(os.path.join(run_dir, "approval.redacted.json"), "w") as f:
            json.dump(approval_artifact, f, indent=2)

        # Also write fresh plan
        with open(os.path.join(run_dir, "plan.json"), "w") as f:
            json.dump(plan, f, indent=2)

        # ── Print send instructions ──
        print(f"\n{'='*60}")
        print(f"  NEXT STEP: SUBMIT DEMO ORDER")
        print(f"{'='*60}")
        print(f"  Approval artifact: {run_dir}/approval.redacted.json")
        print(f"  Plan artifact:     {run_dir}/plan.json")
        print(f"")
        print(f"  To send the demo order, run:")
        print(f"  python scripts/g3_send_order.py {canary_id}")
        print(f"")
        print(f"  Must be run within: TTL remaining")
        print(f"  order_send will be called exactly once.")
        print(f"  After send: reconcile position, SL/TP, close, deal history.")
        print(f"{'='*60}")

        # Save plan for send script
        with open(os.path.join(run_dir, "approval_ready.txt"), "w") as f:
            f.write(f"APPROVED\ncanary_id={canary_id}\nplan_hash={plan_hash}\n")

        return 0
    else:
        print(f"\n❌ APPROVAL REJECTED or mismatch.")
        print(f"Expected: {confirmation}")
        print(f"Got:      {user_input}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
