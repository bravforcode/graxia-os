"""
TSM Paper Trading - 7-Day Monitor
Check portfolio status and metrics.
"""

import json
from pathlib import Path


def check_status():
    """Check and display paper trading status."""
    state_file = Path("artifacts/portfolio/paper_trades/tsm_portfolio_state.json")
    trade_log = Path("artifacts/portfolio/paper_trades/tsm_trade_log.csv")

    print("=" * 60)
    print("TSM Paper Trading - 7-Day Monitor")
    print("=" * 60)

    # Check state
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        print(f"\nLast Update: {state.get('timestamp_utc', 'never')}")
        print(f"Regime: {state.get('regime', 'unknown')}")
        print(f"Trend: {state.get('trend', 'unknown')}")
        print(f"Drawdown: {state.get('drawdown_pct', 0):.2f}%")
        print(f"Vol Scale: {state.get('vol_scale', 1):.4f}")
        print(f"Target Vol: {state.get('config', {}).get('target_vol', 0.1):.1%}")

        # Check positions
        positions = state.get("positions", {})
        if positions:
            print("\nOpen Positions:")
            for sym, pos in positions.items():
                print(f"  {sym}: {pos.get('side', 'unknown')} {pos.get('lots', 0)} lots")
        else:
            print("\nNo open positions")

        # Check fills
        fills = state.get("fills", [])
        if fills:
            print(f"\nRecent Fills: {len(fills)}")
            for fill in fills[-3:]:  # Last 3
                status = "OK" if fill.get("success") else "FAILED"
                print(f"  {fill.get('symbol')}: {fill.get('action')} {fill.get('lots')} lots - {status}")
    else:
        print("\nNo portfolio state found")

    # Check trade log
    if trade_log.exists():
        with open(trade_log) as f:
            lines = f.readlines()
            print(f"\nTrade Log: {len(lines)} entries")
    else:
        print("\nNo trade log found")

    # Status checks
    print("\n" + "=" * 60)
    print("Status Checks:")

    # Kill switch
    ks_file = Path("data/kill_switch_state.json")
    if ks_file.exists():
        ks = json.loads(ks_file.read_text(encoding="utf-8"))
        print(f"  Kill Switch: {ks.get('state', 'unknown')}")
    else:
        print("  Kill Switch: NOT FOUND")

    # Schedule
    print("  Schedule: Mon-Fri at 01:30 UTC")
    print("  Duration: 7 days from start")

    print("=" * 60)


if __name__ == "__main__":
    check_status()
