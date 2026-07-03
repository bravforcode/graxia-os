"""E2E fixture script for release gate — run as standalone process."""

import json
import sys

sys.path.insert(0, r"C:\Users\menum\graxia os")

from graxia.packages.quant_os.backtest.engine_e2e_fixture import get_all_scenarios
from graxia.packages.quant_os.execution.ledger_integrity import IntegrityChain, LedgerRecord

scenarios = get_all_scenarios()
results = []
for name, cfg, bars, ts, signals, exp in scenarios[:3]:
    results.append(name)

print(json.dumps({"scenario_count": len(scenarios), "ran": results}))

chain = IntegrityChain()
for i in range(5):
    rec = LedgerRecord(
        trade_id=f"t-{i}",
        order_id=f"o-{i}",
        symbol="XAUUSD",
        side="BUY",
        entry_price="2000",
        exit_price="2010",
        volume="0.1",
        pnl="10",
        fees="3.5",
        spread_cost="2",
        slippage_cost="1",
        entry_time="2025-01-01T00:00:00",
        exit_time="2025-01-02T00:00:00",
        close_reason="TAKE_PROFIT",
        strategy_id="test",
        contract_snapshot_id="v1",
        risk_policy_version="DEFAULT",
        dataset_manifest_id="d1",
        cost_scenario="BASE",
        git_commit="test",
    )
    chain.append(rec)

valid, errors = chain.verify()
seal = chain.compute_run_seal("test_manifest")
print(json.dumps({"chain_valid": valid, "seal": seal, "errors": errors}))
