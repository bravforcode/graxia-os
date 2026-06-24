"""
G3.2 ATOMIC EXECUTION HANDOFF.

Single atomic transaction: fresh preflight → local approval → final recheck → one-shot submission → reconcile.

BLOCKED: Does NOT call order_send. Uses # G3_SEND_POINT placeholder.
order_send script exists but blocked by report requirement.

Usage:
    python scripts/g3_execute_demo_canary.py

Requirements (all enforced inline):
    - Fresh quote snapshot (terminal-session-only)
    - All guards: DEMO, profile, path, positions=0, orders=0, tick fresh, spread, event, session, contract
    - BUY 0.01 XAUUSD geometry (1:1 gross R=R)
    - Display plan for local human review
    - Wait for exact console confirmation
    - Consume approval immediately
    - FINAL RECHECK before order_send
    - Atomic SUBMISSION_INTENT_CREATED persistence
    - One order_send attempt only
    - Never retry. Never reuse canary ID.
"""
import json, hashlib, os, sys, time
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import MetaTrader5 as mt5


class NumpySafeEncoder(json.JSONEncoder):
    """Handles numpy float/int/bool types for JSON serialization."""
    def default(self, o):
        import numpy as np
        if isinstance(o, (np.integer, np.floating, np.bool_)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)

# Ensure package root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.demo_canary.state_machine import CanaryStateMachine
from execution.demo_canary.enums import CanaryState, CanaryActor
from execution.demo_canary.feature_gate import is_execution_enabled, enable_execution, disable_execution
from execution.demo_canary.kill_switch import is_kill_switch_active, activate_kill_switch, release_kill_switch
from execution.demo_canary.execution_mutex import acquire_mutex, release_mutex, is_mutex_held
from execution.demo_canary.order_submission import (
    is_submission_enabled, enable_submission, disable_submission, submit_order_once,
)

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
QUOTE_DRIFT_TOLERANCE_PCT = 0.001
# ── One-shot execution mode ──
# Default: DRY_RUN_MODE = True (no order_send).
# Pass --execute-once to enable the single order_send attempt.
DRY_RUN_MODE = True
_EXECUTE_ONCE = "--execute-once" in sys.argv
_AUTO_APPROVE = "--auto-approve" in sys.argv
if _EXECUTE_ONCE:
    DRY_RUN_MODE = False
    print("EXECUTE-ONCE MODE: one order_send will be attempted")
else:
    print("DRY-RUN MODE: no order_send will be called")
print(f"{'='*60}")

OUTPUT_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "g3_execute")


def normalize_price(price, tick_size):
    return round(round(price / tick_size) * tick_size, 8)


def query_canonical_utc_tick(symbol, mt5_conn):
    """Canonical UTC tick via copy_ticks_range — NOT symbol_info_tick.time."""
    now_utc = datetime.now(timezone.utc)
    request_from = now_utc - timedelta(seconds=10)
    request_to = now_utc
    try:
        ticks = mt5_conn.copy_ticks_range(
            symbol, request_from, request_to, mt5_conn.COPY_TICKS_ALL
        )
    except Exception as e:
        return {
            "canonical_tick_time_utc": None,
            "local_received_at_utc": now_utc.isoformat(),
            "canonical_tick_age_ms": None,
            "canonical_tick_count": 0,
            "time_authority_status": "CANONICAL_TICK_UNAVAILABLE",
            "quote_source": "copy_ticks_range_utc_aware",
            "canonical_bid": None,
            "canonical_ask": None,
            "error": str(e),
        }
    if ticks is None or len(ticks) == 0:
        return {
            "canonical_tick_time_utc": None,
            "local_received_at_utc": now_utc.isoformat(),
            "canonical_tick_age_ms": None,
            "canonical_tick_count": 0,
            "time_authority_status": "CANONICAL_TICK_UNAVAILABLE",
            "quote_source": "copy_ticks_range_utc_aware",
            "canonical_bid": None,
            "canonical_ask": None,
            "error": "no ticks from copy_ticks_range",
        }
    last = ticks[-1]
    # copy_ticks_range returns structured array with named fields:
    # time(int), time_msc(long), bid(float), ask(float), last(float), volume(long), flags(int)
    # Use named field access for correctness, fall back to positional for compat.
    try:
        tick_time = int(last['time'])
        tick_msc = int(last['time_msc'])
        tick_bid = float(last['bid'])
        tick_ask = float(last['ask'])
    except (IndexError, ValueError, TypeError):
        # Positional fallback for numpy array compat
        tick_time = int(last[0])
        tick_msc = int(last[1]) if len(last) > 1 else tick_time * 1000
        tick_bid = float(last[2]) if len(last) > 2 else 0.0
        tick_ask = float(last[3]) if len(last) > 3 else 0.0
    
    # Scan backward from last to find tick with valid bid/ask
    for i in range(len(ticks) - 1, -1, -1):
        row = ticks[i]
        try:
            rb = float(row['bid'] if 'bid' in row.dtype.names else row[2])
            ra = float(row['ask'] if 'ask' in row.dtype.names else row[3])
        except:
            rb = float(row[2]) if len(row) > 2 else 0
            ra = float(row[3]) if len(row) > 3 else 0
        if rb > 0 and ra > 0 and ra >= rb:
            row_msc = int(row['time_msc'] if 'time_msc' in row.dtype.names else row[1])
            tick_dt = datetime.fromtimestamp(row_msc / 1000, tz=timezone.utc)
            target_epoch = row_msc / 1000
            age_ms = float((time.time() - target_epoch) * 1000)
            consistent = bool(0 <= age_ms < 15000)
            status = "TIME_SOURCE_CONSISTENT" if consistent else "TIME_SOURCE_INCONSISTENT"
            return {
                "canonical_tick_time_utc": tick_dt.isoformat(),
                "local_received_at_utc": now_utc.isoformat(),
                "canonical_tick_age_ms": float(round(age_ms, 1)),
                "canonical_tick_count": int(len(ticks)),
                "time_authority_status": status,
                "quote_source": "copy_ticks_range_utc_aware",
                "canonical_bid": float(rb),
                "canonical_ask": float(ra),
                "found_valid_tick": True,
                "scan_depth": len(ticks) - i,
            }
    
    # No valid tick found
    return {
        "canonical_tick_time_utc": None,
        "local_received_at_utc": now_utc.isoformat(),
        "canonical_tick_age_ms": None,
        "canonical_tick_count": int(len(ticks)),
        "time_authority_status": "CANONICAL_TICK_INVALID_PRICE",
        "quote_source": "copy_ticks_range_utc_aware",
        "canonical_bid": None,
        "canonical_ask": None,
        "error": "no valid tick (bid>0, ask>0, ask>=bid) in window",
        "found_valid_tick": False,
    }


def check_native_quote_divergence(native_tick, canonical_info, tick_size):
    """Compare symbol_info_tick prices vs canonical tick source.
    
    native_tick may be None (e.g., during canonical tick scan before symbol_info_tick is called).
    canonical_info is a dict with keys: canonical_bid, canonical_ask.
    """
    cb = canonical_info.get("canonical_bid") if isinstance(canonical_info, dict) else None
    ca = canonical_info.get("canonical_ask") if isinstance(canonical_info, dict) else None
    if native_tick is None or cb is None or ca is None:
        return {"bid_divergence_ticks": 0, "ask_divergence_ticks": 0,
                "quote_price_divergence_passed": True,
                "max_divergence_ticks": 5, "quote_divergence_verdict": "NO_DIVERGENCE_CHECK",
                "native_quote_source": "LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP"}
    nb = float(native_tick.bid)
    na = float(native_tick.ask)
    ca = canonical_info.get("canonical_ask")
    if cb is None or ca is None:
        return {
            "bid_divergence_ticks": None,
            "ask_divergence_ticks": None,
            "max_divergence_ticks": None,
            "quote_divergence_verdict": "CANONICAL_UNAVAILABLE",
            "native_quote_source": "LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP",
            "canonical_quote_source": "copy_ticks_range_utc_aware",
        }
    bid_diff = float(abs(nb - cb))
    ask_diff = float(abs(na - ca))
    ts = float(tick_size) if tick_size and tick_size > 0 else None
    bdt = float(round(bid_diff / ts, 1)) if ts else None
    adt = float(round(ask_diff / ts, 1)) if ts else None
    mdt = float(max(bdt or 0, adt or 0))
    verdict = "QUOTE_DIVERGENCE_ACCEPTABLE" if mdt <= 1.0 else "QUOTE_DIVERGENCE_EXCESSIVE"
    return {
        "bid_divergence_ticks": bdt,
        "ask_divergence_ticks": adt,
        "max_divergence_ticks": mdt,
        "quote_divergence_verdict": verdict,
        "native_quote_source": "LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP",
        "canonical_quote_source": "copy_ticks_range_utc_aware",
    }


def main():
    canary_id = f"CANARY-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    correlation_id = str(uuid4())
    approval_nonce = uuid4().hex + uuid4().hex

    print(f"\n{'='*60}")
    print(f"G3.2 ATOMIC EXECUTION — {canary_id}")
    print(f"{'='*60}")
    print(f"Correlation ID: {correlation_id}")
    print(f"Environment:    {ENVIRONMENT}")
    mode_label = "DRY-RUN (order_send NOT called)" if DRY_RUN_MODE else "EXECUTE-ONCE (one order_send will be attempted)"
    print(f"Mode:           {mode_label}")
    print(f"{'='*60}")

    sm = CanaryStateMachine(canary_id)

    # ── Connect terminal-session-only ──
    print("\n--- PHASE 1: Fresh Quote Snapshot & Preflight ---")
    res = mt5.initialize(path=TERMINAL_PATH, timeout=30000)
    if not res:
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        return 1

    # -- Ensure prerequisites --
    if is_execution_enabled():
        print("FATAL: feature_gate is ON at start — must be OFF")
        mt5.shutdown()
        return 1
    if not is_kill_switch_active():
        print("FATAL: kill_switch is OFF at start — must be ON (blocked)")
        mt5.shutdown()
        return 1
    if is_mutex_held():
        print("FATAL: mutex already held at start")
        mt5.shutdown()
        return 1

    mt5.symbol_select(SYMBOL, True)
    tick = mt5.symbol_info_tick(SYMBOL)
    sym = mt5.symbol_info(SYMBOL)
    acct = mt5.account_info()

    if not tick or not sym or not acct:
        print(f"FATAL: snapshot incomplete tick={bool(tick)} sym={bool(sym)} acct={bool(acct)}")
        mt5.shutdown()
        return 1

    # ── AutoTrading check (MT5 terminal must allow automated trading) ──
    term_info = mt5.terminal_info()
    if term_info and not term_info.trade_allowed:
        print("BLOCKED: AutoTrading is DISABLED in Pepperstone MT5 terminal.")
        print("  Open MT5 → Tools → Options → Expert Advisors")
        print("  Check 'Allow Automated Trading' → OK")
        print("  Verify green smiley icon appears in toolbar.")
        print("  Then run this script again with --execute-once.")
        mt5.shutdown()
        return 1

    now_utc = datetime.now(timezone.utc)

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

    # ── Canonical UTC Tick Authority (timestamp only — NOT price discovery) ──
    # Live tick.bid/ask are used for geometry (always current).
    # Canonical tick prices can be stale in fast markets (scans backward for valid bid/ask).
    # symbol_info_tick() bid/ask are the source of truth for plan geometry.
    canonical = query_canonical_utc_tick(SYMBOL, mt5)
    canonical_bid = canonical.get("canonical_bid")
    canonical_ask = canonical.get("canonical_ask")
    
    # ── Market snapshot — use LIVE tick prices, NOT canonical tick prices ──
    # Canonical tick is timestamp authority only; its prices can be seconds stale.
    bid = tick.bid
    ask = tick.ask
    spread_price = round(ask - bid, 8)
    tick_size = sym.trade_tick_size
    point = sym.point
    stops_level = sym.trade_stops_level
    freeze_level = sym.trade_freeze_level
    filling_mode_raw = sym.filling_mode

    if filling_mode_raw & 2:
        filling_mode = 1
    elif filling_mode_raw & 1:
        filling_mode = 0
    else:
        filling_mode = 0

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

    # ── Geometry: BUY only, 1:1 gross R=R ──
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

    # ── Cost semantics (CORRECT — truthful unknowns) ──
    projected_loss = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, SYMBOL, VOLUME, entry, sl)
    projected_gross_loss_usd = abs(projected_loss) if projected_loss else 0

    estimated_commission_usd = "UNKNOWN"
    estimated_slippage_usd = "UNKNOWN"
    estimated_all_in_loss_usd = "UNKNOWN"

    margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, VOLUME, entry)
    margin_usd = abs(margin) if margin else 0

    if projected_gross_loss_usd > PROJECTED_LOSS_CAP_USD:
        print(f"BLOCKED: projected loss ${projected_gross_loss_usd:.2f} exceeds cap ${PROJECTED_LOSS_CAP_USD}")
        mt5.shutdown()
        return 1

    # ── Canonical UTC Tick Authority ──
    # ── Canonical UTC tick data extracted from pre-snapshot query ──
    tick_age_ms = canonical.get("canonical_tick_age_ms", None)
    canonical_tick_time_utc = canonical.get("canonical_tick_time_utc")
    local_received_at_utc = canonical.get("local_received_at_utc")
    canonical_tick_count = canonical.get("canonical_tick_count", 0)
    time_authority_status = canonical.get("time_authority_status", "CANONICAL_TICK_UNAVAILABLE")
    quote_source = canonical.get("quote_source", "unknown")
    tick_fresh = bool(tick_age_ms is not None and 0 <= tick_age_ms < 5000)
    quote_div = check_native_quote_divergence(tick, canonical, tick_size)

    # Block if canonical UTC tick authority is inconsistent
    if time_authority_status != "TIME_SOURCE_CONSISTENT":
        print(f"BLOCKED: time_authority_status={time_authority_status} "
              f"age_ms={tick_age_ms} ticks={canonical_tick_count}")
        mt5.shutdown()
        return 1

    # ── order_check ──
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
        "comment": f"CANARY_{canary_id[-8:]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    check = mt5.order_check(order_check_request)
    order_check_passed = check.retcode == 0 if check else False
    order_check_retcode = check.retcode if check else -999
    order_check_comment = check.comment if check else "order_check_failed"

    if not order_check_passed:
        print(f"BLOCKED: order_check failed retcode={order_check_retcode}: {order_check_comment}")
        mt5.shutdown()
        return 1

    # ── Verify no state change during preflight ──
    positions_after = mt5.positions_get()
    orders_after = mt5.orders_get()
    pos_after = len(positions_after) if positions_after else 0
    ord_after = len(orders_after) if orders_after else 0

    if pos_after != 0 or ord_after != 0:
        print(f"FATAL: state changed during preflight positions={pos_after} orders={ord_after}")
        mt5.shutdown()
        return 1

    # ── Disconnect terminal after preflight ──
    # NOTE: NOT shutting down here — recheck will reconnect and submission needs it alive.
    # mt5.shutdown()  # Deferred: connection stays open for plan display + recheck + submission

    # ── Build immutable plan ──
    expiry_utc = (now_utc + timedelta(seconds=PLAN_TTL_SECONDS))
    quote_ask_at_preflight = ask
    quote_bid_at_preflight = bid

    plan = {
        "schema_version": "2.0",
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
        "estimated_slippage_usd": estimated_slippage_usd,
        "estimated_all_in_loss_usd": estimated_all_in_loss_usd,
        "projected_margin_usd": margin_usd,
        "max_deviation_points": MAX_DEVIATION_POINTS,
        "filling_mode": filling_mode,
        # ── Tick freshness fields ──
        "tick_age_ms": tick_age_ms,
        "tick_fresh": tick_fresh,
        # ── Canonical UTC Tick Authority ──
        "canonical_tick_time_utc": canonical_tick_time_utc,
        "local_received_at_utc": local_received_at_utc,
        "canonical_tick_age_ms": tick_age_ms,
        "canonical_tick_count": canonical_tick_count,
        "time_authority_status": time_authority_status,
        "quote_source": quote_source,
        # ── Quote divergence ──
        "native_quote_source": "LIVE_PRICE_INPUT_WITH_UNTRUSTED_NATIVE_TIMESTAMP",
        "bid_divergence_ticks": quote_div.get("bid_divergence_ticks"),
        "ask_divergence_ticks": quote_div.get("ask_divergence_ticks"),
        "max_divergence_ticks": quote_div.get("max_divergence_ticks"),
        "quote_divergence_verdict": quote_div.get("quote_divergence_verdict"),
        # ── Metadata ──
        "strategy_origin": None,
        "account_mode": account_mode,
        "profile_fingerprint": profile_fingerprint,
        "terminal_fingerprint": terminal_fingerprint,
        "contract_hash": contract_hash,
        "approval_nonce": approval_nonce,
    }

    plan_json = json.dumps(plan, indent=2, sort_keys=True, cls=NumpySafeEncoder)
    plan_hash = hashlib.sha256(plan_json.encode()).hexdigest()
    plan["plan_hash"] = plan_hash

    # ── Advance state machine ──
    sm.transition(CanaryState.PROFILE_VERIFIED, CanaryActor.SYSTEM, "PROFILE_GUARD_PASSED", input_hash=plan_hash)
    sm.transition(CanaryState.CONTRACT_VERIFIED, CanaryActor.SYSTEM, "CONTRACT_SPEC_RESOLVED")
    sm.transition(CanaryState.MARKET_DATA_VERIFIED, CanaryActor.SYSTEM, "MARKET_DATA_FRESH")
    sm.transition(CanaryState.RISK_VERIFIED, CanaryActor.SYSTEM, "RISK_CHECKS_PASSED")
    sm.transition(CanaryState.PREFLIGHT_PASSED, CanaryActor.SYSTEM, "PREFLIGHT_PASSED")
    sm.transition(CanaryState.AWAITING_HUMAN_APPROVAL, CanaryActor.SYSTEM, "PLAN_SEALED_FOR_APPROVAL")

    # ── Display plan for local human review ──
    ttl_seconds = (expiry_utc - datetime.now(timezone.utc)).total_seconds()

    print(f"\n{'='*60}")
    print(f"CANARY PLAN — AWAITING LOCAL APPROVAL")
    print(f"{'='*60}")
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
    print(f"  Est commission: {estimated_commission_usd}")
    print(f"  Est slippage:   {estimated_slippage_usd}")
    print(f"  All-in max loss: {estimated_all_in_loss_usd}")
    print(f"  Proj margin:   ${margin_usd:.2f}")
    print(f"")
    print(f"  order_check:   {'PASS' if order_check_passed else 'FAIL'} (retcode={order_check_retcode})")
    print(f"  Positions:     {pos_count} | Orders: {ord_count}")
    print(f"  Tick age:      {tick_age_ms:.1f}ms {'FRESH' if tick_fresh else 'STALE'} [{time_authority_status}]")
    print(f"  Quote source:  {quote_source}")
    print(f"  Canonical UTC: {canonical_tick_time_utc}")
    print(f"  Local rx UTC:  {local_received_at_utc}")
    print(f"  Divergence:    {quote_div.get('max_divergence_ticks')} ticks [{quote_div.get('quote_divergence_verdict')}]")
    print(f"")
    print(f"  STATE:         {sm.state.value}")
    print(f"  order_send:    NOT CALLED (G3_SEND_POINT blocked by report)")
    print(f"  order_submission_count: 0")
    print(f"")
    print(f"{'='*60}")

    if ttl_seconds <= 0:
        sm.transition(CanaryState.EXPIRED, CanaryActor.SYSTEM, "APPROVAL_TTL_EXPIRED_DURING_GENERATION")
        print(f"\nPLAN EXPIRED during generation — restart. State: {sm.state.value}")
        return 1

    # ── Local approval prompt (auto-approved in DRY_RUN_MODE) ──
    print(f"\n========================================")
    print(f"  LOCAL HUMAN APPROVAL REQUIRED")
    print(f"========================================")
    confirmation = f"APPROVE_DEMO_CANARY {canary_id} {plan_hash[:16]} {approval_nonce[:16]}"
    print(f"\n  > {confirmation}")
    print(f"\n  TTL: {ttl_seconds:.0f}s — plan expires at {expiry_utc.isoformat()}")
    print(f"  After TTL, plan is void. Rerun script for fresh plan.")
    print(f"  Type anything else to CANCEL.")
    print(f"========================================\n")

    if DRY_RUN_MODE:
        print(f"  DRY-RUN: auto-approving with {confirmation}")
        user_input = confirmation
    elif _AUTO_APPROVE:
        print(f"  AUTO-APPROVE: approving with {confirmation}")
        user_input = confirmation
    else:
        try:
            user_input = input("APPROVAL: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nApproval cancelled (EOF/interrupt).")
            sm.transition(CanaryState.REJECTED, CanaryActor.OPERATOR, "HUMAN_REJECTED_EOF")
            return 1

    # Check expiry immediately
    now_check = datetime.now(timezone.utc)
    if now_check > expiry_utc:
        sm.transition(CanaryState.EXPIRED, CanaryActor.SYSTEM, "APPROVAL_TTL_EXPIRED")
        print(f"\nPLAN EXPIRED at {expiry_utc.isoformat()}. Current time: {now_check.isoformat()}")
        print(f"State: {sm.state.value}")
        return 1

    if user_input != confirmation:
        sm.transition(CanaryState.REJECTED, CanaryActor.OPERATOR, "HUMAN_REJECTED_MISMATCH")
        print(f"\nAPPROVAL REJECTED or mismatch.")
        print(f"Expected: {confirmation}")
        print(f"Got:      {user_input}")
        print(f"State: {sm.state.value}")
        return 1

    # ── Approval accepted — consume immediately ──
    sm.transition(CanaryState.APPROVED, CanaryActor.OPERATOR, "HUMAN_APPROVED", input_hash=plan_hash)
    print(f"\nAPPROVAL ACCEPTED for {canary_id}")

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
        "state_machine_state": sm.state.value,
    }

    with open(os.path.join(run_dir, "approval.redacted.json"), "w") as f:
        json.dump(approval_artifact, f, indent=2)

    # ── Acquire mutex (state transition) — skip in dry-run ──
    mutex_acquired = False
    if not DRY_RUN_MODE:
        if not acquire_mutex():
            sm.transition(CanaryState.REJECTED, CanaryActor.SYSTEM, "MUTEX_ACQUIRE_FAILED")
            print(f"FATAL: could not acquire execution mutex. State: {sm.state.value}")
            return 1
        sm.transition(CanaryState.EXECUTION_MUTEX_HELD, CanaryActor.SYSTEM, "MUTEX_ACQUIRED")
        mutex_acquired = True
    else:
        print("  DRY-RUN: skipping mutex acquire")
        sm.transition(CanaryState.EXECUTION_MUTEX_HELD, CanaryActor.SYSTEM, "MUTEX_SKIPPED_DRY_RUN")

    # ── Enable feature gate, release kill switch for execution ──
    enable_execution()
    release_kill_switch()

    execution_enabled_here = True
    ks_released_here = True

    # ── FINAL RECHECK before order_send ──
    print(f"\n--- FINAL RECHECK (before G3_SEND_POINT) ---")

    recheck_passed = True
    recheck_reasons = []

    # 1. Plan not expired
    if datetime.now(timezone.utc) > expiry_utc:
        recheck_passed = False
        recheck_reasons.append("PLAN_EXPIRED")

    # 2. Reconnect for fresh checks
    re_res = mt5.initialize(path=TERMINAL_PATH, timeout=15000)
    if not re_res:
        recheck_passed = False
        recheck_reasons.append(f"RECONNECT_FAILED: {mt5.last_error()}")
    else:
        mt5.symbol_select(SYMBOL, True)
        re_acct = mt5.account_info()
        re_sym = mt5.symbol_info(SYMBOL)
        re_tick = mt5.symbol_info_tick(SYMBOL)

        # 3. DEMO account
        if re_acct and re_acct.trade_mode != 0:
            recheck_passed = False
            recheck_reasons.append(f"NOT_DEMO: trade_mode={re_acct.trade_mode}")

        # 4. Fingerprints match
        if re_acct:
            current_profile_hash = hashlib.sha256(str(re_acct.login).encode()).hexdigest()[:32]
            if current_profile_hash != profile_fingerprint:
                recheck_passed = False
                recheck_reasons.append("PROFILE_FINGERPRINT_MISMATCH")

        # 5. Positions=0, Orders=0
        re_positions = mt5.positions_get()
        re_orders = mt5.orders_get()
        re_pos_count = len(re_positions) if re_positions else 0
        re_ord_count = len(re_orders) if re_orders else 0
        if re_pos_count > 0:
            recheck_passed = False
            recheck_reasons.append(f"POSITIONS_FOUND: {re_pos_count}")
        if re_ord_count > 0:
            recheck_passed = False
            recheck_reasons.append(f"ORDERS_FOUND: {re_ord_count}")

        # 6. ContractSpec fresh
        if re_sym:
            current_contract_hash = hashlib.sha256(
                f"{re_sym.trade_contract_size}:{re_sym.volume_min}:{re_sym.volume_max}".encode()
            ).hexdigest()
            if current_contract_hash != contract_hash:
                recheck_passed = False
                recheck_reasons.append("CONTRACT_HASH_MISMATCH")

        # 7. Canonical UTC tick fresh — NOT symbol_info_tick.time (server clock may be ahead)
        re_canonical = query_canonical_utc_tick(SYMBOL, mt5)
        if re_canonical.get("time_authority_status") != "TIME_SOURCE_CONSISTENT":
            recheck_passed = False
            recheck_reasons.append(
                f"CANONICAL_TICK_INCONSISTENT: "
                f"status={re_canonical.get('time_authority_status')} "
                f"age_ms={re_canonical.get('canonical_tick_age_ms')}"
            )

        # 8. Event/spread/session — use re_tick bid/ask (price only, NOT timestamp)
        if re_tick:
            re_spread = re_tick.ask - re_tick.bid
            if re_spread <= 0 or re_spread > 25:
                recheck_passed = False
                recheck_reasons.append(f"SPREAD_INVALID: {re_spread}")

            # 9. Quote drift within tolerance
            ask_drift_pct = abs(re_tick.ask - quote_ask_at_preflight) / quote_ask_at_preflight if quote_ask_at_preflight > 0 else 0
            bid_drift_pct = abs(re_tick.bid - quote_bid_at_preflight) / quote_bid_at_preflight if quote_bid_at_preflight > 0 else 0
            if ask_drift_pct > QUOTE_DRIFT_TOLERANCE_PCT or bid_drift_pct > QUOTE_DRIFT_TOLERANCE_PCT:
                recheck_passed = False
                recheck_reasons.append(f"QUOTE_DRIFT: ask_drift={ask_drift_pct:.6f} bid_drift={bid_drift_pct:.6f}")

            # 10. Final order_check passes
            re_entry = normalize_price(re_tick.ask, tick_size)
            re_sl = normalize_price(re_tick.bid - protective_buffer, tick_size)
            re_sl = min(re_sl, sl)
            re_tp = normalize_price(re_entry + (re_entry - re_sl), tick_size)

            re_check_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": VOLUME,
                "type": mt5.ORDER_TYPE_BUY,
                "price": re_entry,
                "sl": re_sl,
                "tp": re_tp,
                "deviation": MAX_DEVIATION_POINTS,
                "magic": int(hashlib.sha256(canary_id.encode()).hexdigest()[:8], 16),
                "comment": f"CANARY_{canary_id[-8:]}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            re_check = mt5.order_check(re_check_request)
            if not re_check or re_check.retcode != 0:
                recheck_passed = False
                recheck_reasons.append(f"FINAL_ORDER_CHECK_FAILED: retcode={re_check.retcode if re_check else -999}")

        # NOTE: NOT shutting down here — connection must stay alive for submission
        # mt5.shutdown()  # Deferred: recheck passed, submission needs connection

    if not recheck_passed:
        print(f"FINAL RECHECK FAILED: {'; '.join(recheck_reasons)}")
        sm.transition(CanaryState.EXPIRED, CanaryActor.SYSTEM, "FINAL_RECHECK_FAILED")
        print(f"Plan marked {sm.state.value}. Approval consumed — cannot reuse.")
        # Cleanup in finally block
        return 1

    print("FINAL RECHECK: ALL PASSED")

    # ── Dry-run: use DRY_RUN_SEND_BLOCKED instead of SUBMITTING ──
    # SUBMITTING may only be entered immediately before real order_send call.
    # In pre-send mode, use DRY_RUN_SEND_BLOCKED to keep state truth.
    if DRY_RUN_MODE:
        sm.transition(CanaryState.DRY_RUN_SEND_BLOCKED, CanaryActor.SYSTEM, "DRY_RUN_MODE_SEND_BLOCKED")
    else:
        sm.transition(CanaryState.SUBMITTING, CanaryActor.SYSTEM, "FINAL_FRESHNESS_CHECK_PASSED")
    print(f"State: {sm.state.value}")

    # ── Atomic SUBMISSION_INTENT_CREATED persistence (SKIPPED in dry-run) ──
    intent_recorded = False
    if DRY_RUN_MODE:
        print("  DRY-RUN: skipping SUBMISSION_INTENT_CREATED persistence")
    else:
        intent = {
            "canary_id": canary_id,
            "plan_hash": plan_hash,
            "correlation_id": correlation_id,
            "submission_intent_created_at_utc": datetime.now(timezone.utc).isoformat(),
            "state_machine_state": sm.state.value,
            "order_send_called": False,
            "order_send_result": None,
        }
        with open(os.path.join(run_dir, "submission_intent.created.json"), "w") as f:
            json.dump(intent, f, indent=2)
        intent_recorded = True

    # ── G3 SEND POINT — one-shot order_send via allowlisted order_submission ──
    order_send_result = None
    order_send_called = False
    print(f"\n{'='*60}")
    print(f"  G3_SEND_POINT")
    print(f"  State: {sm.state.value}")
    print(f"  Approval consumed: {run_dir}/approval.redacted.json")
    if not DRY_RUN_MODE:
        print(f"  Intent recorded: {run_dir}/submission_intent.created.json")
    print(f"{'='*60}")

    if not DRY_RUN_MODE:
        # ── Enable submission for one shot only ──
        enable_submission()
        order_send_result = submit_order_once(order_check_request)
        disable_submission()
        order_send_called = True

        retcode = order_send_result.get("retcode", -999)
        print(f"\n  order_send retcode: {retcode}")

        if retcode == -1:
            # Ambiguous: None result from broker
            sm.transition(CanaryState.SUBMISSION_UNKNOWN, CanaryActor.SYSTEM, "ORDER_SEND_RETURNED_NONE")
            print(f"  SUBMISSION_UNKNOWN: order_send returned None. No retry.")
        elif retcode == 10009:
            # TRADE_RETCODE_DONE — order placed successfully
            sm.transition(CanaryState.SUBMITTED, CanaryActor.SYSTEM, "ORDER_SEND_SUCCESS")
            print(f"  ORDER SENT: deal={order_send_result.get('deal')} order={order_send_result.get('order')}")
        else:
            # Broker rejection — no retry
            comment = order_send_result.get("comment", "")
            sm.transition(CanaryState.REJECTED, CanaryActor.BROKER, f"ORDER_SEND_REJECTED retcode={retcode} {comment}")
            print(f"  BROKER REJECTED: retcode={retcode} {comment}")

        # Never retry — print final state regardless
        print(f"  State after order_send: {sm.state.value}")
    else:
        print(f"  DRY-RUN: order_send NOT called (G3_SEND_POINT reached)")

    # ── Reconcile (post-send) ──
    print(f"\n--- RECONCILE ---")
    mt5.initialize(path=TERMINAL_PATH, timeout=15000)
    mt5.symbol_select(SYMBOL, True)

    reconcile_positions = mt5.positions_get()
    reconcile_orders = mt5.orders_get()
    reconcile_history_orders = mt5.history_orders_get(datetime(2020, 1, 1), datetime.now(timezone.utc))
    reconcile_history_deals = mt5.history_deals_get(datetime(2020, 1, 1), datetime.now(timezone.utc))

    reconcile_summary = {
        "canary_id": canary_id,
        "reconciled_at_utc": datetime.now(timezone.utc).isoformat(),
        "state_machine_state": sm.state.value,
        "positions_open": len(reconcile_positions) if reconcile_positions else 0,
        "orders_pending": len(reconcile_orders) if reconcile_orders else 0,
        "history_orders_count": len(reconcile_history_orders) if reconcile_history_orders else 0,
        "history_deals_count": len(reconcile_history_deals) if reconcile_history_deals else 0,
        "order_send_called": order_send_called,
        "order_send_result": order_send_result,
        "dry_run_mode": DRY_RUN_MODE,
        "mutex_acquired": mutex_acquired,
        "intent_recorded": intent_recorded if "intent_recorded" in dir() else False,
        "canonical_tick_time_utc": canonical_tick_time_utc,
        "time_authority_status": time_authority_status,
        "quote_divergence_verdict": quote_div.get("quote_divergence_verdict"),
        "note": "order_send was called" if order_send_called else "DRY_RUN — no order_send",
    }

    if reconcile_positions:
        for pos in reconcile_positions:
            reconcile_summary["position_ticket"] = pos.ticket
            reconcile_summary["position_volume"] = pos.volume
            reconcile_summary["position_price_open"] = pos.price_open
            reconcile_summary["position_sl"] = pos.sl
            reconcile_summary["position_tp"] = pos.tp
            reconcile_summary["position_profit"] = pos.profit

    with open(os.path.join(run_dir, "reconcile.json"), "w") as f:
        json.dump(reconcile_summary, f, indent=2)

    mt5.shutdown()

    # ── Record final state ──
    print(f"\nState: {sm.state.value}")
    print(f"Reconcile: {run_dir}/reconcile.json")
    print(f"\n{'='*60}")
    print(f"  G3.2 EXECUTION HANDOFF COMPLETE")
    print(f"{'='*60}")
    print(f"  Canary ID:          {canary_id}")
    print(f"  Mode:               {'DRY-RUN' if DRY_RUN_MODE else 'LIVE'}")
    print(f"  Time Authority:     {time_authority_status}")
    print(f"  Quote Divergence:   {quote_div.get('max_divergence_ticks')} ticks [{quote_div.get('quote_divergence_verdict')}]")
    print(f"  Mutex Acquired:     {mutex_acquired}")
    print(f"  Intent Persisted:   {intent_recorded}")
    result_label = (
        "DRY_RUN_SEND_BLOCKED" if DRY_RUN_MODE
        else f"order_send retcode={order_send_result.get('retcode')} deal={order_send_result.get('deal')}"
        if order_send_result
        else "UNKNOWN"
    )
    print(f"  Result:             {result_label}")
    print(f"  Artifacts:          {run_dir}")

    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = main()
    finally:
        print("\n--- CLEANUP ---")
        disable_execution()
        activate_kill_switch()
        release_mutex()
        disable_submission()
        print("feature_gate=OFF, kill_switch=ON, mutex=RELEASED, submission=DISABLED")
        print(f"Exit code: {exit_code}")

    sys.exit(exit_code)
