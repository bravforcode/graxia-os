#!/usr/bin/env python3
"""
XAUUSD Position Size Calculator
================================
Computes position size from account balance, risk percentage, and
stop-loss distance. Cross-checks against broker minimum stop distance.

Usage:
    python scripts/calc_position.py
    python scripts/calc_position.py --balance 50000 --risk-pct 2 --stop-dist 10.00
"""

import argparse
import sys

# ── Constants ───────────────────────────────────────────────────────────────
CONTRACT_SIZE = 100  # 1 lot XAUUSD = 100 oz


def compute_position(
    balance: float,
    risk_pct: float,
    stop_dist: float,
    min_stop_dollars: float = 0.0,
) -> dict:
    """Compute position sizing from balance, risk, and stop distance.

    Parameters
    ----------
    balance : float
        Account balance in account currency (USD).
    risk_pct : float
        Percentage of balance to risk on this trade (e.g. 1.0 = 1%%).
    stop_dist : float
        Stop-loss distance in dollars of risk per lot.
        Example: $6.30 stop means you risk $6.30 per lot traded.
    min_stop_dollars : float
        Broker minimum stop distance in dollars (per lot), to cross-check.

    Returns
    -------
    dict with keys: balance, risk_pct, max_loss, stop_dist,
                    max_lots_raw, max_lots, safe_lot, min_stop_ok
    """
    if balance <= 0:
        raise ValueError("balance must be > 0")
    if risk_pct <= 0 or risk_pct > 100:
        raise ValueError("risk_pct must be in (0, 100]")
    if stop_dist <= 0:
        raise ValueError("stop_dist must be > 0")

    max_loss = balance * risk_pct / 100.0
    max_lots_raw = max_loss / stop_dist
    # Round down to nearest 0.01 lot (standard volume_step)
    max_lots = int(max_lots_raw * 100) / 100.0
    # Safe lot: at most 0.1 lots for paper-trading conservatism
    safe_lot = min(round_down_lot(max_lots * 0.5), 0.1)
    safe_lot = max(safe_lot, 0.01)  # at least min lot

    min_stop_ok = stop_dist >= min_stop_dollars if min_stop_dollars > 0 else True

    return {
        "balance": balance,
        "risk_pct": risk_pct,
        "max_loss": round(max_loss, 2),
        "stop_dist": stop_dist,
        "max_lots_raw": round(max_lots_raw, 4),
        "max_lots": max_lots,
        "safe_lot": safe_lot,
        "min_stop_dollars": min_stop_dollars,
        "min_stop_ok": min_stop_ok,
    }


def round_down_lot(val: float) -> float:
    """Round down to nearest 0.01 lot."""
    return int(val * 100) / 100.0


def fmt_dollars(val: float) -> str:
    return f"${val:,.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="XAUUSD Position Size Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--balance", type=float, default=50_000.0,
        help="Account balance in USD (default: 50000)",
    )
    parser.add_argument(
        "--risk-pct", type=float, default=1.0,
        help="Risk percentage per trade (default: 1.0)",
    )
    parser.add_argument(
        "--stop-dist", type=float, default=6.30,
        help="Stop-loss distance in USD risk per lot (default: 6.30)",
    )
    parser.add_argument(
        "--min-stop", type=float, default=0.50,
        help="Broker minimum stop distance in USD per lot (default: 0.50)",
    )
    args = parser.parse_args()

    try:
        result = compute_position(
            balance=args.balance,
            risk_pct=args.risk_pct,
            stop_dist=args.stop_dist,
            min_stop_dollars=args.min_stop,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    b = result["balance"]
    rp = result["risk_pct"]
    ml = result["max_loss"]
    sd = result["stop_dist"]
    mr = result["max_lots_raw"]
    mf = result["max_lots"]
    sf = result["safe_lot"]
    msd = result["min_stop_dollars"]
    mso = result["min_stop_ok"]

    # ── Output ────────────────────────────────────────────────────────────
    print("=" * 62)
    print("  XAUUSD POSITION SIZE CALCULATOR")
    print("=" * 62)
    print(f"  Balance:                   {fmt_dollars(b):>10s}")
    print(f"  Risk:                      {rp:.1f}%")
    print(f"  Max loss:                  {fmt_dollars(ml):>10s}")
    print(f"  Stop distance (per lot):   {fmt_dollars(sd):>10s}")
    print(f"  Max lots (raw):            {mr:.4f}")
    print(f"  Max lots (rounded down):   {mf:.2f}")
    print(f"  Safe lot (recommended):    {sf:.2f}")
    print()

    # Broker min stop cross-check
    if msd > 0:
        status = "PASS" if mso else "FAIL"
        print(f"  Broker min stop check:     [{status}]")
        print(f"    Your stop:  {fmt_dollars(sd)}/lot")
        print(f"    Broker min: {fmt_dollars(msd)}/lot")
        if not mso:
            print(f"    WARNING: stop_dist ({fmt_dollars(sd)}) < broker min ({fmt_dollars(msd)})")
            print(f"    Increase stop_dist to at least {fmt_dollars(msd)}.")
    else:
        print("  Broker min stop check:     [SKIP] (not provided)")

    print()
    print("-- Summary Line -------------------------------------------------")
    print(f"  For balance {fmt_dollars(b)} at {rp}% risk: "
          f"max loss {fmt_dollars(ml)}. "
          f"With {fmt_dollars(sd)} stop: max {mf:.0f} lots. "
          f"Safe lot: {sf:.2f}")
    print("=" * 62)


if __name__ == "__main__":
    main()
