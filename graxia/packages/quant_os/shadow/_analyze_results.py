"""Analyze campaign results."""
import json

with open("shadow_results/pepperstone_campaign_20260624_052916.json") as f:
    r = json.load(f)

print("Session:", r["session_id"])
print("Symbol:", r["symbol"])
print("Total:", r["total_signals"])
print("Accepted:", r["accepted"])
print("Rejected:", r["rejected"])
print("PnL:", r["hypothetical_pnl"])
print("Cost:", r["cost_total"])
print("Ledger valid:", r["ledger_valid"])
print()
print("Rejection reasons:")
for k, v in r.get("rejection_reasons", {}).items():
    print(f"  {k}: {v}")
print()

cycles = r.get("evidence", [])
if cycles:
    print("First 3 cycles:")
    for c in cycles[:3]:
        print(f"  Cycle {c['cycle']}: {c['outcome']} | ticks={c.get('raw_tick_count', 0)} | spread={c.get('spread', 0):.4f}")
    print("Last 3 cycles:")
    for c in cycles[-3:]:
        print(f"  Cycle {c['cycle']}: {c['outcome']} | ticks={c.get('raw_tick_count', 0)} | spread={c.get('spread', 0):.4f}")

    # Count accepted vs rejected_no_ticks by time
    accepted = [c for c in cycles if c["outcome"] == "accepted"]
    no_ticks = [c for c in cycles if c["outcome"] == "rejected_no_ticks"]
    dup = [c for c in cycles if c["outcome"] == "rejected_duplicate"]
    print(f"\nAccepted: {len(accepted)}")
    print(f"Rejected no ticks: {len(no_ticks)}")
    print(f"Rejected duplicate: {len(dup)}")
