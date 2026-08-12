"""
G3.2.4 Quote Source Diagnostic. READ-ONLY. 60s runtime. No order API calls.
Diagnoses native (symbol_info_tick) vs canonical (copy_ticks_range) divergence.
"""
import sys, time, statistics
from datetime import datetime, timedelta, UTC

try:
    import MetaTrader5 as mt5
except ImportError:
    print("FAIL: MetaTrader5 package not installed"); sys.exit(1)

SYMBOL = "XAUUSD"
RUN_SECONDS = 60
SAMPLE_INTERVAL = 1.0
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
MAX_AGE_MS = 5000

def ts():
    return datetime.now(UTC)

def fmt_dt(dt):
    return dt.isoformat()

def main():
    print("=== G3.2.4 Quote Source Diagnostic ===")
    print(f"Symbol: {SYMBOL}")
    print(f"Runtime: {RUN_SECONDS}s | Interval: {SAMPLE_INTERVAL}s")
    print("Query: no order_send, no order_check, no order_calc")

    if not mt5.initialize(path=TERMINAL_PATH, timeout=30000):
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        sys.exit(1)

    mt5.symbol_select(SYMBOL, True)
    tick = mt5.symbol_info_tick(SYMBOL)
    sym = mt5.symbol_info(SYMBOL)
    acct = mt5.account_info()

    print("\n--- Identity ---")
    print(f"symbol: {SYMBOL}")
    print(f"terminal: {TERMINAL_PATH}")
    print(f"account: {acct.login}")
    print(f"digits: {sym.digits} point: {sym.point} tick_size: {sym.trade_tick_size}")
    print(f"contract_size: {sym.trade_contract_size}")

    print("\n--- Raw symbol_info_tick() ---")
    print(f"bid={tick.bid} ask={tick.ask} time={tick.time} time_msc={tick.time_msc} flags={tick.flags}")

    now = ts()
    tcks_5s = mt5.copy_ticks_range(SYMBOL, now - timedelta(seconds=5), now, mt5.COPY_TICKS_INFO)
    print("\n--- copy_ticks_range(5s) ---")
    if tcks_5s is not None and len(tcks_5s) > 0:
        print(f"dtype.names: {tcks_5s.dtype.names}")
        last_5s = tcks_5s[-1]
        print(f"raw last valid canonical tick: bid={last_5s['bid']} ask={last_5s['ask']} "
              f"time={last_5s['time']} time_msc={last_5s['time_msc']} flags={last_5s['flags']}")
    else:
        print("no ticks returned")
        last_5s = None

    divergences = []
    native_success = 0
    canonical_liveness = 0
    errors = []

    print(f"\n--- Sampling {int(RUN_SECONDS / SAMPLE_INTERVAL)} intervals ---")
    print(f"{'#':>3} | {'utc_receipt':>28} | {'native_bid':>12} | {'canon_bid':>12} | {'bid_div':>10} | {'ask_div':>10} | {'age_ms':>8}")
    print("-" * 110)

    t0 = time.time()
    i = 0
    while (time.time() - t0) < RUN_SECONDS:
        t_receipt = ts()
        n_tick = mt5.symbol_info_tick(SYMBOL)
        if n_tick is None:
            errors.append({"time": fmt_dt(t_receipt), "error": "symbol_info_tick returned None"})
            time.sleep(SAMPLE_INTERVAL)
            continue
        native_success += 1

        window_start = t_receipt - timedelta(seconds=5)
        c_ticks = mt5.copy_ticks_range(SYMBOL, window_start, t_receipt, mt5.COPY_TICKS_INFO)
        if c_ticks is not None and len(c_ticks) > 0:
            c_last = c_ticks[-1]
            c_bid = float(c_last["bid"])
            c_ask = float(c_last["ask"])
            c_time = int(c_last["time"])
            c_time_dt = datetime.fromtimestamp(c_time, tz=UTC)
            age_ms = (t_receipt - c_time_dt).total_seconds() * 1000
            canonical_liveness += 1

            bid_div = abs(n_tick.bid - c_bid)
            ask_div = abs(n_tick.ask - c_ask)
            divergences.append({"bid": bid_div, "ask": ask_div, "age_ms": age_ms})

            if i < 10:
                print(f"{i:>3} | {fmt_dt(t_receipt):>28} | {n_tick.bid:>12.2f} | {c_bid:>12.2f} | "
                      f"{bid_div:>10.4f} | {ask_div:>10.4f} | {age_ms:>8.1f}")
        else:
            if i < 10:
                print(f"{i:>3} | {fmt_dt(t_receipt):>28} | {n_tick.bid:>12.2f} | {'N/A':>12} | "
                      f"{'N/A':>10} | {'N/A':>10} | {'N/A':>8}")

        i += 1
        time.sleep(SAMPLE_INTERVAL)

    print("\n--- Summary ---")
    print(f"native_quote_call_success_count: {native_success}")
    print(f"canonical_tick_liveness_count: {canonical_liveness}")

    if divergences:
        bid_divs = [d["bid"] for d in divergences]
        ask_divs = [d["ask"] for d in divergences]
        ages = [d["age_ms"] for d in divergences]

        print(f"bid_divergence: min={min(bid_divs):.4f} median={statistics.median(bid_divs):.4f} "
              f"p95={sorted(bid_divs)[int(len(bid_divs)*0.95)]:.4f} max={max(bid_divs):.4f}")
        print(f"ask_divergence: min={min(ask_divs):.4f} median={statistics.median(ask_divs):.4f} "
              f"p95={sorted(ask_divs)[int(len(ask_divs)*0.95)]:.4f} max={max(ask_divs):.4f}")
        print(f"canonical_age_ms: min={min(ages):.1f} median={statistics.median(ages):.1f} "
              f"p95={sorted(ages)[int(len(ages)*0.95)]:.1f} max={max(ages):.1f}")
    else:
        print("no divergence data collected")

    if errors:
        print(f"\n--- Errors ({len(errors)}) ---")
        for e in errors:
            print(f"  {e['time']}: {e['error']}")

    print(f"\nlast_error: {errors[-1]['error'] if errors else 'NONE'}")
    print(f"query_window_utc: {fmt_dt(ts())}")
    print(f"runtime_actual: {time.time() - t0:.1f}s")

    mt5.shutdown()
    print("\n=== Diagnostic complete ===")

if __name__ == "__main__":
    main()
