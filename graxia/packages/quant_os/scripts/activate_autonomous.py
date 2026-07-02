"""
Autonomous Engine Activation Script
====================================
Enables the autonomous trading engine with user-specified risk budget.

SAFETY: All 9 guards remain active. This only sets kill_switch = False.

Usage:
  python scripts/activate_autonomous.py --daily-loss 2.0 --weekly-loss 5.0
  python scripts/activate_autonomous.py --dry-run    # Test mode, no real trades
  python scripts/activate_autonomous.py --status      # Check engine status
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

STATE_PATH = Path(__file__).parent.parent / "state" / "autonomous_state.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"enabled": False, "kill_switch": True}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def activate(daily_loss: float = 2.0, weekly_loss: float = 5.0,
             max_position: float = 1.0, max_positions: int = 3,
             cooldown: int = 300, dry_run: bool = False):
    """Enable autonomous engine with specified risk budget."""
    state = load_state()
    state["enabled"] = True
    state["kill_switch"] = False
    state["dry_run"] = dry_run
    state["risk_budget"] = {
        "max_daily_loss_pct": daily_loss,
        "max_weekly_loss_pct": weekly_loss,
        "max_position_pct": max_position,
        "max_open_positions": max_positions,
        "cooldown_seconds": cooldown,
    }
    save_state(state)

    logger.info("engine.activated",
                daily_loss=daily_loss, weekly_loss=weekly_loss,
                dry_run=dry_run)

    print(f"\n{'='*60}")
    print(f"  Autonomous Engine: {'DRY RUN' if dry_run else 'ACTIVE'}")
    print(f"  Daily loss limit:  {daily_loss}%")
    print(f"  Weekly loss limit: {weekly_loss}%")
    print(f"  Max position:      {max_position}%")
    print(f"  Max positions:     {max_positions}")
    print(f"  Cooldown:          {cooldown}s")
    print("  Kill switch:       OFF")
    print(f"{'='*60}\n")
    print("  All 9 safety guards remain ACTIVE.")
    print("  To emergency stop: python scripts/activate_autonomous.py --kill\n")


def deactivate():
    """Emergency stop — sets kill switch to True."""
    state = load_state()
    state["kill_switch"] = True
    save_state(state)
    logger.warning("engine.deactivated")
    print("\n  KILL SWITCH ACTIVATED — All trading stopped.\n")


def status():
    """Print current engine status."""
    state = load_state()
    print(f"\n{'='*60}")
    print("  Autonomous Engine Status")
    print(f"{'='*60}")
    print(f"  Enabled:     {state.get('enabled', False)}")
    print(f"  Kill switch: {state.get('kill_switch', True)}")
    print(f"  Dry run:     {state.get('dry_run', True)}")
    if "risk_budget" in state:
        rb = state["risk_budget"]
        print(f"  Daily loss:  {rb.get('max_daily_loss_pct', '?')}%")
        print(f"  Weekly loss: {rb.get('max_weekly_loss_pct', '?')}%")
        print(f"  Max pos:     {rb.get('max_position_pct', '?')}%")
        print(f"  Max count:   {rb.get('max_open_positions', '?')}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Engine Control")
    parser.add_argument("--activate", action="store_true", help="Enable engine")
    parser.add_argument("--kill", action="store_true", help="Emergency stop")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--daily-loss", type=float, default=2.0)
    parser.add_argument("--weekly-loss", type=float, default=5.0)
    parser.add_argument("--max-position", type=float, default=1.0)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--cooldown", type=int, default=300)
    args = parser.parse_args()

    if args.kill:
        deactivate()
    elif args.activate:
        activate(args.daily_loss, args.weekly_loss, args.max_position,
                 args.max_positions, args.cooldown, args.dry_run)
    else:
        status()


if __name__ == "__main__":
    main()
