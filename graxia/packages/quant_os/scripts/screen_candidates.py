#!/usr/bin/env python3
"""
Candidate screening — Phase 2 acceleration.

Fetches whatever tick history MT5 offers per symbol (copy_ticks_range) and
computes spread quality stats, so we can prune the 120 discovered
candidates down to the handful with real data + genuinely low cost BEFORE
the daemon spends ~14 days measuring everything.

Pure read-only against MT5; never writes universe state (report only).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


OUT = ROOT / "reports" / "candidate_screening_20260803.json"
LOOKBACK_DAYS = 7


def median(values: list[float]) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = min(len(s) - 1, int(q * len(s)))
    return s[idx]


def screen_symbol(mt5, symbol: str) -> dict:
    now = datetime.now(UTC)
    start = now - timedelta(days=LOOKBACK_DAYS)
    ticks = mt5.copy_ticks_range(symbol, start, now, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        return {"symbol": symbol, "ticks": 0, "error": mt5.last_error()}
    spreads = []
    for t in ticks:
        bid = float(t["bid"])
        ask = float(t["ask"])
        mid = (bid + ask) / 2.0
        if mid > 0 and ask >= bid:
            spreads.append((ask - bid) / mid * 10_000.0)
    n = len(ticks)
    return {
        "symbol": symbol,
        "ticks": n,
        "ticks_per_day": round(n / LOOKBACK_DAYS, 1),
        "spread_median_bps": round(median(spreads), 4),
        "spread_p95_bps": round(pct(spreads, 0.95), 4),
        "first_ts": str(ticks[0]["time"]),
        "last_ts": str(ticks[-1]["time"]),
    }


def main() -> None:
    import MetaTrader5 as mt5  # noqa: N813

    if not mt5.initialize(timeout=30000):
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        raise SystemExit(1)

    universe = json.loads((ROOT / "config" / "tradeable_universe.json").read_text(encoding="utf-8"))
    symbols: list[str] = []
    symbol_map: dict[str, str] = {}
    for key in ("measuring", "verifying", "candidate"):
        for entry in universe.get(key, []):
            symbols.append(entry["symbol"])
            mt5_name = entry.get("mt5_symbol")
            if mt5_name and mt5_name != entry["symbol"]:
                symbol_map[entry["symbol"]] = mt5_name

    print(f"Screening {len(symbols)} symbols over ~{LOOKBACK_DAYS}d of tick history...")
    results = []
    try:
        for i, sym in enumerate(symbols, 1):
            broker_name = symbol_map.get(sym, sym)
            mt5.symbol_select(broker_name, True)
            res = screen_symbol(mt5, broker_name)
            if broker_name != sym:
                res["symbol"] = sym
                res["broker_symbol"] = broker_name
            results.append(res)
            if i % 25 == 0 or res["ticks"] == 0:
                print(f"  [{i}/{len(symbols)}] {sym}: ticks={res.get('ticks')}")
    finally:
        mt5.shutdown()

    with_data = [r for r in results if r.get("ticks", 0) > 0]
    with_data.sort(key=lambda r: r["spread_median_bps"])
    report = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "screened": len(symbols),
        "with_tick_history": len(with_data),
        "top_cheapest": with_data[:15],
        "all": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT}")
    print(f"With tick history: {len(with_data)}/{len(symbols)}")
    print("Cheapest 10 by median spread bps:")
    for r in with_data[:10]:
        print(f"  {r['symbol']}: med={r['spread_median_bps']} p95={r['spread_p95_bps']} ticks={r['ticks']}")


if __name__ == "__main__":
    main()
