"""Quick 5-cycle verify on Pepperstone."""
import sys, json, time, hashlib
sys.path.insert(0, ".")
import MetaTrader5 as mt5
from graxia.packages.quant_os.shadow.canonical_tick_source import CanonicalTickSource, CanonicalTickPolicy
from graxia.packages.quant_os.shadow.broker_profile import BrokerProfile, validate_broker_match

PEPPERSTONE = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
mt5.initialize(path=PEPPERSTONE)
acct = mt5.account_info()
sym = mt5.symbol_info("XAUUSD")

profile = BrokerProfile()
profile.compute_fingerprint()
match, issues = validate_broker_match(acct.server, acct.login, sym.trade_contract_size, sym.digits, sym.point, profile)
print(f"Broker: {acct.server} | Profile match: {match}")
if issues:
    for i in issues:
        print(f"  {i}")

class MT5Wrapper:
    def __init__(self):
        self._mt5 = mt5
    def get_tick(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {"bid": tick.bid, "ask": tick.ask, "last": tick.last,
                "volume": tick.volume, "time": tick.time,
                "time_msc": tick.time_msc, "flags": tick.flags}

policy = CanonicalTickPolicy(query_interval_seconds=5, trailing_overlap_seconds=30, safety_lag_seconds=2)
source = CanonicalTickSource(MT5Wrapper(), "XAUUSD", policy)

ledger = []
prev_hash = ""
for cycle in range(5):
    batch = source.fetch_cycle()
    entry_hash = hashlib.sha256(json.dumps({
        "cycle": cycle, "verdict": batch.verdict,
        "tick_count": batch.deduplicated_tick_count,
        "batch_hash": batch.batch_hash, "previous_hash": prev_hash,
    }, sort_keys=True).encode()).hexdigest()
    ledger.append({"cycle": cycle, "verdict": batch.verdict,
                   "ticks": batch.deduplicated_tick_count, "hash": entry_hash, "prev": prev_hash})
    prev_hash = entry_hash
    bars = source.get_finalized_m1_bars(1)
    age = batch.canonical_data_age_ms
    print(f"Cycle {cycle}: {batch.verdict} | ticks={batch.deduplicated_tick_count} | age={age:.0f}ms | bars={len(bars)}")
    if batch.rejected_reason:
        print(f"  REASON: {batch.rejected_reason}")
    time.sleep(5)

mt5.shutdown()

valid = all(ledger[i]["prev"] == ledger[i-1]["hash"] for i in range(1, len(ledger)))
seal = ledger[-1]["hash"] if ledger else ""
all_pass = match and valid and all(e["verdict"] == "PASS" for e in ledger)
print(f"Ledger valid: {valid}")
print(f"Ledger seal: {seal[:16]}...")
print(f"Exit gate: {'PASS_TO_BE_P8_5_CAMPAIGN' if all_pass else 'CHECK'}")
