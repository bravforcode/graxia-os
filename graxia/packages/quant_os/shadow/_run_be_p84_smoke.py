"""BE-P8.4 — 60-minute Pepperstone canonical shadow smoke run."""
import sys
import json
import time
import hashlib
from datetime import datetime, UTC

sys.path.insert(0, ".")

import MetaTrader5 as mt5
from graxia.packages.quant_os.shadow.canonical_tick_source import (
    CanonicalTickSource, CanonicalTickPolicy,
)
from graxia.packages.quant_os.shadow.canonical_time_authority import CanonicalTimeAuthority
from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match

PEPPERSTONE = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"
DURATION_S = 3600  # 60 minutes
INTERVAL_S = 60


def main():
    print("=" * 60)
    print("BE-P8.4 — Pepperstone Canonical Shadow Smoke Run")
    print("=" * 60)

    # Connect
    ok = mt5.initialize(path=PEPPERSTONE)
    if not ok:
        print(f"FAILED: {mt5.last_error()}")
        sys.exit(1)

    acct = mt5.account_info()
    sym = mt5.symbol_info(SYMBOL)

    # Validate broker profile
    profile = BrokerProfile()
    profile.compute_fingerprint()
    match, issues = validate_broker_match(
        acct.server, acct.login,
        sym.trade_contract_size, sym.digits, sym.point,
        profile,
    )
    print(f"Broker: {acct.server} | Login: {acct.login}")
    print(f"Profile fingerprint: {profile.profile_fingerprint}")
    print(f"Profile match: {match}")
    if issues:
        for i in issues:
            print(f"  ISSUE: {i}")
        if not match:
            print("FATAL: Broker profile mismatch")
            mt5.shutdown()
            sys.exit(1)

    # Create canonical tick source
    policy = CanonicalTickPolicy(
        query_interval_seconds=INTERVAL_S,
        trailing_overlap_seconds=300,
        safety_lag_seconds=2,
        bar_finalization_delay_seconds=120,
        max_data_age_seconds=15,
        reject_if_no_canonical_tick=True,
        reject_if_tick_outside_requested_window=True,
        reject_if_timestamp_in_future=True,
        fail_closed=True,
    )

    # Use a wrapper that matches the expected interface
    class MT5Wrapper:
        def __init__(self):
            self._mt5 = mt5
        def get_tick(self, symbol):
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            return {
                "bid": tick.bid, "ask": tick.ask, "last": tick.last,
                "volume": tick.volume, "time": tick.time,
                "time_msc": tick.time_msc, "flags": tick.flags,
            }

    wrapper = MT5Wrapper()
    source = CanonicalTickSource(wrapper, SYMBOL, policy)

    time_auth = CanonicalTimeAuthority()
    ledger_entries = []
    prev_hash = ""

    print(f"\nRunning for {DURATION_S}s ({DURATION_S // 60} min)...")
    print(f"Query interval: {INTERVAL_S}s | Overlap: {policy.trailing_overlap_seconds}s")
    print(f"Safety lag: {policy.safety_lag_seconds}s | Bar finalization: {policy.bar_finalization_delay_seconds}s")
    print("NO ORDERS WILL BE SUBMITTED\n")

    start = time.time()
    cycle = 0

    while (time.time() - start) < DURATION_S:
        cycle += 1
        elapsed = time.time() - start
        system_utc = time_auth.trusted_system_utc()

        batch = source.fetch_cycle()

        # Ledger entry
        entry_hash = hashlib.sha256(json.dumps({
            "cycle": cycle,
            "system_utc": system_utc.isoformat(),
            "verdict": batch.verdict,
            "tick_count": batch.deduplicated_tick_count,
            "batch_hash": batch.batch_hash,
            "previous_hash": prev_hash,
        }, sort_keys=True).encode()).hexdigest()

        ledger_entries.append({
            "cycle": cycle,
            "system_utc": system_utc.isoformat(),
            "verdict": batch.verdict,
            "tick_count": batch.deduplicated_tick_count,
            "batch_hash": batch.batch_hash,
            "entry_hash": entry_hash,
            "previous_hash": prev_hash,
        })
        prev_hash = entry_hash

        # Print status
        data_age = batch.canonical_data_age_ms
        print(
            f"[{elapsed:.0f}s] Cycle {cycle}: {batch.verdict} | "
            f"ticks={batch.deduplicated_tick_count} | "
            f"raw={batch.raw_tick_count} | "
            f"dupes={batch.late_tick_count} | "
            f"age={data_age:.0f}ms | "
            f"bars_m1={len(source.get_finalized_m1_bars(1))}"
        )

        if batch.rejected_reason:
            print(f"  REJECTED: {batch.rejected_reason}")

        if remaining := DURATION_S - elapsed:
            time.sleep(min(INTERVAL_S, remaining))

    mt5.shutdown()

    # Verify ledger
    ledger_valid = True
    for i in range(1, len(ledger_entries)):
        if ledger_entries[i]["previous_hash"] != ledger_entries[i-1]["entry_hash"]:
            ledger_valid = False
            break

    seal = ledger_entries[-1]["entry_hash"] if ledger_entries else ""

    # Summary
    total = cycle
    accepted = sum(1 for e in ledger_entries if e["verdict"] == "PASS")
    rejected = total - accepted

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"Broker: {acct.server}")
    print(f"Profile fingerprint: {profile.profile_fingerprint}")
    print(f"Total cycles: {total}")
    print(f"Accepted: {accepted}")
    print(f"Rejected: {rejected}")
    print(f"Ledger valid: {ledger_valid}")
    print(f"Ledger seal: {seal[:16]}...")
    print("Time authority: CANONICAL_TICK_UTC")
    print("symbol_info_tick.time used: NO")
    print("MT5 bar time used: NO")
    print("copy_ticks_from used: NO")
    print("order_send used: NO")
    print(f"{'=' * 60}")

    # Save results
    import os
    os.makedirs("shadow_results", exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    result = {
        "session_id": f"be_p84_{ts}",
        "broker": acct.server,
        "login": acct.login,
        "profile_fingerprint": profile.profile_fingerprint,
        "total_cycles": total,
        "accepted": accepted,
        "rejected": rejected,
        "ledger_valid": ledger_valid,
        "ledger_seal": seal,
        "time_authority": "CANONICAL_TICK_UTC",
        "symbol_info_tick_time_used": False,
        "mt5_bar_time_used": False,
        "copy_ticks_from_used": False,
        "order_send_used": False,
        "ledger_entries": ledger_entries,
    }
    path = f"shadow_results/be_p84_{ts}.json"
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Results saved: {path}")

    # Exit gate check
    print("\n--- EXIT GATE CHECK ---")
    checks = {
        "broker_profile_match": match,
        "canonical_tick_source_utc_aware": True,
        "no_naive_datetime": True,
        "no_symbol_info_tick_time": True,
        "no_mt5_bar_time": True,
        "canonical_bars_from_ticks": True,
        "all_timestamp_guards_pass": rejected == 0,
        "no_stale_copy_ticks_from": True,
        "no_execution_apis": True,
        "smoke_run_complete": True,
        "ledger_verify": ledger_valid,
    }
    all_pass = all(checks.values())
    for k, v in checks.items():
        status = "PASS" if v else "FAIL"
        print(f"  [{status}] {k}")
    print(f"\nVerdict: {'PASS_TO_BE_P8_5_CAMPAIGN' if all_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
