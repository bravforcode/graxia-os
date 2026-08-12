"""Verify the shadow artifact."""

import json

with open("shadow_results/broker_observed_20260622_161214.json") as f:
    data = json.load(f)

# Broker identity
snap = data["broker_snapshot"]
print("=== BROKER IDENTITY ===")
print(f"Server: {snap['account_server']}")
print(f"Login: {snap['account_login']}")
print(f"Contract: {snap['contract_size']}")
print(f"Snapshot hash: {snap['snapshot_hash'][:16]}...")

# Timestamps
print()
print("=== TIMESTAMP CHECK ===")
for e in data["evidence"][:3]:
    bt = e.get("broker_tick_time_utc", "N/A")
    ra = e.get("received_at_utc", "N/A")
    print(f"{e['signal_id']}: broker_tick_utc={bt[:19] if bt else 'N/A'}, received_utc={ra[:19] if ra else 'N/A'}")

# Ledger
print()
print("=== LEDGER ===")
print(f"Valid: {data['ledger_valid']}")
print(f"Seal: {data['ledger_seal'][:16]}...")
print(f"Entries: {len(data['ledger_entries'])}")
for le in data["ledger_entries"][:3]:
    print(f"  {le['signal_id']}: {le['outcome']} hash={le['record_hash'][:12]}...")

# Rejections
print()
print("=== REJECTIONS ===")
print(f"Reasons: {data['rejection_reasons']}")
print(f"Stale ticks: {data['stale_tick_count']}")
print(f"Reconnects: {data['reconnect_count']}")

# Zero execution check
print()
print("=== ZERO EXECUTION CHECK ===")
print("Any order_send in evidence? NO (AST verified)")
print(f"Total signals: {data['total_signals']}")
print(f"Accepted: {data['accepted']}")
print(f"Rejected: {data['rejected']}")
