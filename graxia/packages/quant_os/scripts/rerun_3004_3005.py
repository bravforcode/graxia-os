#!/usr/bin/env python3
"""Re-run Path B trials 3004 (DXYDiv) and 3005 (TSMOM) with $100k capital.

CONTEXT
-------
Trials 3004 and 3005 were originally run with $10k initial capital.
The _historical_size() function in backtest/engine.py rounds down lot sizes,
and with $10k capital + 100bps risk, ~97% of sizing calls rounded to 0.00 lots
(per cot_positioning_edge_verification.txt:15-23).

This caused systematic bias:
- High-vol periods (where stops were wider) had trades silently dropped
- Both mean AND variance estimates are biased
- The sample is truncated, not just translated by a constant

The capital bug was fixed in commit 733dca63:
  -    initial_capital=Decimal("10000"),
  +    initial_capital=Decimal("100000"),

This script re-runs the two tainted strategies with $100k capital.

PRECEDENT: Bug-fix re-runs do NOT consume new trial slots.
The symbol-threading bug fix (commit 59a15bd) set the precedent:
results overwrote the originals, pre-fix preserved as .PRE_SYMBOL_FIX.json.bak.
Same principle applies here — these are measurement error corrections,
not new hypotheses.

USAGE
-----
    cd graxia/packages/quant_os
    python scripts/rerun_3004_3005.py

OUTPUT
------
    reports/path_b_rerun_3004_3005_100k.json
    Prints DK test summary + old vs new comparison table.

UNIVERSE
--------
    7 assets (matching original trial scope):
    XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30
    (BTC/USD excluded — CORE_UNIVERSE minus crypto)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Re-use the same pipeline from edge_search_all.py
sys.path.insert(0, str(ROOT))

from scripts.edge_search_all import (
    run_variant,
    strategy_registry,
    CORE_UNIVERSE,
)


# ── bench comparison data ────────────────────────────────────────────
OLD_RESULTS = {
    3004: {"name": "DXYDiv",    "dk_t": -1.310, "sharpe": -1.166, "pos": "2/7", "trades": 2000},
    3005: {"name": "TSMOM",     "dk_t": -1.206, "sharpe": -1.073, "pos": "2/7", "trades": 1981},
}


def main() -> int:
    # 7-asset universe — match original trial scope, exclude crypto
    universe = [s for s in CORE_UNIVERSE if s not in ("BTCUSD", "ETHUSD")]
    print(f"Universe ({len(universe)}): {universe}")

    # Get strategies from registry (filter to just DXYDiv + TSMOM)
    variants = strategy_registry()
    wanted = {"DXYDiv_default", "TSMOM_default"}
    variants = [(n, f) for n, f in variants if n in wanted]

    if len(variants) != 2:
        print(f"FATAL: expected 2 strategies, found {len(variants)}: {[n for n, _ in variants]}")
        return 1

    print(f"Capital: $100,000 (fixed per commit 733dca63)")
    print(f"GO rule: dk_t > 2.0 AND pos_sharpe >= 5\n")

    new_results: dict = {}
    for name, factory in variants:
        result = run_variant(name, factory, universe)
        new_results[name] = result

    # ── comparison table ──────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print("  COMPARISON: Old ($10k, bug) vs New ($100k, fixed)")
    print(f"{'=' * 72}")
    print(f"  {'Trial':<8}{'Strategy':<14}{'Old dk_t':>12}{'New dk_t':>12}{'Old Sharpe':>12}{'New Sharpe':>12}{'Verdict':<12}")
    print(f"  {'-' * 70}")

    trial_map = {"TSMOM_default": 3005, "DXYDiv_default": 3004}
    for name, result in new_results.items():
        tn = trial_map.get(name, 0)
        old = OLD_RESULTS.get(tn, {})
        old_dk = old.get("dk_t", "?")
        old_sh = old.get("sharpe", "?")
        new_dk = result.get("dk_t_stat", 0)
        new_sh = result.get("pooled_sharpe", 0)
        verdict = result.get("verdict", "?")
        print(
            f"  {tn:<8}{old.get('name', name):<14}"
            f"{old_dk:>12.3f}{new_dk:>12.3f}"
            f"{old_sh:>12.3f}{new_sh:>12.3f}"
            f"{verdict:<12}"
        )

    print(f"\n  RE-RUN NOTE: These are bug-fix re-runs (capital $10k→$100k).")
    print(f"  They do NOT consume new trial slots per symbol-threading precedent.")
    print(f"  Original results preserved in: reports/path_b_tsmom_dxydiv.json")

    # ── save results ──────────────────────────────────────────────
    out_path = ROOT / "reports" / "path_b_rerun_3004_3005_100k.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "capital": "$100,000",
        "universe": universe,
        "fix_commit": "733dca63",
        "bug": "initial_capital $10k → 97% sizing rounded to 0.00 lots",
        "precedent": "symbol-threading bug fix (commit 59a15bd) — bug-fix re-runs do not consume trial slots",
        "old_results": OLD_RESULTS,
        "new_results": {name: {
            "dk_t_stat": r.get("dk_t_stat"),
            "pooled_sharpe": r.get("pooled_sharpe"),
            "positive_sharpe_count": r.get("positive_sharpe_count"),
            "total_trades": r.get("total_trades"),
            "verdict": r.get("verdict"),
            "per_asset": r.get("per_asset", {}),
        } for name, r in new_results.items()},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nResults saved: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
