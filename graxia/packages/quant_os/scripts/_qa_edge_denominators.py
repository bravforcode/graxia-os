"""QA: denominator mismatch + VolumeBreakout trade counts from edge_search_all_results."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "reports" / "edge_search_all_results.json").read_text(encoding="utf-8"))
print("universe", d.get("universe"))
print()
for name, r in d["results"].items():
    pa = r.get("per_asset") or {}
    with_trades, zero, errors = [], [], []
    for sym, m in pa.items():
        if not isinstance(m, dict):
            continue
        if m.get("error"):
            errors.append(f"{sym}:{str(m['error'])[:40]}")
        elif int(m.get("n_trades") or 0) == 0:
            zero.append(sym)
        else:
            with_trades.append(sym)
    print(
        f"{name}: total_assets={r.get('total_assets')} pos={r.get('positive_sharpe_count')} "
        f"with_trades={len(with_trades)} zero={zero} err={errors}"
    )

print("\n--- VolumeBreakout detail ---")
for name in ("VolumeBreakout_1.5", "VolumeBreakout_2.0"):
    r = d["results"].get(name, {})
    print(name, "trades=", r.get("total_trades"), "dk=", r.get("dk_t_stat"))
    for sym, m in (r.get("per_asset") or {}).items():
        print(" ", sym, m)
