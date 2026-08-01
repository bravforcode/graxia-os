"""Recompute all Sharpe values in DuckDB from trades_json with frequency-corrected annualization."""
import json
import numpy as np
import duckdb
from paper_engine.analyzer import _trades_per_year_from_dicts

DB = "reports/paper_engine/campaign_results.duckdb"

con = duckdb.connect(DB)
rows = con.execute(
    "SELECT campaign_id, trades_json, sharpe FROM campaigns WHERE trades_json IS NOT NULL AND length(trades_json) > 2"
).fetchall()

updated = 0
for cid, tjson, old_sharpe in rows:
    trades = json.loads(tjson)
    if len(trades) < 2:
        continue
    pnls = np.array([t["net_pnl"] for t in trades])
    returns = pnls / 100000
    tpy = _trades_per_year_from_dicts(trades)
    r_std = returns.std()
    if r_std > 1e-10:
        new_sharpe = float(returns.mean() / r_std * np.sqrt(tpy))
    else:
        new_sharpe = 0.0
    con.execute(
        "UPDATE campaigns SET sharpe = ? WHERE campaign_id = ?",
        [round(new_sharpe, 3), cid]
    )
    updated += 1

con.commit()
con.close()
print(f"Updated {updated} campaigns")
