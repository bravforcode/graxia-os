"""Verify timestamps in latest artifact."""
import json, glob

files = sorted(glob.glob("shadow_results/broker_observed_*.json"))
if not files:
    print("No artifacts found")
    exit(1)

with open(files[-1]) as f:
    data = json.load(f)

print("=== TIMESTAMP VERIFICATION ===")
for e in data["evidence"][:3]:
    sid = e["signal_id"]
    raw_s = e.get("raw_tick_time_seconds", 0)
    raw_m = e.get("raw_tick_time_msc", 0)
    broker = e.get("broker_tick_time_utc", "N/A")
    received = e.get("received_at_utc", "N/A")
    delay = e.get("observed_transport_delay_ms", 0)
    anomaly = e.get("clock_anomaly", "")
    diag = e.get("mt5_last_error", "")
    print(f"{sid}:")
    print(f"  raw_tick_seconds={raw_s}")
    print(f"  raw_tick_msc={raw_m}")
    print(f"  broker_tick_utc={broker}")
    print(f"  received_utc={received}")
    print(f"  delay_ms={delay:.0f}")
    print(f"  anomaly={anomaly or 'none'}")
    if diag:
        print(f"  mt5_error={diag}")
    print()

# Check stale tick diagnostics
stale = [e for e in data["evidence"] if "stale" in e.get("outcome", "")]
if stale:
    print("=== STALE TICK DIAGNOSTICS ===")
    for e in stale[:2]:
        print(f"{e['signal_id']}:")
        print(f"  mt5_last_error={e.get('mt5_last_error','N/A')}")
        print(f"  terminal_connected={e.get('terminal_connected','N/A')}")
        print(f"  symbol_visible={e.get('symbol_visible','N/A')}")
        print(f"  symbol_trade_mode={e.get('symbol_trade_mode','N/A')}")
        print(f"  last_good_tick={e.get('last_good_tick_time_utc','N/A')}")
        print()
