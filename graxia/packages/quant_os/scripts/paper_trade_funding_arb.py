"""Paper Trading — Funding Rate Arbitrage (Direction D, Trial #4001).

Sets up genuine forward paper-testing of the funding-arb feasibility finding
(reports/funding_rate_arb_pilot_*.json, PASS verdict, 2026-07-28): real,
live market data (price + funding rate via ccxt's public Binance endpoint,
no API key required), simulated position and P&L, ZERO real capital.

This is intentionally NOT run through execution/adapters/paper.py's
PaperAdapter — that adapter models a single spot/CFD-style position with
price-based P&L, and has no concept of a periodic funding payment at all
(it's built for FX/metals, not perpetual futures carry). Forcing a 2-leg
delta-neutral cash-and-carry position through a single-instrument price-P&L
adapter would mean either faking a zero price feed (dishonest) or double
counting directional risk that the real strategy doesn't take. This script
tracks the actual mechanism instead: a paper (notional, no real order,
no real capital) position that is delta-neutral by construction (long spot
notional == short perp notional), so its ONLY real cashflow is the funding
payment itself — which is fetched live and recorded honestly, not simulated.

Designed to be re-invoked periodically (e.g. once per funding interval, 8h)
to accumulate a genuine track record over real elapsed days. State persists
to reports/paper_trading/funding_arb_state.json between runs.

Usage:
    python scripts/paper_trade_funding_arb.py --notional-per-leg 1000 --init
    python scripts/paper_trade_funding_arb.py   # subsequent runs: check + record
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import ccxt

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "reports" / "paper_trading" / "funding_arb_state.json"

SYMBOLS = ["BTC/USDT", "ETH/USDT"]

# Same realistic Binance cost assumptions as the feasibility pilot
ASSUMED_SPOT_FEE_BPS = 10.0
ASSUMED_PERP_FEE_BPS = 4.0
ASSUMED_SPREAD_BPS = 2.0
ROUND_TRIP_COST_BPS = 2 * (ASSUMED_SPOT_FEE_BPS + ASSUMED_PERP_FEE_BPS + ASSUMED_SPREAD_BPS)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"positions": {}, "funding_log": [], "created_at": None}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def init_positions(exchange: ccxt.Exchange, notional_per_leg: float, state: dict) -> None:
    """Open PAPER (notional only, no real order) delta-neutral positions."""
    now = datetime.now(UTC).isoformat()
    for symbol in SYMBOLS:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker["last"]
        entry_cost_bps = ROUND_TRIP_COST_BPS / 2  # entry half of the round trip
        state["positions"][symbol] = {
            "notional_usd": notional_per_leg,
            "entry_price": price,
            "opened_at": now,
            # Set equal to opened_at so the first check_and_record_funding()
            # call only picks up funding events strictly AFTER position open
            # (since=now), not the entire pre-existing funding history that
            # ccxt's fetch_funding_rate_history returns by default when
            # since=None. Bug found and fixed same session: the first real
            # run of this script back-filled 100 historical events as if
            # they'd "just happened," inflating the paper track record with
            # pre-existing history instead of only genuinely-forward data.
            "last_checked_at": now,
            "entry_cost_usd": notional_per_leg * entry_cost_bps / 10_000,
            "cumulative_funding_usd": 0.0,
            "n_funding_events_recorded": 0,
        }
        print(f"  Opened PAPER position: {symbol} notional=${notional_per_leg:.2f} "
              f"@ {price:.2f} (spot long / perp short, delta-neutral by construction)")
    state["created_at"] = state["created_at"] or now
    state["notional_per_leg"] = notional_per_leg


def check_and_record_funding(exchange: ccxt.Exchange, state: dict) -> None:
    """Fetch the most recent REAL funding rate for each open position and
    record any funding period(s) that occurred since the last check.
    """
    now = datetime.now(UTC)
    for symbol, pos in state["positions"].items():
        last_checked = pos.get("last_checked_at")
        since_ms = None
        if last_checked:
            since_ms = int(datetime.fromisoformat(last_checked).timestamp() * 1000)

        try:
            history = exchange.fetch_funding_rate_history(symbol, since=since_ms, limit=100)
        except Exception as e:
            print(f"  ERROR fetching funding history for {symbol}: {e}")
            continue

        new_events = [h for h in history if not last_checked or h["timestamp"] > int(
            datetime.fromisoformat(last_checked).timestamp() * 1000
        )]

        for event in new_events:
            rate = event["fundingRate"]
            # Being short the perp: receive funding when rate is positive, pay when negative.
            payment_usd = pos["notional_usd"] * rate
            pos["cumulative_funding_usd"] += payment_usd
            pos["n_funding_events_recorded"] += 1
            state["funding_log"].append({
                "symbol": symbol,
                "timestamp": event["datetime"],
                "funding_rate": rate,
                "payment_usd": round(payment_usd, 4),
            })

        pos["last_checked_at"] = now.isoformat()
        if new_events:
            print(f"  {symbol}: recorded {len(new_events)} new real funding event(s), "
                  f"cumulative funding=${pos['cumulative_funding_usd']:.4f}")
        else:
            print(f"  {symbol}: no new funding events since last check")


def print_summary(state: dict) -> None:
    print("\n" + "=" * 70)
    print("  PAPER TRADING SUMMARY — Funding Rate Arbitrage (Trial #4001)")
    print("  ALL POSITIONS ARE NOTIONAL / PAPER — NO REAL CAPITAL, NO REAL ORDERS")
    print("=" * 70)
    total_funding = 0.0
    total_notional = 0.0
    for symbol, pos in state["positions"].items():
        net = pos["cumulative_funding_usd"] - pos["entry_cost_usd"]
        total_funding += pos["cumulative_funding_usd"]
        total_notional += pos["notional_usd"]
        days_open = (
            (datetime.now(UTC) - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 86400
            if pos.get("opened_at") else 0
        )
        annualized_pct = (net / pos["notional_usd"]) / max(days_open, 0.01) * 365 * 100 if pos["notional_usd"] else 0
        print(f"  {symbol:<10} notional=${pos['notional_usd']:>8.2f}  "
              f"funding_events={pos['n_funding_events_recorded']:>3}  "
              f"cum_funding=${pos['cumulative_funding_usd']:>+8.4f}  "
              f"entry_cost=${pos['entry_cost_usd']:>6.2f}  "
              f"net=${net:>+8.4f}  "
              f"days_open={days_open:>5.2f}  "
              f"annualized={annualized_pct:>+6.2f}%")
    print(f"\n  Total notional: ${total_notional:.2f}  Total cumulative funding: ${total_funding:+.4f}")
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper trade the funding-arb hypothesis with live data")
    parser.add_argument("--notional-per-leg", type=float, default=1000.0,
                         help="Paper notional per symbol, USD (default $1000, no real capital)")
    parser.add_argument("--init", action="store_true", help="Open new paper positions (first run only)")
    args = parser.parse_args()

    exchange = ccxt.binance({"options": {"defaultType": "future"}})
    state = load_state()

    if args.init or not state["positions"]:
        print("Opening PAPER positions with real live prices (no real capital, no real orders)...")
        init_positions(exchange, args.notional_per_leg, state)
    else:
        print("Checking real funding rate history since last run...")
        check_and_record_funding(exchange, state)

    save_state(state)
    print_summary(state)
    print(f"\nState saved: {STATE_PATH}")
    print("Re-run this script periodically (e.g. every 8h, matching the funding interval)")
    print("to accumulate a genuine track record. No action needed between runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
