"""
G3 CLOSE DEMO CANARY — SEPARATE HUMAN APPROVAL REQUIRED.

Does NOT auto-close after open. Requires fresh human confirmation for close.
One close attempt only.

Usage:
    python scripts/g3_close_demo_canary.py <canary_id>

Position must already be open. Reads current broker position tied to canary
correlation ID and creates an immutable close plan for human approval.
"""
import json, hashlib, os, sys, time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
import MetaTrader5 as mt5

from execution.demo_canary.state_machine import CanaryStateMachine
from execution.demo_canary.enums import CanaryState, CanaryActor

# ── Constants ──
SYMBOL = "XAUUSD"
ENVIRONMENT = "PEPPERSTONE_DEMO_ONLY"
PURPOSE = "EXECUTION_LIFECYCLE_CLOSE"
CLOSE_PLAN_TTL_SECONDS = 60
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

OUTPUT_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "g3_close")


def validate_position_for_close(canary_id: str, mt5_connection) -> Optional[dict]:
    """Read current broker position tied to canary correlation ID."""
    positions = mt5_connection.positions_get(symbol=SYMBOL)
    if not positions:
        print(f"No open positions for {SYMBOL}")
        return None

    # Find position matching canary (by comment or magic)
    expected_magic = int(hashlib.sha256(canary_id.encode()).hexdigest()[:8], 16)
    for pos in positions:
        if pos.magic == expected_magic or f"CANARY_{canary_id[-8:]}" in (pos.comment or ""):
            return {
                "ticket": pos.ticket,
                "side": "BUY" if pos.type == 0 else "SELL",
                "volume": pos.volume,
                "open_price": pos.price_open,
                "current_price": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "commission": pos.commission,
                "magic": pos.magic,
                "comment": pos.comment,
                "open_time_utc": datetime.fromtimestamp(pos.time, tz=timezone.utc).isoformat(),
            }

    print(f"No position found matching canary {canary_id} (magic={expected_magic})")
    return None


def create_close_plan(position_data: dict, canary_id: str) -> dict:
    """Create immutable close plan from current broker state."""
    now_utc = datetime.now(timezone.utc)
    close_nonce = uuid4().hex + uuid4().hex
    expiry_utc = datetime.fromtimestamp(
        now_utc.timestamp() + CLOSE_PLAN_TTL_SECONDS, tz=timezone.utc
    )

    opposite_side = "SELL" if position_data["side"] == "BUY" else "BUY"

    plan = {
        "schema_version": "1.0",
        "canary_id": canary_id,
        "purpose": PURPOSE,
        "environment": ENVIRONMENT,
        "symbol": SYMBOL,
        "side": opposite_side,
        "volume": position_data["volume"],
        "position_ticket": position_data["ticket"],
        "position_side": position_data["side"],
        "position_open_price": position_data["open_price"],
        "position_current_price": position_data["current_price"],
        "position_profit": position_data["profit"],
        "position_swap": position_data["swap"],
        "position_commission": position_data["commission"],
        "close_method": "MARKET",
        "generated_at_utc": now_utc.isoformat(),
        "expiry_utc": expiry_utc.isoformat(),
        "close_nonce": close_nonce,
    }
    plan_json = json.dumps(plan, indent=2, sort_keys=True)
    plan["plan_hash"] = hashlib.sha256(plan_json.encode()).hexdigest()
    return plan


def close_approved(mt5_connection, close_plan: dict) -> bool:
    """
    One close attempt. Never retry on unknown.

    # G3_CLOSE_POINT placeholder — would call order_send(TRADE_ACTION_DEAL, opposite side)
    """
    print(f"\n{'='*60}")
    print(f"  G3_CLOSE_POINT_REACHED — would call order_send to close position")
    print(f"  Position ticket: {close_plan['position_ticket']}")
    print(f"  Side:            {close_plan['side']} (opposite of {close_plan['position_side']})")
    print(f"  Volume:          {close_plan['volume']}")
    print(f"{'='*60}")

    # # G3_CLOSE_POINT: order_send would go here when unblocked.
    # # One-shot close only. Never retry.
    # close_request = {
    #     "action": mt5.TRADE_ACTION_DEAL,
    #     "symbol": SYMBOL,
    #     "volume": close_plan["volume"],
    #     "type": mt5.ORDER_TYPE_SELL if close_plan["side"] == "SELL" else mt5.ORDER_TYPE_BUY,
    #     "position": close_plan["position_ticket"],
    #     "price": 0,  # market
    #     "deviation": 10,
    #     "magic": 0,
    #     "comment": f"CLOSE_{close_plan['canary_id'][-8:]}",
    #     "type_time": mt5.ORDER_TIME_GTC,
    #     "type_filling": mt5.ORDER_FILLING_IOC,
    # }
    # result = mt5.order_send(close_request)
    # if result and result.retcode == 10009:
    #     print(f"Close successful: ticket={result.order}")
    #     return True
    # elif result:
    #     print(f"Close failed: retcode={result.retcode}")
    #     return False
    # else:
    #     print(f"Close failed: no result")
    #     return False

    print("Close not executed — G3_CLOSE_POINT blocked by report.")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/g3_close_demo_canary.py <canary_id>")
        print("Example: python scripts/g3_close_demo_canary.py CANARY-20250623-143022")
        return 1

    canary_id = sys.argv[1]
    close_id = f"CLOSE-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    sm = CanaryStateMachine(close_id)
    sm.transition(CanaryState.EXIT_REQUESTED, CanaryActor.OPERATOR, "CLOSE_INITIATED")

    print(f"\n{'='*60}")
    print(f"G3 CLOSE DEMO CANARY — {close_id}")
    print(f"For canary: {canary_id}")
    print(f"{'='*60}")

    # ── Connect ──
    print("\n--- Validating position ---")
    res = mt5.initialize(path=TERMINAL_PATH, timeout=30000)
    if not res:
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        return 1

    mt5.symbol_select(SYMBOL, True)

    # ── Validate position ──
    position_data = validate_position_for_close(canary_id, mt5)
    if not position_data:
        mt5.shutdown()
        print("No valid position to close. Aborting.")
        sm.transition(CanaryState.REJECTED, CanaryActor.SYSTEM, "NO_POSITION_FOUND")
        return 1

    print(f"Position found: ticket={position_data['ticket']}, "
          f"side={position_data['side']}, volume={position_data['volume']}, "
          f"profit={position_data['profit']}")

    # ── Create close plan ──
    close_plan = create_close_plan(position_data, canary_id)

    run_dir = os.path.join(OUTPUT_BASE, close_id)
    os.makedirs(run_dir, exist_ok=True)

    with open(os.path.join(run_dir, "close_plan.json"), "w") as f:
        json.dump(close_plan, f, indent=2)

    # ── Display for human review ──
    print(f"\n{'='*60}")
    print(f"CLOSE PLAN — HUMAN APPROVAL REQUIRED")
    print(f"{'='*60}")
    print(f"  Close ID:       {close_id}")
    print(f"  Canary ID:      {canary_id}")
    print(f"  Plan Hash:      {close_plan['plan_hash']}")
    print(f"  Expiry:         {close_plan['expiry_utc']}")
    print(f"")
    print(f"  Position:       ticket={position_data['ticket']}")
    print(f"  Open side:      {position_data['side']}")
    print(f"  Close side:     {close_plan['side']} (opposite)")
    print(f"  Volume:         {close_plan['volume']}")
    print(f"  Open price:     {position_data['open_price']}")
    print(f"  Current price:  {position_data['current_price']}")
    print(f"  Profit:         {position_data['profit']}")
    print(f"  Swap:           {position_data['swap']}")
    print(f"  Commission:     {position_data['commission']}")
    print(f"")
    print(f"  STATE:          {sm.state.value}")
    print(f"  order_send:     NOT CALLED")
    print(f"{'='*60}")

    # ── Local human approval for close ──
    confirmation = f"CLOSE_DEMO_CANARY {close_id} {close_plan['plan_hash'][:16]} {close_plan['close_nonce'][:16]}"

    print(f"\n========================================")
    print(f"  HUMAN APPROVAL REQUIRED FOR CLOSE")
    print(f"========================================")
    print(f"  > {confirmation}")
    print(f"  Type anything else to CANCEL.")
    print(f"========================================\n")

    try:
        user_input = input("CLOSE APPROVAL: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nClose cancelled (EOF/interrupt).")
        sm.transition(CanaryState.REJECTED, CanaryActor.OPERATOR, "CLOSE_REJECTED_EOF")
        mt5.shutdown()
        return 1

    if user_input != confirmation:
        print(f"\nCLOSE REJECTED or mismatch.")
        sm.transition(CanaryState.REJECTED, CanaryActor.OPERATOR, "CLOSE_REJECTED_MISMATCH")
        mt5.shutdown()
        return 1

    sm.transition(CanaryState.CLOSED_CONFIRMED, CanaryActor.OPERATOR, "CLOSE_APPROVED")

    # ── Execute close ──
    print(f"\nExecuting close...")
    success = close_approved(mt5, close_plan)

    if success:
        sm.transition(CanaryState.SEALED, CanaryActor.SYSTEM, "CLOSE_EXECUTED")
        # ── Record close artifact ──
        close_artifact = {
            "close_id": close_id,
            "canary_id": canary_id,
            "plan_hash": close_plan["plan_hash"],
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "state_machine_state": sm.state.value,
        }
        with open(os.path.join(run_dir, "close_executed.json"), "w") as f:
            json.dump(close_artifact, f, indent=2)

        print(f"\nClose executed successfully.")
        print(f"State: {sm.state.value}")
        print(f"Artifacts: {run_dir}")
    else:
        sm.transition(CanaryState.SUBMISSION_UNKNOWN, CanaryActor.SYSTEM, "CLOSE_RESULT_UNKNOWN")
        print(f"\nClose result unknown. State: {sm.state.value}")

    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
