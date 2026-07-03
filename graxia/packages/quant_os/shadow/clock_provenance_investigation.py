"""BE-P8.3.1 — Clock Provenance Investigation.

Cross-checks MT5 timestamps from 3 independent APIs against system clock.
NO assumptions. NO conversions. Raw evidence only.
"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"


def get_system_clock() -> dict:
    """Collect system clock evidence."""
    now_utc = datetime.now(UTC)
    now_epoch_s = time.time()
    now_epoch_ms = int(now_epoch_s * 1000)

    # Windows time service
    ntp_source = "UNKNOWN"
    time_service_status = "UNKNOWN"
    try:
        result = subprocess.run(["w32tm", "/query", "/status"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            time_service_status = "RUNNING"
            for line in result.stdout.splitlines():
                if "Source:" in line or "Stratum:" in line:
                    ntp_source = line.strip()
                    break
    except Exception as e:
        time_service_status = f"ERROR: {e}"

    # Also try w32tm /peers
    ntp_peers = []
    try:
        result = subprocess.run(["w32tm", "/query", "/peers"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Peer:" in line or "Host:" in line:
                    ntp_peers.append(line.strip())
    except Exception:
        pass

    return {
        "system_utc_now_iso": now_utc.isoformat(),
        "system_epoch_s": now_epoch_s,
        "system_epoch_ms": now_epoch_ms,
        "system_utc_from_epoch": datetime.fromtimestamp(now_epoch_s, tz=UTC).isoformat(),
        "ntp_source": ntp_source,
        "time_service_status": time_service_status,
        "ntp_peers": ntp_peers,
    }


def run_mt5_investigation() -> dict:
    """Run MT5 timestamp investigation in a subprocess."""
    script = (
        '''
import json
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

SYMBOL = "'''
        + SYMBOL
        + '''"

result = {
    "mt5_initialize": False,
    "mt5_last_error": "",
    "account_info": {},
    "terminal_info": {},
    "symbol_info": {},
    "investigation": {},
}

# 1. Initialize
ok = mt5.initialize(path=r"'''
        + MT5_PATH
        + """", timeout=10000)
result["mt5_initialize"] = ok
if not ok:
    result["mt5_last_error"] = str(mt5.last_error())
    print(json.dumps(result, indent=2, default=str))
    exit(0)

try:
    # 2. Account info
    ai = mt5.account_info()
    if ai:
        result["account_info"] = {
            "login": ai.login, "server": ai.server,
            "balance": ai.balance, "currency": ai.currency,
        }

    # 3. Terminal info
    ti = mt5.terminal_info()
    if ti:
        result["terminal_info"] = {
            "build": ti.build, "connected": ti.connected,
            "trade_allowed": ti.trade_allowed,
            "dlls_allowed": ti.dlls_allowed,
        }

    # 4. Symbol info
    si = mt5.symbol_info(SYMBOL)
    if si:
        result["symbol_info"] = {
            "name": si.name, "visible": si.visible,
            "point": si.point, "digits": si.digits,
            "trade_mode": si.trade_mode,
            "time": si.time,
        }

    # 5. symbol_info_tick()
    tick = mt5.symbol_info_tick(SYMBOL)
    tick_data = {}
    if tick:
        tick_data = {
            "bid": tick.bid, "ask": tick.ask,
            "last": tick.last, "volume": tick.volume,
            "time": tick.time,
            "time_msc": tick.time_msc,
            "flags": tick.flags,
            "datetime_utc_from_time": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
            "datetime_utc_from_time_msc": datetime.fromtimestamp(tick.time_msc / 1000, tz=timezone.utc).isoformat(),
        }
    else:
        tick_data = {"error": str(mt5.last_error())}

    # 6. copy_ticks_range() — get last 5 ticks
    now = datetime.now(UTC)
    fr = now - timedelta(minutes=5)
    ticks_range = mt5.copy_ticks_range(SYMBOL, fr, now, mt5.COPY_TICKS_ALL)
    ticks_range_data = []
    if ticks_range is not None and len(ticks_range) > 0:
        for t in ticks_range[-5:]:
            ticks_range_data.append({
                "time": int(t[0]),
                "bid": float(t[1]),
                "ask": float(t[2]),
                "last": float(t[3]),
                "volume": int(t[4]),
                "time_msc": int(t[5]) if len(t) > 5 else int(t[0]) * 1000,
                "flags": int(t[6]) if len(t) > 6 else 0,
                "datetime_utc": datetime.fromtimestamp(int(t[0]), tz=timezone.utc).isoformat(),
            })
    else:
        ticks_range_data = {"error": "no ticks", "last_error": str(mt5.last_error())}

    # 7. copy_rates_from_pos() — last 3 bars H1
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 3)
    rates_data = []
    if rates is not None and len(rates) > 0:
        for r in rates:
            rates_data.append({
                "time": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": int(r[5]),
                "datetime_utc": datetime.fromtimestamp(int(r[0]), tz=timezone.utc).isoformat(),
            })
    else:
        rates_data = {"error": "no rates", "last_error": str(mt5.last_error())}

    # 8. copy_rates_range() — last 5 min
    rates_range = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M1, fr, now)
    rates_range_data = []
    if rates_range is not None and len(rates_range) > 0:
        for r in rates_range[-3:]:
            rates_range_data.append({
                "time": int(r[0]),
                "open": float(r[1]),
                "close": float(r[4]),
                "datetime_utc": datetime.fromtimestamp(int(r[0]), tz=timezone.utc).isoformat(),
            })
    else:
        rates_range_data = {"error": "no rates", "last_error": str(mt5.last_error())}

    result["investigation"] = {
        "symbol_info_tick": tick_data,
        "copy_ticks_range_last5": ticks_range_data,
        "copy_rates_from_pos_last3_h1": rates_data,
        "copy_rates_range_last3_m1": rates_range_data,
    }

finally:
    mt5.shutdown()

print(json.dumps(result, indent=2, default=str))
"""
    )
    return script


def main():
    print("=" * 60)
    print("BE-P8.3.1 — CLOCK PROVENANCE INVESTIGATION")
    print("=" * 60)

    # 1. System clock
    print("\n--- SYSTEM CLOCK ---")
    sys_clock = get_system_clock()
    for k, v in sys_clock.items():
        print(f"  {k}: {v}")

    # 2. MT5 investigation
    print("\n--- MT5 TIMESTAMP INVESTIGATION ---")
    script = run_mt5_investigation()
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}")
        return

    mt5_data = json.loads(result.stdout)

    # Print account/terminal
    print(f"  MT5 initialized: {mt5_data['mt5_initialize']}")
    acct = mt5_data.get("account_info", {})
    print(f"  Account: {acct.get('login')} @ {acct.get('server')}")
    term = mt5_data.get("terminal_info", {})
    print(f"  Terminal build: {term.get('build')}, connected: {term.get('connected')}")

    # Print tick investigation
    inv = mt5_data.get("investigation", {})

    print("\n--- SOURCE A: symbol_info_tick() ---")
    tick = inv.get("symbol_info_tick", {})
    if "error" in tick:
        print(f"  ERROR: {tick['error']}")
    else:
        print(f"  bid: {tick.get('bid')}")
        print(f"  ask: {tick.get('ask')}")
        print(f"  raw time: {tick.get('time')}")
        print(f"  raw time_msc: {tick.get('time_msc')}")
        print(f"  datetime from time:     {tick.get('datetime_utc_from_time')}")
        print(f"  datetime from time_msc: {tick.get('datetime_utc_from_time_msc')}")

    print("\n--- SOURCE B: copy_ticks_range() last 5 ---")
    ticks = inv.get("copy_ticks_range_last5", [])
    if isinstance(ticks, dict):
        print(f"  ERROR: {ticks}")
    else:
        for t in ticks:
            print(f"  time={t.get('time')} msc={t.get('time_msc')} utc={t.get('datetime_utc')} bid={t.get('bid')}")

    print("\n--- SOURCE C: copy_rates_from_pos() H1 last 3 ---")
    rates = inv.get("copy_rates_from_pos_last3_h1", [])
    if isinstance(rates, dict):
        print(f"  ERROR: {rates}")
    else:
        for r in rates:
            print(f"  time={r.get('time')} utc={r.get('datetime_utc')} close={r.get('close')}")

    print("\n--- SOURCE C2: copy_rates_range() M1 last 3 ---")
    rates_r = inv.get("copy_rates_range_last3_m1", [])
    if isinstance(rates_r, dict):
        print(f"  ERROR: {rates_r}")
    else:
        for r in rates_r:
            print(f"  time={r.get('time')} utc={r.get('datetime_utc')} close={r.get('close')}")

    # 3. Cross-check
    print("\n--- CROSS-CHECK ---")
    sys_epoch = sys_clock["system_epoch_s"]
    tick_time = tick.get("time", 0)
    tick_msc = tick.get("time_msc", 0)

    if tick_time > 0:
        diff_s = tick_time - sys_epoch
        diff_h = diff_s / 3600
        print(f"  tick.time vs system_epoch: {diff_s:.3f}s ({diff_h:.3f}h)")
    if tick_msc > 0:
        diff_ms = tick_msc - sys_clock["system_epoch_ms"]
        diff_h2 = diff_ms / 3600000
        print(f"  tick.time_msc vs system_ms: {diff_ms}ms ({diff_h2:.3f}h)")

    # Check if tick time matches rates time
    if rates and not isinstance(rates, dict) and len(rates) > 0:
        last_bar_time = rates[-1].get("time", 0)
        if tick_time > 0:
            bar_tick_diff = last_bar_time - tick_time
            print(f"  last_bar.time vs tick.time: {bar_tick_diff}s")

    # 4. Save full evidence
    evidence = {
        "system_clock": sys_clock,
        "mt5_data": mt5_data,
    }
    os.makedirs("shadow_results", exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = f"shadow_results/clock_provenance_{ts}.json"
    with open(path, "w") as f:
        json.dump(evidence, f, indent=2, default=str)
    print(f"\n--- EVIDENCE SAVED: {path} ---")


if __name__ == "__main__":
    main()
