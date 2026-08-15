"""Measure live MT5 swap rates and convert to bps-of-notional (MB-017).

Fills the cost-model gap for EURUSD / GBPUSD / BTCUSD / US30 (and any other
symbols passed): reads MT5 symbol_info swap_long/swap_short/swap_mode via
read-only access, converts to the calibration convention ("Daily swap in bps
of position notional. Negative = cost."), and writes a dated evidence report.

Conversion by swap_mode (official MQL5 SYMBOL_SWAP_MODE enum):
  0 SYMBOL_SWAP_MODE_DISABLED      -> bps = 0
  1 SYMBOL_SWAP_MODE_POINTS        -> bps = swap_points * point_value_per_lot / (price * contract_size) * 10_000
  2 SYMBOL_SWAP_MODE_CURRENCY_SYMBOL -> bps = swap_per_lot / (price * contract_size) * 10_000
  3 SYMBOL_SWAP_MODE_CURRENCY_MARGIN -> bps = swap_per_lot / (price * contract_size) * 10_000
  4 SYMBOL_SWAP_MODE_CURRENCY_DEPOSIT -> bps = swap_per_lot / (price * contract_size) * 10_000
  5 SYMBOL_SWAP_MODE_INTEREST_CURRENT -> bps = rate_pct * 100 / 365  (% per annum of current price)

NOTE: for FX majors (point x contract_size = 1.0), mode 1 points and mode 2
currency give the same bps result; mode 5 is what Pepperstone reports for
BTCUSD/US30 (e.g. BTCUSD long=-11.5 means -11.5% p.a. -> -3.1507 bps/day).

Usage:
    python scripts/measure_swap_rates.py                    # default 4 symbols
    python scripts/measure_swap_rates.py --symbols EURUSD GBPUSD BTCUSD US30
    python scripts/measure_swap_rates.py --symbols XAUUSD   # verify against calibration

The script only MEASURES and reports; it never writes cost_calibration.json.
A human copies the verified bps values into the calibration file.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "reports" / "swap_rates_measurement.json"

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "BTCUSD", "US30"]


def _connect_mt5() -> bool:
    try:
        import MetaTrader5 as mt5  # noqa: N813 — canonical MT5 alias used across the repo
    except ImportError:
        print("FAIL: MetaTrader5 python package not installed")
        return False

    import os

    login = os.environ.get("MT5_LOGIN") or "0"
    password = os.environ.get("MT5_PASSWORD") or ""
    server = os.environ.get("MT5_SERVER") or "Pepperstone-Demo"
    if not mt5.initialize():
        print(f"FAIL: mt5.initialize() -> {mt5.last_error()}")
        return False
    try:
        if login and login != "0":
            ok = mt5.login(login=int(login), password=password, server=server)
            if not ok:
                print(f"WARN: mt5.login() -> {mt5.last_error()} (continuing with default account)")
        return True
    except Exception as exc:  # noqa: BLE001 - any login failure must not crash measurement
        print(f"WARN: mt5.login exception: {exc} (continuing with default account)")
        return True


def measure(symbol: str) -> dict:
    import MetaTrader5 as mt5  # noqa: N813

    info = mt5.symbol_info(symbol)
    if info is None:
        return {"symbol": symbol, "error": f"symbol_info None ({mt5.last_error()})"}

    swap_long = float(getattr(info, "swap_long", 0.0))
    swap_short = float(getattr(info, "swap_short", 0.0))
    mode = int(getattr(info, "swap_mode", 0))
    point = float(getattr(info, "point", 0.0))
    contract_size = float(getattr(info, "trade_contract_size", 100.0))
    rollover3 = int(getattr(info, "swap_rollover3days", 3))

    tick = mt5.symbol_info_tick(symbol)
    price = float(tick.bid) if tick and tick.bid else (float(info.last) if info.last else 0.0)

    def _to_bps(rate: float) -> float:
        if rate == 0.0:
            return 0.0
        if mode == 0:  # disabled
            return 0.0
        if mode in (1, 2, 3, 4):  # points or per-lot currency
            if point == 0.0 or price == 0.0 or contract_size == 0.0:
                return float("nan")
            notional = price * contract_size
            if mode == 1:  # points: value in points -> per-lot currency via point x contract
                per_lot = rate * point * contract_size
            else:  # per-lot currency
                per_lot = rate
            if notional == 0.0:
                return float("nan")
            return round(per_lot / notional * 10_000.0, 4)
        if mode in (5, 6):  # % per annum of current/initial price (official MQL5)
            return round(rate * 100.0 / 365.0, 4)
        return float("nan")

    result = {
        "symbol": symbol,
        "measured_at": datetime.now(UTC).isoformat(),
        "swap_mode": mode,
        "swap_rollover3days": rollover3,
        "price": price,
        "contract_size": contract_size,
        "point": point,
        "swap_long_raw": swap_long,
        "swap_short_raw": swap_short,
        "swap_long_bps": _to_bps(swap_long),
        "swap_short_bps": _to_bps(swap_short),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    args = parser.parse_args()

    if not _connect_mt5():
        return 1

    results = [measure(s) for s in args.symbols]
    for r in results:
        if "error" in r:
            print(f"  {r['symbol']}: ERROR {r['error']}")
        else:
            print(
                f"  {r['symbol']:8s} mode={r['swap_mode']} rollover3={r['swap_rollover3days']} "
                f"price={r['price']:.4f} long={r['swap_long_raw']:+.4f}->{r['swap_long_bps']}bps "
                f"short={r['swap_short_raw']:+.4f}->{r['swap_short_bps']}bps"
            )

    payload = {"schema_version": "1.0", "purpose": "MB-017 swap-rate measurement (bps of notional)", "measured_at": datetime.now(UTC).isoformat(), "source": "MT5 symbol_info (read-only)", "symbols": results}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
